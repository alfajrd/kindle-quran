#!/usr/bin/env python3
"""Milestone-2 repo-level checks, plus the whole-gate aggregator.

    python tools/check_m2.py [--root <repo root>]

Runs its own R-checks (R1-R12 -- static, structural checks over the reader
artefact itself: file existence, Lua parseability, the two fenced blocks
that keep TextBoxWidget-internals access and pack-text handling confined
and honest, the MUST-VERIFY registry cross-check, typography constants,
_meta.lua's version, the STEP-marker sync between reader.lua and
paging_model.py, README's on-device checklist, and the io.*/os.* ban), then
shells out to `tools/check_m1.py` (which itself nests `check_m0.py` and
`verify_pack.py`) and folds its output and exit code in under a banner.
This is the single command for the whole M2 gate.

Pattern follows `tools/check_m1.py`: `record()`/`check_boolean()`
accumulation, never short-circuiting, `PASS/FAIL <id> <message>` lines, a
final `RESULT:` line, stdlib + luaparser, no network, no Lua execution.

This script proves the artefact is well-formed, the fences hold, the
documented MUST-VERIFY list matches the code, and (via
`tools/paging_model.py`, run separately) the paging *arithmetic* is sound
over real ayah lengths. It proves NOTHING about whether TextBoxWidget
behaves as claimed, whether the rules land in register, or whether
anything renders at all on a real device -- that is the on-device
checklist in README.md (D1-D12).
"""
import argparse
import os
import re
import subprocess
import sys

try:
    from luaparser import ast as lua_ast
    from luaparser import astnodes as lua_astnodes
except ImportError:
    lua_ast = None
    lua_astnodes = None

CHECKS = []


def record(check_id, passed, message):
    CHECKS.append((check_id, passed, message))


def check_boolean(check_id, condition, ok_desc, fail_reason):
    if condition:
        record(check_id, True, ok_desc)
    else:
        record(check_id, False, fail_reason)


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def strip_lua_comments(src):
    """Blanks Lua comments, preserving offsets and line structure.

    R3 and R7 used to scan raw file text, so a commented-out require
    satisfied R3 and a stale number left in a comment satisfied R7 -- both
    found by mutation testing. Scanning code only closes that. Comments
    become spaces rather than being deleted, so any offset reported against
    the stripped text still lines up with the original file.

    Handles --[[ long ]] and --[==[ long ]==] comments, -- line comments,
    and skips string literals so a "--" inside a string is not mistaken for
    the start of a comment.
    """
    out = list(src)
    i, n = 0, len(src)

    def blank(a, b):
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = src[i]
        if c == '"' or c == "'":
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == c or src[j] == "\n":
                    break
                j += 1
            i = j + 1
            continue
        if c == "[":
            m = re.match(r"\[(=*)\[", src[i:])
            if m:
                close = "]" + m.group(1) + "]"
                j = src.find(close, i + len(m.group(0)))
                i = n if j == -1 else j + len(close)
                continue
        if src.startswith("--", i):
            m = re.match(r"--\[(=*)\[", src[i:])
            if m:
                close = "]" + m.group(1) + "]"
                j = src.find(close, i + len(m.group(0)))
                end = n if j == -1 else j + len(close)
            else:
                j = src.find("\n", i)
                end = n if j == -1 else j
            blank(i, end)
            i = end
            continue
        i += 1
    return "".join(out)


def read_text(path):
    return read_bytes(path).decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# R1 -- every M2 "Create"/"Modify" file exists.
# ---------------------------------------------------------------------------

M2_CREATE_FILES = [
    os.path.join("quran.koplugin", "quranreader.lua"),
    os.path.join("quran.koplugin", "quransettings.lua"),
    os.path.join("tools", "check_m2.py"),
    os.path.join("tools", "paging_model.py"),
    os.path.join("tests", "test_check_m2.py"),
    os.path.join("tests", "test_paging_model.py"),
    os.path.join("docs", "VERIFY-M2.md"),
]

