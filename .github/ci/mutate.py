#!/usr/bin/env python3
"""Mutation check for the right-side modifier fix (CI-only helper, not part of the PR).

Each mutation reverts one piece of the fix; its guarding tests must then fail.
A baseline run first proves the guarding tests pass on the unmutated tree, so a
typo in a test name (which would run zero tests) cannot pass as "killed".
"""
import pathlib
import subprocess
import sys

XCB = [
    "xcodebuild", "-project", "Mos.xcodeproj", "-scheme", "Debug",
    "-destination", "platform=macOS", "CODE_SIGNING_ALLOWED=NO", "test",
]

T_BINDING = "MosTests/ButtonBindingTests/"
T_PROCESSOR = "MosTests/InputProcessorTests/"

MUTATIONS = [
    (
        "recorder-always-left",
        "Mos/Keys/KeyCode.swift",
        "return isRightOnly ? candidate.right : candidate.left",
        "return candidate.left",
        [T_BINDING + "testPrimaryModifierKeyCode_picksSideFromDeviceFlags",
         T_BINDING + "testNormalizedCustomBindingName_recordedRightOptionKeepsItsOwnKeyCode"],
    ),
    (
        "display-no-side-marker",
        "Mos/InputEvent/InputEvent.swift",
        'return isRightSide && selfMask == mask ? "\\(base) (R)" : base',
        "return base",
        [T_BINDING + "testInputEventDisplayComponents_marksOnlyRightSideModifierKeys",
         T_BINDING + "testActionDisplayResolver_rendersRightOptionCustomBindingWithSideMarker"],
    ),
    (
        "executor-no-right-device-bit",
        "Mos/Shortcut/ShortcutExecutor.swift",
        "flags |= KeyCode.getDeviceMask(code)",
        "flags |= 0",
        [T_PROCESSOR + "testModifierKeyEventFlags_rightSideKeysCarryTheirDeviceFlag"],
    ),
    (
        "executor-device-bit-on-left-keys",
        "Mos/Shortcut/ShortcutExecutor.swift",
        "if KeyCode.rightModifierKeys.contains(code) {",
        "if KeyCode.modifierKeys.contains(code) {",
        [T_PROCESSOR + "testModifierKeyEventFlags_leftSideAndFnKeysAreUnchanged"],
    ),
]


def run_tests(tests, log_name):
    args = XCB + [f"-only-testing:{t}" for t in tests]
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    pathlib.Path(log_name).write_text(proc.stdout)
    out = proc.stdout
    build_failed = "** BUILD FAILED **" in out or "** TEST BUILD FAILED **" in out
    test_failed = "** TEST FAILED **" in out
    executed = [line for line in out.splitlines() if "Executed " in line and " test" in line]
    return proc.returncode, build_failed, test_failed, executed[-1].strip() if executed else "(no 'Executed' line)"


def main():
    all_tests = sorted({t for *_, tests in MUTATIONS for t in tests})
    code, build_failed, test_failed, executed = run_tests(all_tests, "mutation-baseline.log")
    print(f"baseline: rc={code} {executed}")
    if code != 0 or build_failed or test_failed or "Executed 0 tests" in executed:
        print("::error::baseline run of the guarding tests did not pass cleanly")
        return 1

    failures = 0
    for name, path, before, after, tests in MUTATIONS:
        src = pathlib.Path(path)
        original = src.read_text()
        if original.count(before) != 1:
            print(f"::error::{name}: expected exactly one match in {path}, found {original.count(before)}")
            failures += 1
            continue
        src.write_text(original.replace(before, after))
        try:
            code, build_failed, test_failed, executed = run_tests(tests, f"mutation-{name}.log")
        finally:
            src.write_text(original)
        if build_failed:
            verdict = "INCONCLUSIVE (build failed)"
            failures += 1
        elif code != 0 and test_failed:
            verdict = "killed"
        else:
            verdict = "SURVIVED"
            failures += 1
        print(f"{name}: {verdict} | rc={code} | {executed}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
