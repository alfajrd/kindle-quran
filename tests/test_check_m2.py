#!/usr/bin/env python3
"""Durable regression tests for `kindle-quran/tools/check_m2.py`.

Same discipline as `tests/test_check_m0.py` / `tests/test_check_m1.py`:
each test builds a deliberately corrupted COPY of `kindle-quran/` in a
throwaway temp directory, runs the real, unmodified `tools/check_m2.py`
against that copy (`--root <copy>`), and asserts it FAILS -- and asserts
exactly which R-check id caught it. One test per R-check (R1-R12) plus
`test_clean_tree_passes` -- 13 tests.

None of this ever touches the real repository tree. Every mutation happens
on a `tempfile.mkdtemp()` copy, and every test removes its own temp
directory in a `finally` block.

KNOWN LIMITATION -- READ BEFORE TRUSTING THIS SUITE
------------------------------------------------------------------------
`check_m2.py`'s R-checks are purely structural: they prove the artefact is
well-formed, the two fences hold, the MUST-VERIFY registry matches the
code, and the STEP markers stay in sync. They prove NOTHING about whether
`TextBoxWidget`, `LuaSettings`, `ButtonDialog`, or any other KOReader API
actually behaves as `reader.lua`/`settings.lua` assume -- that is what
`docs/VERIFY-M2.md`'s registry exists to track, and only a real on-device
pass (README.md's "Milestone 2 — on-device checklist", D1-D12) can confirm
or refute it. A green `check_m2.py` (and a green run of this suite) is not
evidence the reader renders correctly on a Kindle.

Usage:
    python kindle-quran/tests/test_check_m2.py
    (from the repo root, or any cwd -- paths are resolved from this file's
    location, not from cwd)

Also runnable under pytest, but pytest is NOT required.

Stdlib only. No network. No Lua execution.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK_M2_SCRIPT = os.path.join(REPO_ROOT, "tools", "check_m2.py")

READER_REL = os.path.join("quran.koplugin", "reader.lua")
SETTINGS_REL = os.path.join("quran.koplugin", "settings.lua")
META_REL = os.path.join("quran.koplugin", "_meta.lua")
VERIFY_DOC_REL = os.path.join("docs", "VERIFY-M2.md")
PAGING_MODEL_REL = os.path.join("tools", "paging_model.py")
README_REL = "README.md"

TEXTBOX_END = "-- END TEXTBOX INTERNALS"
CONCAT_BEGIN = "-- BEGIN VERBATIM CONCAT"
CONCAT_END = "-- END VERBATIM CONCAT"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def write_bytes(path, data):
    with open(path, "wb") as f:
        f.write(data)


def read_text(path):
    return read_bytes(path).decode("utf-8")


def write_text(path, text):
    write_bytes(path, text.encode("utf-8"))


def make_mutant_copy():
    tmp = tempfile.mkdtemp(prefix="check_m2_test_")
    dst = os.path.join(tmp, "kindle-quran")
    shutil.copytree(
        REPO_ROOT,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"),
    )
    return tmp, dst


def run_checker(root):
    """Runs the REAL, unmodified tools/check_m2.py (from the copy, which
    itself shells out to the copy's own check_m1.py) against `--root
    <root>`. Returns (returncode, {id: bool}, stdout)."""
    proc = subprocess.run(
        [sys.executable, os.path.join(root, "tools", "check_m2.py"), "--root", root],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    statuses = {}
    for line in proc.stdout.splitlines():
        m = re.match(r"^(PASS|FAIL)\s+(\S+)\s", line)
        if m:
            statuses[m.group(2)] = (m.group(1) == "PASS")
    return proc.returncode, statuses, proc.stdout + proc.stderr


def assert_failed(statuses, stdout, *check_ids):
    for check_id in check_ids:
        assert statuses.get(check_id) is False, (
            "expected %s to FAIL but it did not (or was not reported)\n%s"
            % (check_id, stdout)
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_clean_tree_passes():
    tmp, dst = make_mutant_copy()
    try:
        code, statuses, stdout = run_checker(dst)
        assert code == 0, "expected exit 0 on an unmodified copy, got %d\n%s" % (code, stdout)
        for check_id in ("R%d" % i for i in range(1, 13)):
            assert statuses.get(check_id) is True, "%s did not PASS on a clean tree\n%s" % (check_id, stdout)
        assert "check_m2.py OVERALL: PASS" in stdout, stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_missing_settings_lua_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        os.remove(os.path.join(dst, SETTINGS_REL))
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "R1")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_unparseable_reader_lua_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, READER_REL)
        write_bytes(path, read_bytes(path) + b"\nfunction broken( (\n")
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "R2")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_missing_textboxwidget_require_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, READER_REL)
        src = read_text(path)
        assert 'require("ui/widget/textboxwidget")' in src, "test fixture assumption broken"
        mutated = src.replace(
            'local TextBoxWidget = require("ui/widget/textboxwidget")',
            'local TextBoxWidget = nil -- require removed by test',
        )
        assert mutated != src, "test fixture assumption broken: require line not found in expected form"
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "R3")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_line_height_px_moved_outside_fence_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, READER_REL)
        src = read_text(path)
        assert TEXTBOX_END in src, "test fixture assumption broken"
        # Insert a real code line using the restricted identifier just
        # after the fence closes (i.e. outside it).
        mutated = src.replace(
            TEXTBOX_END,
            TEXTBOX_END + "\nlocal leaked_line_height_px_reference = line_height_px\n",
            1,
        )
        assert mutated != src
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "R4")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_gsub_inside_concat_fence_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, READER_REL)
        src = read_text(path)
        assert CONCAT_BEGIN in src and CONCAT_END in src, "test fixture assumption broken"
        mutated = src.replace(
            CONCAT_BEGIN,
            CONCAT_BEGIN + "\nlocal _test_mutation = text:gsub(\" \", \"\")\n",
            1,
        )
        assert mutated != src
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "R5")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_deleted_verify_doc_entry_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, VERIFY_DOC_REL)
        src = read_text(path)
        lines = src.splitlines(keepends=True)
        mutated_lines = [line for line in lines if not re.match(r"\|\s*V20\s*\|", line)]
        assert len(mutated_lines) < len(lines), "test fixture assumption broken: no V20 table row found"
        write_text(path, "".join(mutated_lines))
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "R6")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_typography_constant_changed_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, SETTINGS_REL)
        src = read_text(path)
        mutated = src.replace("arabic_font_size = 34", "arabic_font_size = 32", 1)
        assert mutated != src, "test fixture assumption broken: 'arabic_font_size = 34' not found"
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "R7")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_meta_version_changed_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, META_REL)
        src = read_text(path)
        mutated = src.replace('version = "0.3.0-m2"', 'version = "0.3.1-m2"', 1)
        assert mutated != src, "test fixture assumption broken"
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "R8")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_deleted_step_marker_from_paging_model_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, PAGING_MODEL_REL)
        src = read_text(path)
        mutated = src.replace("# STEP W2\n", "", 1)
        assert mutated != src, "test fixture assumption broken: '# STEP W2' not found"
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "R9")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_deleted_d7_from_readme_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, README_REL)
        src = read_text(path)
        lines = src.splitlines(keepends=True)
        mutated_lines = [line for line in lines if not re.match(r"\|\s*D7\s*\|", line)]
        assert len(mutated_lines) < len(lines), "test fixture assumption broken: no D7 table row found"
        write_text(path, "".join(mutated_lines))
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "R10")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_zone_constant_changed_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, READER_REL)
        src = read_text(path)
        mutated = src.replace(
            "local ZONE_MENU_X_MIN_FRAC = 0.25",
            "local ZONE_MENU_X_MIN_FRAC = 0.2",
            1,
        )
        assert mutated != src, "test fixture assumption broken"
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "R11")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_io_open_added_to_settings_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, SETTINGS_REL)
        src = read_text(path)
        mutated = src + "\n-- test mutation\nlocal _f = io.open(\"/tmp/x\", \"w\")\n"
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "R12")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Runner (no pytest required)
# ---------------------------------------------------------------------------

def _collect_tests():
    mod = sys.modules[__name__]
    return sorted(
        (name, getattr(mod, name))
        for name in dir(mod)
        if name.startswith("test_") and callable(getattr(mod, name))
    )


def main():
    tests = _collect_tests()
    failures = []
    for name, fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failures.append(name)
            print("FAIL  %s" % name)
            msg = str(exc)
            if msg:
                print("      " + msg.replace("\n", "\n      "))
        except Exception as exc:  # pragma: no cover - unexpected error
            failures.append(name)
            print("ERROR %s: %r" % (name, exc))
        else:
            print("PASS  %s" % name)

    total = len(tests)
    if failures:
        print("RESULT: FAIL (%d of %d failed)" % (len(failures), total))
        return 1
    print("RESULT: PASS (%d tests)" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