M2_MODIFY_FILES = [
    os.path.join("quran.koplugin", "main.lua"),
    os.path.join("quran.koplugin", "db.lua"),
    os.path.join("quran.koplugin", "_meta.lua"),
    os.path.join("tools", "check_m0.py"),
    "README.md",
    os.path.join("docs", "BUILD.md"),
]


def check_r1(root):
    missing = []
    for rel in M2_CREATE_FILES + M2_MODIFY_FILES:
        if not os.path.isfile(os.path.join(root, rel)):
            missing.append(rel)
    check_boolean("R1", not missing,
                   "every M2 \"Create\"/\"Modify\" file exists",
                   "missing file(s): " + ", ".join(missing))


# ---------------------------------------------------------------------------
# R2 -- every .lua under quran.koplugin/ parses, last statement is Return.
# ---------------------------------------------------------------------------

def parse_lua(path):
    if lua_ast is None:
        return None, "luaparser is not installed"
    try:
        src = read_text(path)
    except OSError as exc:
        return None, str(exc)
    try:
        tree = lua_ast.parse(src)
    except Exception as exc:
        return None, str(exc)
    return tree, None


def check_r2(root):
    koplugin_dir = os.path.join(root, "quran.koplugin")
    if not os.path.isdir(koplugin_dir):
        record("R2", False, "quran.koplugin/ does not exist")
        return
    reasons = []
    lua_files = sorted(name for name in os.listdir(koplugin_dir) if name.endswith(".lua"))
    if not lua_files:
        reasons.append("no .lua files found under quran.koplugin/")
    for name in lua_files:
        path = os.path.join(koplugin_dir, name)
        tree, err = parse_lua(path)
        if tree is None:
            reasons.append("%s failed to parse: %s" % (name, err))
            continue
        try:
            body = tree.body.body
        except AttributeError:
            reasons.append("%s: could not read top-level statement list" % name)
            continue
        if not body:
            reasons.append("%s has no statements" % name)
            continue
        last = body[-1]
        is_return = lua_astnodes is not None and isinstance(last, lua_astnodes.Return)
        if not is_return:
            reasons.append("%s's last statement is %s, not Return" % (name, type(last).__name__))
    check_boolean("R2", not reasons,
                   "every .lua under quran.koplugin/ parses and ends with a Return (%d file(s) checked)" % len(lua_files),
                   "; ".join(reasons))


# ---------------------------------------------------------------------------
# R3 -- reader.lua requires ui/widget/textboxwidget.
# ---------------------------------------------------------------------------

def check_r3(root):
    path = os.path.join(root, "quran.koplugin", "quranreader.lua")
    if not os.path.isfile(path):
        record("R3", False, "reader.lua does not exist")
        return
    src = strip_lua_comments(read_text(path))
    check_boolean("R3", 'require("ui/widget/textboxwidget")' in src,
                   "reader.lua contains require(\"ui/widget/textboxwidget\")",
                   "require(\"ui/widget/textboxwidget\") not found in quranreader.lua")


# ---------------------------------------------------------------------------
# R4 -- BEGIN/END TEXTBOX INTERNALS fence; line_height_px,
# vertical_string_list, lines_per_page confined to it.
# ---------------------------------------------------------------------------

TEXTBOX_BEGIN = "-- BEGIN TEXTBOX INTERNALS"
TEXTBOX_END = "-- END TEXTBOX INTERNALS"
TEXTBOX_INTERNAL_IDS = ("line_height_px", "vertical_string_list", "lines_per_page")

LONG_COMMENT_OPEN_RE = re.compile(r"--\[(=*)\[")


