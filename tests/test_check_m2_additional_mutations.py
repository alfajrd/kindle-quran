#!/usr/bin/env python3
"""Additional mutation tests for `tools/check_m2.py`, beyond the coder's own
`tests/test_check_m2.py` (13 tests -- one per R-check plus a clean-tree
test).

Same discipline: copy the whole repo to a `tempfile.mkdtemp()`, corrupt
exactly one thing, run the REAL unmodified `tools/check_m2.py --root <copy>`,
assert what actually happens, clean up in `finally`. Never touches the real
repo tree.

Purpose: the coder's own 13 tests each prove a check catches *one*
representative corruption. This suite asks the harder question the test
brief asks for -- "a check that passes on corrupted input is worse than no
check" -- by trying a SECOND, differently-shaped corruption against several
of the same checks, and by deliberately probing for corruptions that a
purely textual/regex check is structurally unable to catch (a check that
scans raw source text, not parsed code, cannot tell a live `require(...)`
call from the same string sitting inside a comment).

Where a check is found to be genuinely vacuous against a realistic
corruption, the test still runs and its result is reported honestly in
`test-results.md` -- this file does not "fix" `check_m2.py`.

Usage:
    python kindle-quran/tests/test_check_m2_additional_mutations.py
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

READER_REL = os.path.join("quran.koplugin", "reader.lua")
SETTINGS_REL = os.path.join("quran.koplugin", "settings.lua")
META_REL = os.path.join("quran.koplugin", "_meta.lua")
VERIFY_DOC_REL = os.path.join("docs", "VERIFY-M2.md")
PAGING_MODEL_REL = os.path.join("tools", "paging_model.py")
README_REL = "README.md"
BUILD_DOC_REL = os.path.join("docs", "BUILD.md")

CONCAT_BEGIN = "-- BEGIN VERBATIM CONCAT"
CONCAT_END = "-- END VERBATIM CONCAT"


def read_text(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8")


def write_text(path, text):
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def make_mutant_copy():
    tmp = tempfile.mkdtemp(prefix="check_m2_extra_test_")
    dst = os.path.join(tmp, "kindle-quran")
    shutil.copytree(
        REPO_ROOT,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"),
    )
    return tmp, dst


def run_checker(root):
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


# ---------------------------------------------------------------------------
# R1 -- also catches a missing "Modify" file, not just a missing "Create" one.
# ---------------------------------------------------------------------------

def test_r1_catches_missing_modify_file_not_just_missing_create_file():
    tmp, dst = make_mutant_copy()
    try:
        os.remove(os.path.join(dst, BUILD_DOC_REL))
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert statuses.get("R1") is False, (
            "R1 did not fail when a spec-'Modify' file (docs/BUILD.md) was deleted -- "
            "R1's own list (M2_MODIFY_FILES) does include it, so this should fail:\n" + stdout
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# R2 -- also catches a broken settings.lua, not just a broken reader.lua.
# ---------------------------------------------------------------------------

def test_r2_catches_unparseable_settings_lua_too():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, SETTINGS_REL)
        with open(path, "ab") as f:
            f.write(b"\nfunction also_broken( (\n")
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert statuses.get("R2") is False, stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_r2_catches_missing_final_return():
    # R2 requires the LAST top-level statement to be `Return`. Appending a
    # harmless statement after `return Reader` should be caught.
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, READER_REL)
        src = read_text(path)
        assert src.rstrip().endswith("return Reader")
        mutated = src.rstrip() + "\nprint(\"oops, not the last statement anymore\")\n"
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert statuses.get("R2") is False, stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# R3 -- KNOWN GAP: check_r3 is `'require("ui/widget/textboxwidget")' in src`,
# a raw substring test over the WHOLE file, not over parsed/de-commented
# code (unlike R4's identifier check, which does blank comments first).
# Commenting out the actual require call -- which breaks the module at
# runtime (TextBoxWidget stays nil, every construction throws) -- still
# leaves the literal substring in the file, so R3 does not catch it. This is
# a real vacuous-check finding, reported as such; not something this test
# suite is allowed to fix.
# ---------------------------------------------------------------------------

def test_r3_catches_a_commented_out_require():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, READER_REL)
        src = read_text(path)
        live_line = 'local TextBoxWidget = require("ui/widget/textboxwidget")'
        assert live_line in src, "test fixture assumption broken"
        mutated = src.replace(live_line, "-- " + live_line + "  -- DISABLED BY TEST", 1)
        assert mutated != src
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        # Regression guard. This was a real gap: R3 scanned raw file text,
        # so a require commented out still satisfied it while TextBoxWidget
        # would be nil at runtime. check_m2.py now blanks Lua comments
        # before scanning (strip_lua_comments), so the mutation is caught.
        # If this ever passes again, that hardening has been lost.
        assert statuses.get("R3") is False, (
            "R3 no longer catches a commented-out require -- strip_lua_comments has "
            "regressed or R3 stopped using it\n" + stdout
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# R4 -- also catches the identifier leaking via a *different* new statement
# than the one the coder's own mutation test uses (a bare reference vs. a
# local declaration), and confirms genuinely-commented mentions of the
# identifier do NOT false-fail (already relied on by the real file's own
# header comment, which names all three identifiers by prose).
# ---------------------------------------------------------------------------

def test_r4_catches_vertical_string_list_leaking_outside_fence():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, READER_REL)
        src = read_text(path)
        end_marker = "-- END TEXTBOX INTERNALS"
        assert end_marker in src
        mutated = src.replace(
            end_marker,
            end_marker + "\nlocal function count_lines(box) return #box.vertical_string_list end\n",
            1,
        )
        assert mutated != src
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert statuses.get("R4") is False, stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_r4_true_negative_clean_tree_header_prose_does_not_false_fail():
    # The real reader.lua's own module header names line_height_px,
    # vertical_string_list, and lines_per_page by prose, OUTSIDE the fence,
    # inside a `--[[--`/`--]]--` block comment. R4 must not flag that --
    # confirms blank_lua_comments() is doing its job, not just present.
    tmp, dst = make_mutant_copy()
    try:
        src = read_text(os.path.join(dst, READER_REL))
        assert "line_height_px" in src.split("-- BEGIN TEXTBOX INTERNALS")[0], (
            "test fixture assumption broken: the real file's header prose "
            "no longer mentions line_height_px before the fence"
        )
        code, statuses, stdout = run_checker(dst)
        assert statuses.get("R4") is True, (
            "R4 false-failed on the real, unmodified reader.lua's own header-comment prose\n" + stdout
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# R5 -- every forbidden pattern in the list actually gets caught, not just
# `:gsub(` (the one pattern the coder's own suite exercises).
# ---------------------------------------------------------------------------

FORBIDDEN_PATTERNS_TO_PROBE = (
    "string.upper(text)",
    "text:sub(1, 5)",
    "text:rep(2)",
    "text:upper()",
    "text:lower()",
    "text:gmatch(\"%a+\")",
    "text:find(\"x\")",
    "text:match(\"x\")",
)


def test_r5_catches_every_forbidden_pattern_in_the_list():
    tmp, dst = make_mutant_copy()
    try:
        base_src = read_text(os.path.join(dst, READER_REL))
        assert CONCAT_BEGIN in base_src and CONCAT_END in base_src
        for probe in FORBIDDEN_PATTERNS_TO_PROBE:
            mutated = base_src.replace(
                CONCAT_BEGIN,
                CONCAT_BEGIN + "\nlocal _test_mutation = " + probe + "\n",
                1,
            )
            assert mutated != base_src, "probe %r produced no change" % probe
            write_text(os.path.join(dst, READER_REL), mutated)
            code, statuses, stdout = run_checker(dst)
            assert statuses.get("R5") is False, (
                "R5 did not catch forbidden pattern %r inside the VERBATIM CONCAT fence\n%s" % (probe, stdout)
            )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# R6 -- catches a doc row that keeps the id but drops the required source
# path (the coder's own test only deletes the whole row).
# ---------------------------------------------------------------------------

def test_r6_catches_doc_row_present_but_missing_source_path():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, VERIFY_DOC_REL)
        src = read_text(path)
        lines = src.splitlines(keepends=True)
        mutated_lines = []
        found = False
        for line in lines:
            if re.match(r"\|\s*V20\s*\|", line):
                # Strip the trailing "| `frontend/...` |" cell so V20 is
                # still mentioned by id but no longer carries a source path.
                stripped = re.sub(r"\|\s*`frontend/[^`]*`\s*\|\s*$", "|", line.rstrip("\n")) + "\n"
                assert stripped != line, "test fixture assumption broken: V20 row shape changed"
                mutated_lines.append(stripped)
                found = True
            else:
                mutated_lines.append(line)
        assert found, "test fixture assumption broken: no V20 row found"
        write_text(path, "".join(mutated_lines))
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert statuses.get("R6") is False, (
            "R6 did not catch a V20 doc row that kept the id but lost its source path\n" + stdout
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# R7 -- boundary discipline: "0.9" must not be satisfied by "0.90", and a
# missing max (60) must be caught independently of a missing default (34).
# ---------------------------------------------------------------------------

def test_r7_catches_a_wrong_default_even_when_a_comment_still_says_the_right_number():
    # Regression guard for a real gap: check_r7 used to ask "does this
    # number appear ANYWHERE in settings.lua", comments included. The file's
    # own header comment says "line_height = 0.9" above the DEFAULTS table,
    # so changing only the real default to 0.90 left the comment's 0.9
    # standing in for it and R7 passed on a wrong shipped default.
    # check_m2.py now blanks comments first, so only the declaration counts.
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, SETTINGS_REL)
        src = read_text(path)
        needle = "arabic_line_height = 0.9,"
        assert needle in src, "test fixture assumption broken"
        mutated = src.replace(needle, "arabic_line_height = 0.90,", 1)
        assert mutated != src
        # Confirm the comment above still contains the unqualified "0.9"
        # that lets R7 be fooled -- this is the mechanism, not a guess.
        assert re.search(r"(?<![0-9.])0\.9(?![0-9.])", mutated), "test fixture assumption broken: no stray 0.9 left in comments"
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert statuses.get("R7") is False, (
            "R7 no longer catches the real default changing to 0.90 while a comment still "
            "carries 0.9 -- strip_lua_comments has regressed or R7 stopped using it\n" + stdout
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_r7_catches_missing_max_independent_of_default():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, SETTINGS_REL)
        src = read_text(path)
        needle = "max = 60"
        assert needle in src
        mutated = src.replace(needle, "max = 58", 1)
        assert mutated != src
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert statuses.get("R7") is False, stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# R8 -- catches description losing "Milestone 2" independent of the version
# string being right.
# ---------------------------------------------------------------------------

def test_r8_catches_description_losing_milestone_2_wording():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, META_REL)
        src = read_text(path)
        assert "Milestone 2" in src
        mutated = src.replace("Milestone 2", "milestone two", 1)
        assert mutated != src
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert statuses.get("R8") is False, stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# R9 -- catches the two files' STEP-W lists diverging by REORDERING, not
# just by deleting a marker.
# ---------------------------------------------------------------------------

def test_r9_catches_reordered_step_markers():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, PAGING_MODEL_REL)
        src = read_text(path)
        assert "# STEP W1" in src and "# STEP W2" in src
        mutated = src.replace("# STEP W1", "# STEP W1_TMP", 1) \
                      .replace("# STEP W2", "# STEP W1", 1) \
                      .replace("# STEP W1_TMP", "# STEP W2", 1)
        assert mutated != src
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert statuses.get("R9") is False, (
            "R9 did not catch paging_model.py's STEP W1/W2 markers being swapped relative to reader.lua\n" + stdout
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_r9_is_scoped_to_w_markers_only_p_markers_are_not_compared():
    # Documents (does not "fix") the coder's own flagged deviation #2:
    # spec.md §8.5's literal text for R9 does not restrict to W-prefixed
    # markers, but check_m2.py's R9 does. Deleting a `-- STEP P<n>` marker
    # from reader.lua must NOT be caught by R9 as implemented -- if it ever
    # is, the implementation has changed and this test (and the report)
    # should be revisited.
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, READER_REL)
        src = read_text(path)
        assert "-- STEP P3" in src
        mutated = src.replace("-- STEP P3", "-- (P3 marker removed by test)", 1)
        assert mutated != src
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert statuses.get("R9") is True, (
            "R9 unexpectedly reacted to a deleted STEP P marker -- if check_m2.py has been "
            "widened to compare P markers too, update this test and test-results.md\n" + stdout
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# R10 -- catches a DUPLICATED checklist row, not just a missing one (the
# check's own stated rule is "exactly once", not just "at least once").
# ---------------------------------------------------------------------------

def test_r10_catches_duplicated_d_row():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, README_REL)
        src = read_text(path)
        m = re.search(r"^\|\s*D3\s*\|.*$", src, re.MULTILINE)
        assert m, "test fixture assumption broken: no D3 row found"
        d3_row = m.group(0)
        mutated = src[:m.end()] + "\n" + d3_row + src[m.end():]
        assert mutated != src
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert statuses.get("R10") is False, (
            "R10 did not catch a duplicated D3 checklist row (the check claims 'exactly once')\n" + stdout
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# R11 -- catches the corresponding README-side number going missing, not
# just the reader.lua-side constant.
# ---------------------------------------------------------------------------

def test_r11_catches_readme_missing_a_zone_number():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, README_REL)
        src = read_text(path)
        assert "0.10" in src
        mutated = src.replace("0.10", "0.1x", 1)
        assert mutated != src
        write_text(path, mutated)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert statuses.get("R11") is False, (
            "R11 did not catch '0.10' disappearing from README.md while reader.lua kept its constant\n" + stdout
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# R12 -- also catches os.remove/os.rename/io.write, not just io.open.
# ---------------------------------------------------------------------------

def test_r12_catches_os_remove_and_os_rename_and_io_write():
    for forbidden_call in ("os.remove(\"x\")", "os.rename(\"x\", \"y\")", "io.write(\"x\")"):
        tmp, dst = make_mutant_copy()
        try:
            path = os.path.join(dst, READER_REL)
            src = read_text(path)
            mutated = src + "\n-- test mutation\nlocal function _t() return %s end\n" % forbidden_call
            write_text(path, mutated)
            code, statuses, stdout = run_checker(dst)
            assert code == 1, stdout
            assert statuses.get("R12") is False, (
                "R12 did not catch %r added to reader.lua\n%s" % (forbidden_call, stdout)
            )
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