def blank_lua_comments(src):
    """Replaces every Lua comment's content (both `--` line comments and
    `--[[ ... ]]` / `--[=[ ... ]=]` long comments) with spaces, preserving
    every newline so line/column positions of non-comment text are
    unchanged. Used only to decide "is this identifier occurrence inside a
    comment", never to alter a file on disk."""
    out = []
    i = 0
    n = len(src)
    while i < n:
        if src[i:i + 2] == "--":
            m = LONG_COMMENT_OPEN_RE.match(src, i)
            if m:
                eq = m.group(1)
                close = "]" + eq + "]"
                end = src.find(close, m.end())
                end = n if end == -1 else end + len(close)
                segment = src[i:end]
                out.append("".join(ch if ch == "\n" else " " for ch in segment))
                i = end
                continue
            end = src.find("\n", i)
            end = n if end == -1 else end
            out.append(" " * (end - i))
            i = end
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def check_r4(root):
    path = os.path.join(root, "quran.koplugin", "quranreader.lua")
    if not os.path.isfile(path):
        record("R4", False, "reader.lua does not exist")
        return
    src = read_text(path)
    reasons = []

    begin_count = len(re.findall(re.escape(TEXTBOX_BEGIN), src))
    end_count = len(re.findall(re.escape(TEXTBOX_END), src))
    if begin_count != 1 or end_count != 1:
        reasons.append("BEGIN marker appears %d time(s), END marker appears %d time(s) (expected 1 each)" % (
            begin_count, end_count))
        check_boolean("R4", not reasons,
                       "TEXTBOX INTERNALS fence present once each, identifiers confined to it",
                       "; ".join(reasons))
        return

    begin_idx = src.index(TEXTBOX_BEGIN)
    end_idx = src.index(TEXTBOX_END)
    if begin_idx >= end_idx:
        reasons.append("BEGIN marker does not appear before END marker")
        check_boolean("R4", not reasons,
                       "TEXTBOX INTERNALS fence present once each, identifiers confined to it",
                       "; ".join(reasons))
        return

    outside = src[:begin_idx] + src[end_idx + len(TEXTBOX_END):]
    # Comments (line comments and `--[[ ]]` block comments, including the
    # module header) are prose *about* the identifier, not code that
    # touches TextBoxWidget internals -- same precedent as check_m1.py's
    # C6 (PIN_2_255 outside its verbatim block, comment lines excluded).
    outside_code_only = blank_lua_comments(outside)
    offending = []
    for ident in TEXTBOX_INTERNAL_IDS:
        if re.search(r"\b%s\b" % re.escape(ident), outside_code_only):
            offending.append(ident)

    if offending:
        reasons.append("identifier(s) found outside the fence, in non-comment code: " + ", ".join(offending))

    check_boolean("R4", not reasons,
                   "TEXTBOX INTERNALS fence present once each, identifiers confined to it",
                   "; ".join(reasons))


# ---------------------------------------------------------------------------
# R5 -- BEGIN/END VERBATIM CONCAT fence; no string-library call inside.
# ---------------------------------------------------------------------------

CONCAT_BEGIN = "-- BEGIN VERBATIM CONCAT"
CONCAT_END = "-- END VERBATIM CONCAT"
# Literal substrings (not regex) -- "string%." is the spec's own Lua-pattern
# spelling of "string." (the dot escaped for Lua's pattern matching, which
# check_m2.py does not use); matched here as a plain literal substring.
FORBIDDEN_STRING_CALLS = ("string.", ":gsub(", ":sub(", ":rep(", ":upper(", ":lower(", ":gmatch(", ":find(", ":match(")


def check_r5(root):
    path = os.path.join(root, "quran.koplugin", "quranreader.lua")
    if not os.path.isfile(path):
        record("R5", False, "reader.lua does not exist")
        return
    src = read_text(path)
    reasons = []

    begin_count = len(re.findall(re.escape(CONCAT_BEGIN), src))
    end_count = len(re.findall(re.escape(CONCAT_END), src))
    if begin_count != 1 or end_count != 1:
        reasons.append("BEGIN marker appears %d time(s), END marker appears %d time(s) (expected 1 each)" % (
            begin_count, end_count))
        check_boolean("R5", not reasons,
                       "VERBATIM CONCAT fence present once each, no string-library call inside",
                       "; ".join(reasons))
        return

    begin_idx = src.index(CONCAT_BEGIN)
    end_idx = src.index(CONCAT_END)
    if begin_idx >= end_idx:
        reasons.append("BEGIN marker does not appear before END marker")
        check_boolean("R5", not reasons,
                       "VERBATIM CONCAT fence present once each, no string-library call inside",
                       "; ".join(reasons))
        return

    between = src[begin_idx + len(CONCAT_BEGIN):end_idx]
    offenders = [pat for pat in FORBIDDEN_STRING_CALLS if pat in between]
    if offenders:
        reasons.append("forbidden pattern(s) found inside the fence: " + ", ".join(offenders))

    check_boolean("R5", not reasons,
                   "VERBATIM CONCAT fence present once each, no string-library call inside",
                   "; ".join(reasons))


# ---------------------------------------------------------------------------
# R6 -- MUST-VERIFY V<n> ids in quranreader.lua/settings.lua/db.lua == the ids
# documented in docs/VERIFY-M2.md.
#
# Scoped to n >= 20: numbering "continues from M0/M1's V1-V16" (spec.md
# §9), and docs/VERIFY-M2.md is M2's own registry (V20-V36) -- it does not
# re-document db.lua's pre-existing M1 ids (e.g. its "MUST-VERIFY V11-V14"
# header), which are already covered by M1's own record. Restricting the
# comparison to M2's own id range is what lets this check hold for
# db.lua's *unmodified* M1 content as well as the two new M2 files.
# ---------------------------------------------------------------------------

MUST_VERIFY_RE = re.compile(r"MUST-VERIFY\s+V(\d+)")
DOC_ROW_RE = re.compile(r"\bV(\d+)\b")


def extract_code_v_ids(src):
    ids = set()
    for m in MUST_VERIFY_RE.finditer(src):
        n = int(m.group(1))
        if n >= 20:
            ids.add(n)
    return ids


def extract_doc_v_ids(doc_src):
    ids = set()
    for line in doc_src.splitlines():
        m = DOC_ROW_RE.search(line)
        if not m:
            continue
        n = int(m.group(1))
        if n < 20:
            continue
        has_source_path = ("frontend/" in line) or ("ffi/" in line)
        if has_source_path:
            ids.add(n)
    return ids


def check_r6(root):
    paths = {
        "reader.lua": os.path.join(root, "quran.koplugin", "quranreader.lua"),
        "settings.lua": os.path.join(root, "quran.koplugin", "quransettings.lua"),
        "db.lua": os.path.join(root, "quran.koplugin", "db.lua"),
    }
    doc_path = os.path.join(root, "docs", "VERIFY-M2.md")

    missing = [name for name, p in paths.items() if not os.path.isfile(p)]
    if not os.path.isfile(doc_path):
        missing.append("docs/VERIFY-M2.md")
    if missing:
        record("R6", False, "missing file(s): " + ", ".join(missing))
        return

    code_ids = set()
    for p in paths.values():
        code_ids |= extract_code_v_ids(read_text(p))

    doc_ids = extract_doc_v_ids(read_text(doc_path))

    undocumented = sorted(code_ids - doc_ids)
    stale = sorted(doc_ids - code_ids)
    reasons = []
    if undocumented:
        reasons.append("undocumented id(s) (in code, not in docs/VERIFY-M2.md with a source path): " +
                        ", ".join("V%d" % n for n in undocumented))
    if stale:
        reasons.append("stale doc entry/entries (in docs/VERIFY-M2.md, not referenced by any MUST-VERIFY comment): " +
                        ", ".join("V%d" % n for n in stale))

    check_boolean("R6", not reasons,
                   "MUST-VERIFY V20+ ids in quranreader.lua/settings.lua/db.lua exactly match docs/VERIFY-M2.md (%d id(s))" % len(code_ids),
                   "; ".join(reasons))


# ---------------------------------------------------------------------------
# R7 -- settings.lua declares exactly §6.6's typography numbers.
# ---------------------------------------------------------------------------

EXPECTED_TYPOGRAPHY_NUMBERS = ["34", "26", "60", "2", "1.5", "0.7", "2.0", "0.1"]


def check_r7(root):
    path = os.path.join(root, "quran.koplugin", "quransettings.lua")
    if not os.path.isfile(path):
        record("R7", False, "settings.lua does not exist")
        return
    src = strip_lua_comments(read_text(path))
    missing = []
    for number in EXPECTED_TYPOGRAPHY_NUMBERS:
        if not re.search(r"(?<![0-9.])%s(?![0-9.])" % re.escape(number), src):
            missing.append(number)
    check_boolean("R7", not missing,
                   "settings.lua declares every §6.6 typography number: " + ", ".join(EXPECTED_TYPOGRAPHY_NUMBERS),
                   "missing number(s): " + ", ".join(missing))


# ---------------------------------------------------------------------------
# R8 -- _meta.lua version and description.
# ---------------------------------------------------------------------------

def check_r8(root):
    path = os.path.join(root, "quran.koplugin", "_meta.lua")
    if not os.path.isfile(path):
        record("R8", False, "_meta.lua does not exist")
        return
    src = read_text(path)
    has_version = 'version = "0.3.0-m2"' in src
    has_desc = "Milestone 2" in src
    check_boolean("R8", has_version and has_desc,
                   "_meta.lua has version = \"0.3.0-m2\" and description contains \"Milestone 2\"",
                   "has_version=%r has_desc=%r" % (has_version, has_desc))


# ---------------------------------------------------------------------------
# R9 -- STEP marker sync between reader.lua and paging_model.py.
#
# Scoped to the W-prefixed (arithmetic) steps: spec.md §6.2 states R9's
# purpose explicitly -- "so check_m2.py can verify that paging_model.py
# mirrors [W1/W2/W3]". reader.lua's rendering steps (P1-P6, §6.4) have no
# counterpart in paging_model.py (a pure arithmetic model that does no
# rendering) and are out of R9's stated scope.
# ---------------------------------------------------------------------------

def check_r9(root):
    reader_path = os.path.join(root, "quran.koplugin", "quranreader.lua")
    model_path = os.path.join(root, "tools", "paging_model.py")
    if not os.path.isfile(reader_path) or not os.path.isfile(model_path):
        record("R9", False, "reader.lua or tools/paging_model.py does not exist")
        return

    reader_src = read_text(reader_path)
    model_src = read_text(model_path)

    reader_steps = re.findall(r"--\s*STEP\s+(W\d+)", reader_src)
    model_steps = re.findall(r"#\s*STEP\s+(W\d+)", model_src)

    check_boolean("R9", reader_steps == model_steps and bool(reader_steps),
                   "reader.lua's STEP W markers %r match paging_model.py's %r" % (reader_steps, model_steps),
                   "reader.lua STEP W markers %r != paging_model.py STEP W markers %r" % (reader_steps, model_steps))


# ---------------------------------------------------------------------------
# R10 -- README's M2 on-device checklist heading and D1-D12.
# ---------------------------------------------------------------------------

README_HEADING = "## Milestone 2 — on-device checklist"


def check_r10(root):
    path = os.path.join(root, "README.md")
    if not os.path.isfile(path):
        record("R10", False, "README.md does not exist")
        return
    src = read_text(path)
    if README_HEADING not in src:
        record("R10", False, "README.md does not contain the heading %r" % README_HEADING)
        return
    section = src[src.index(README_HEADING) + len(README_HEADING):]
    # Stop at the next '## ' heading, if any, so ids from later sections
    # don't count.
    next_heading = re.search(r"\n## ", section)
    if next_heading:
        section = section[:next_heading.start()]

    # Counted as *checklist table rows* ("| D<n> | ..."), not as every
    # prose mention -- the section's own diagnostic prose (telling a
    # paging bug from a rendering bug from a position-memory bug)
    # legitimately references some ids again by name.
    table_row_ids = re.findall(r"^\|\s*(D\d+)\s*\|", section, re.MULTILINE)

    reasons = []
    for i in range(1, 13):
        did = "D%d" % i
        count = table_row_ids.count(did)
        if count != 1:
            reasons.append("%s appears as a checklist table row %d time(s) (expected exactly 1)" % (did, count))
    check_boolean("R10", not reasons,
                   "README.md's M2 checklist table contains each of D1..D12 exactly once as a row",
                   "; ".join(reasons))


# ---------------------------------------------------------------------------
# R11 -- touch-zone numbers as named constants in quranreader.lua, and present
# in README's checklist section.
# ---------------------------------------------------------------------------

TOUCH_ZONE_NUMBERS = ["0.25", "0.75", "0.10", "0.5"]


def check_r11(root):
    reader_path = os.path.join(root, "quran.koplugin", "quranreader.lua")
    readme_path = os.path.join(root, "README.md")
    if not os.path.isfile(reader_path) or not os.path.isfile(readme_path):
        record("R11", False, "reader.lua or README.md does not exist")
        return
    reader_src = read_text(reader_path)
    readme_src = read_text(readme_path)

    reasons = []
    for number in TOUCH_ZONE_NUMBERS:
        if not re.search(r"local\s+\w+\s*=\s*%s\b" % re.escape(number), reader_src):
            reasons.append("%s not found as a named constant (local NAME = %s) in quranreader.lua" % (number, number))
    for number in TOUCH_ZONE_NUMBERS:
        if number not in readme_src:
            reasons.append("%s not found anywhere in README.md" % number)

    check_boolean("R11", not reasons,
                   "touch-zone numbers 0.25/0.75/0.10/0.5 are named constants in quranreader.lua and appear in README.md",
                   "; ".join(reasons))


# ---------------------------------------------------------------------------
# R12 -- no io.open/io.write/os.remove/os.rename in quranreader.lua or settings.lua.
# ---------------------------------------------------------------------------

FORBIDDEN_IO_CALLS = ("io.open", "io.write", "os.remove", "os.rename")


def check_r12(root):
    reasons = []
    for name in ("quranreader.lua", "quransettings.lua"):
        path = os.path.join(root, "quran.koplugin", name)
        if not os.path.isfile(path):
            reasons.append("%s does not exist" % name)
            continue
        src = read_text(path)
        found = [call for call in FORBIDDEN_IO_CALLS if call in src]
        if found:
            reasons.append("%s contains: %s" % (name, ", ".join(found)))
    check_boolean("R12", not reasons,
                   "neither quranreader.lua nor quransettings.lua contains io.open/io.write/os.remove/os.rename",
                   "; ".join(reasons))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def run_subprocess(args):
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout + proc.stderr


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    default_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument("--root", default=default_root, help="path to kindle-quran/ (default: %(default)s)")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    root = os.path.abspath(args.root)

    check_r1(root)
    check_r2(root)
    check_r3(root)
    check_r4(root)
    check_r5(root)
    check_r6(root)
    check_r7(root)
    check_r8(root)
    check_r9(root)
    check_r10(root)
    check_r11(root)
    check_r12(root)

    failed = 0
    for check_id, passed, message in CHECKS:
        if passed:
            print("PASS  %s  %s" % (check_id, message))
        else:
            failed += 1
            print("FAIL  %s  %s" % (check_id, message))

    r_total = len(CHECKS)
    r_result_ok = failed == 0
    if r_result_ok:
        print("RESULT: PASS (%d checks)" % r_total)
    else:
        print("RESULT: FAIL (%d of %d failed)" % (failed, r_total))

    check_m1_path = os.path.join(root, "tools", "check_m1.py")
    print("")
    print("=== tools/check_m1.py --root %s ===" % root)
    m1_code, m1_out = run_subprocess([sys.executable, check_m1_path, "--root", root])
    print(m1_out.rstrip("\n"))

    overall_ok = r_result_ok and (m1_code == 0)
    print("")
    if overall_ok:
        print("check_m2.py OVERALL: PASS")
        return 0
    else:
        print("check_m2.py OVERALL: FAIL (R-checks: %s, check_m1.py: %s)" % (
            "PASS" if r_result_ok else "FAIL",
            "PASS" if m1_code == 0 else "FAIL",
        ))
        return 1


if __name__ == "__main__":
    sys.exit(main())
