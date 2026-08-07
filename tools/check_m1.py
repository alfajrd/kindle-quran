#!/usr/bin/env python3
"""Milestone-1 repo-level checks, plus the whole-gate aggregator.

    python tools/check_m1.py [--root <repo root>]

Runs its own C-checks (repo-structure / provenance-consistency checks that
are neither "does the pack's content match the corpus" -- that's
`verify_pack.py` -- nor "is M0's artefact still well-formed" -- that's
`check_m0.py`), then shells out to both of those and folds their output and
exit codes in under a banner. This is the single command for the whole M1
gate: exit 0 only if all three (C-checks, check_m0.py, verify_pack.py) are
clean.

Pattern follows `tools/check_m0.py`: `record()`/`check_boolean()`
accumulation, never short-circuiting, `PASS/FAIL <id> <message>` lines, a
final `RESULT:` line, stdlib-only, no network.

This script proves the repository is internally consistent and that the
pack's content matches the verified corpus. It does NOT prove Tanzil
provenance by itself -- see `data/SOURCE.md` and `docs/BUILD.md`.
"""
import argparse
import hashlib
import json
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

# The vendored file's digest, exactly as Tanzil shipped it (byte-exact,
# including its trailing blank-line-plus-'#'-comment copyright block).
EXPECTED_CORPUS_SHA256 = "18c719bb3ba26d32ef457f40dad77cd28c4c5a34156833e26a8e5fcfdd246fb1"
EXPECTED_SURAH_COUNT = 114
EXPECTED_AYAH_COUNT = 6236
EXPECTED_SAJDAH_COUNT = 15

# The pattern C4 rejects: an actual call to unicodedata's normalize
# function, module-dotted-name followed immediately (whitespace aside) by
# an opening parenthesis. Kept as a single named constant, defined once
# here, so no other part of this file (including its own comments) has to
# spell the call pattern out where C4's own scan of tools/*.py would see it.
NORMALIZE_CALL_RE = re.compile(r"unicodedata\s*\.\s*normalize\s*\(")

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


FILES_TO_CREATE = [
    os.path.join("data", "quran-uthmani.txt"),
    os.path.join("data", "quran-uthmani.sha256"),
    os.path.join("data", "surah_meta.json"),
    os.path.join("data", "surah_meta.sha256"),
    os.path.join("data", "SOURCE.md"),
    os.path.join("data", "errata.tsv"),
    os.path.join("docs", "ERRATA.md"),
    os.path.join("tools", "import_corpus.py"),
    os.path.join("tools", "build_pack.py"),
    os.path.join("tools", "verify_pack.py"),
    os.path.join("tools", "check_m1.py"),
    os.path.join("tests", "test_check_m1.py"),
    os.path.join("quran.koplugin", "db.lua"),
    os.path.join("quran.koplugin", "data", "quran.db"),
    os.path.join("quran.koplugin", "data", "quran.db.sha256"),
    os.path.join("quran.koplugin", "data", "manifest.json"),
    os.path.join("docs", "BUILD.md"),
]


def check_c1(root):
    missing = [rel for rel in FILES_TO_CREATE if not os.path.isfile(os.path.join(root, rel))]
    check_boolean("C1", not missing,
                   "every file in \"Files to create\" exists",
                   "missing file(s): " + ", ".join(missing))


def check_c2(root):
    txt_path = os.path.join(root, "data", "quran-uthmani.txt")
    sha_path = os.path.join(root, "data", "quran-uthmani.sha256")
    if not os.path.isfile(txt_path) or not os.path.isfile(sha_path):
        record("C2", False, "data/quran-uthmani.txt or data/quran-uthmani.sha256 missing")
        return
    digest = hashlib.sha256(read_bytes(txt_path)).hexdigest()
    stated = read_bytes(sha_path).decode("utf-8").split()[0].lower()
    ok = digest == EXPECTED_CORPUS_SHA256 and digest == stated
    check_boolean("C2", ok,
                   "sha256(data/quran-uthmani.txt) == pin and matches data/quran-uthmani.sha256",
                   "digest=%s expected=%s file_says=%s" % (digest, EXPECTED_CORPUS_SHA256, stated))


def check_c3(root):
    # Tanzil's own download format is exactly EXPECTED_AYAH_COUNT
    # "surah|ayah|text" lines, followed by a trailer of blank lines and
    # lines starting with '#' (Tanzil's copyright/terms-of-use block). The
    # previous, mirror-sourced vendored file had no such trailer; the real
    # Tanzil download always does, so this check tolerates -- and validates
    # -- that trailer instead of rejecting it. See docs/BUILD.md.
    txt_path = os.path.join(root, "data", "quran-uthmani.txt")
    if not os.path.isfile(txt_path):
        record("C3", False, "data/quran-uthmani.txt does not exist")
        return
    raw = read_bytes(txt_path)
    reasons = []
    if raw[:3] == b"\xef\xbb\xbf":
        reasons.append("starts with a UTF-8 BOM")
    if b"\r" in raw:
        reasons.append("contains a \\r byte")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        record("C3", False, "does not decode as UTF-8: %s" % exc)
        return
    if not text.endswith("\n"):
        reasons.append("does not end with a trailing \\n")
    body = text[:-1] if text.endswith("\n") else text
    lines = body.split("\n")
    if len(lines) < EXPECTED_AYAH_COUNT:
        reasons.append("has %d line(s), fewer than the expected %d ayah lines" % (
            len(lines), EXPECTED_AYAH_COUNT))
        check_boolean("C3", not reasons,
                       "corpus file is well-formed: %d ayah lines, ascending (surah, ayah), "
                       "no CR/BOM/blank lines among them, trailer (if any) is blank/'#' only" % EXPECTED_AYAH_COUNT,
                       "; ".join(reasons))
        return

    ayah_lines = lines[:EXPECTED_AYAH_COUNT]
    trailer_lines = lines[EXPECTED_AYAH_COUNT:]
    for i, line in enumerate(trailer_lines):
        if line != "" and not line.startswith("#"):
            reasons.append("trailer line %d is neither blank nor a '#' comment: %r" % (
                EXPECTED_AYAH_COUNT + i + 1, line[:40]))

    prev = None
    for i, line in enumerate(ayah_lines):
        if line == "":
            reasons.append("line %d is blank" % (i + 1))
            continue
        parts = line.split("|", 2)
        if len(parts) != 3:
            reasons.append("line %d is not int|int|text: %r" % (i + 1, line[:40]))
            continue
        s_str, a_str, ayah_text = parts
        try:
            s, a = int(s_str), int(a_str)
        except ValueError:
            reasons.append("line %d: surah/ayah not integers" % (i + 1))
            continue
        if "|" in ayah_text:
            reasons.append("line %d: text contains '|'" % (i + 1))
        if prev is not None and (s, a) <= prev:
            reasons.append("line %d: not ascending (surah, ayah)" % (i + 1))
        prev = (s, a)
    check_boolean("C3", not reasons,
                   "corpus file is well-formed: %d ayah lines, ascending (surah, ayah), "
                   "no CR/BOM/blank lines among them, trailer (if any) is blank/'#' only" % EXPECTED_AYAH_COUNT,
                   "; ".join(reasons))


def check_c4(root):
    tools_dir = os.path.join(root, "tools")
    offenders = []
    if os.path.isdir(tools_dir):
        for name in os.listdir(tools_dir):
            if not name.endswith(".py"):
                continue
            path = os.path.join(tools_dir, name)
            src = read_bytes(path).decode("utf-8", errors="replace")
            # A genuine call -- the normalize function of the unicodedata
            # module, invoked with an opening parenthesis -- not the bare
            # phrase that several of these files' own docstrings/comments
            # use, deliberately, to warn a future editor away from calling
            # it. Requiring the open-paren tells the two apart. (This
            # comment deliberately does not spell out the call pattern
            # itself, for the same reason -- see NORMALIZE_CALL_RE below.)
            if NORMALIZE_CALL_RE.search(src):
                offenders.append(os.path.join("tools", name))
    check_boolean("C4", not offenders,
                   "no unicodedata.normalize anywhere under tools/",
                   "found in: " + ", ".join(offenders))


def parse_lua(path):
    if lua_ast is None:
        return None, "luaparser is not installed"
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
    except OSError as exc:
        return None, str(exc)
    try:
        tree = lua_ast.parse(src)
    except Exception as exc:
        return None, str(exc)
    return tree, None


def check_c5(root):
    db_lua_path = os.path.join(root, "quran.koplugin", "db.lua")
    if not os.path.isfile(db_lua_path):
        record("C5", False, "quran.koplugin/db.lua does not exist")
        return
    tree, err = parse_lua(db_lua_path)
    if tree is None:
        record("C5", False, "db.lua failed to parse: %s" % err)
        return
    try:
        body = tree.body.body
    except AttributeError:
        record("C5", False, "could not read db.lua's top-level statement list")
        return
    if not body:
        record("C5", False, "db.lua has no statements")
        return
    last = body[-1]
    is_return = lua_astnodes is not None and isinstance(last, lua_astnodes.Return)
    check_boolean("C5", is_return,
                   "quran.koplugin/db.lua parses with luaparser and its last statement is a return",
                   "db.lua's last statement is %s, not Return" % type(last).__name__)


def check_c6(root):
    main_path = os.path.join(root, "quran.koplugin", "main.lua")
    if not os.path.isfile(main_path):
        record("C6", False, "main.lua does not exist")
        return
    src = read_bytes(main_path).decode("utf-8", errors="replace")

    # Matches the Lua table-field assignment `text = ... PIN_2_255` (an
    # InfoMessage's `text` field being fed the pin directly), but not a
    # comparison like `pin_text == PIN_2_255` -- the negative lookbehind
    # keeps "text" from matching as a suffix of "pin_text", and `=(?!=)`
    # keeps a single "=" from matching the "=" inside "==".
    display_pattern = re.compile(r"(?<![A-Za-z0-9_])text\s*=(?!=)\s*.*PIN_2_255")
    code_lines = [line for line in src.splitlines() if not line.strip().startswith("--")]
    display_offenders = [line for line in code_lines if display_pattern.search(line)]

    begin_marker = "-- BEGIN VERBATIM TANZIL UTHMANI 2:255 -- DO NOT EDIT, DO NOT NORMALISE, DO NOT REFLOW"
    end_marker = "-- END VERBATIM"
    reasons = []
    if display_offenders:
        reasons.append("PIN_2_255 appears in a text=... assignment: %r" % display_offenders)

    begin_idx = src.find(begin_marker)
    end_idx = src.find(end_marker)
    if begin_idx == -1 or end_idx == -1 or begin_idx >= end_idx:
        reasons.append("could not locate the BEGIN/END VERBATIM block")
        check_boolean("C6", not reasons,
                       "main.lua never displays the pin; PIN_2_255 appears only in the verbatim block and the comparison",
                       "; ".join(reasons))
        return

    outside_block = src[:begin_idx] + src[end_idx + len(end_marker):]
    lines_outside = outside_block.splitlines()

    # "The comparison" is read as the whole `if ... PIN_2_255 ... then
    # ... end` block, not just the single line carrying the `==`/`~=` --
    # the spec-mandated behaviour ("show ... plus both lengths in bytes",
    # main.lua's showTestAyah step 3) legitimately references PIN_2_255
    # again a few lines later, inside that same block, to report its byte
    # length. That is not "displaying the pin" (its Arabic text never
    # appears; only an integer does), so it is allowed there.
    in_comparison_block = [False] * len(lines_outside)
    depth = 0
    in_block = False
    for i, line in enumerate(lines_outside):
        stripped = line.strip()
        if not in_block and re.search(r"(==|~=)\s*PIN_2_255\b", line):
            in_block = True
            depth = 0
        if in_block:
            in_comparison_block[i] = True
            # Cheap block-depth tracker: count opening keywords vs "end".
            # Sufficient for this file's simple, non-nested comparison
            # block; not a general Lua parser.
            opens = len(re.findall(r"\b(if|for|while|function|do)\b", stripped))
            # "end" that closes an inline "then ... end" on one line, or
            # the block's own closing "end".
            closes = len(re.findall(r"\bend\b", stripped))
            depth += opens - closes
            if depth <= 0:
                in_block = False

    # Comments (prose explaining PIN_2_255's role, e.g. the D5 note above)
    # are not "the identifier appearing" in the code-usage sense this check
    # is about -- they document behaviour, they do not implement it.
    bad_outside = []
    for i, line in enumerate(lines_outside):
        if line.strip().startswith("--"):
            continue
        if "PIN_2_255" in line and not display_pattern.search(line) and not in_comparison_block[i]:
            bad_outside.append(line)
    if bad_outside:
        reasons.append("PIN_2_255 used outside the verbatim block and outside the comparison: %r" % bad_outside)

    check_boolean("C6", not reasons,
                   "main.lua never displays the pin; PIN_2_255 appears only in the verbatim block and the comparison",
                   "; ".join(reasons))


def check_c7(root):
    path = os.path.join(root, ".gitattributes")
    if not os.path.isfile(path):
        record("C7", False, ".gitattributes does not exist")
        return
    src = read_bytes(path).decode("utf-8", errors="replace")
    required = [
        "data/quran-uthmani.txt binary",
        "quran.koplugin/data/quran.db binary",
        "data/surah_meta.json -text",
    ]
    missing = [line for line in required if line not in src]
    check_boolean("C7", not missing,
                   ".gitattributes contains the three required M1 lines",
                   "missing line(s): " + ", ".join(missing))


def check_c8(root):
    path = os.path.join(root, "THIRD-PARTY.md")
    if not os.path.isfile(path):
        record("C8", False, "THIRD-PARTY.md does not exist")
        return
    src = read_bytes(path).decode("utf-8", errors="replace")
    names_file = "data/quran-uthmani.txt" in src
    has_digest = EXPECTED_CORPUS_SHA256 in src
    check_boolean("C8", names_file and has_digest,
                   "THIRD-PARTY.md names data/quran-uthmani.txt and contains the corpus digest",
                   "names_file=%r has_digest=%r" % (names_file, has_digest))


def check_c9(root):
    manifest_path = os.path.join(root, "quran.koplugin", "data", "manifest.json")
    db_path = os.path.join(root, "quran.koplugin", "data", "quran.db")
    if not os.path.isfile(manifest_path):
        record("C9", False, "manifest.json does not exist")
        return
    try:
        manifest = json.loads(read_bytes(manifest_path).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        record("C9", False, "manifest.json is not valid JSON: %s" % exc)
        return
    required_keys = {
        "pack_id", "schema_version", "name", "language", "direction",
        "text_edition", "source_url", "attribution", "build_date",
        "surah_count", "ayah_count", "corpus_sha256", "db_sha256",
    }
    missing_keys = required_keys - set(manifest.keys())
    if missing_keys:
        record("C9", False, "manifest.json missing key(s): " + ", ".join(sorted(missing_keys)))
        return
    if not os.path.isfile(db_path):
        record("C9", False, "quran.db does not exist to cross-check manifest against")
        return
    import sqlite3
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % db_path.replace("\\", "/"), uri=True)
        meta_rows = dict(conn.execute("SELECT key, value FROM meta;").fetchall())
        conn.close()
    except sqlite3.Error as exc:
        record("C9", False, "could not read meta table from quran.db: %s" % exc)
        return
    mapping = {
        "pack_id": "pack_id", "schema_version": "schema_version", "name": "name",
        "language": "language", "direction": "direction", "text_edition": "text_edition",
        "source_url": "source_url", "attribution": "attribution", "build_date": "build_date",
        "surah_count": "surah_count", "ayah_count": "ayah_count", "corpus_sha256": "checksum",
    }
    mismatches = []
    for manifest_key, meta_key in mapping.items():
        manifest_value = str(manifest.get(manifest_key))
        meta_value = meta_rows.get(meta_key)
        if manifest_value != meta_value:
            mismatches.append("%s: manifest=%r meta.%s=%r" % (manifest_key, manifest_value, meta_key, meta_value))
    check_boolean("C9", not mismatches,
                   "manifest.json is valid JSON with every required key, and every shared value equals the db's meta row",
                   "; ".join(mismatches))


def check_c10(root):
    path = os.path.join(root, "data", "surah_meta.json")
    sha_path = os.path.join(root, "data", "surah_meta.sha256")
    if not os.path.isfile(path):
        record("C10", False, "data/surah_meta.json does not exist")
        return
    raw = read_bytes(path)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        record("C10", False, "data/surah_meta.json is not valid JSON: %s" % exc)
        return
    reasons = []
    surahs = data.get("surahs")
    if not isinstance(surahs, list) or len(surahs) != EXPECTED_SURAH_COUNT:
        reasons.append("surahs is not a %d-entry list" % EXPECTED_SURAH_COUNT)
    else:
        numbers = sorted(row.get("number") for row in surahs)
        if numbers != list(range(1, EXPECTED_SURAH_COUNT + 1)):
            reasons.append("surahs.number values are not exactly 1..%d" % EXPECTED_SURAH_COUNT)
        for row in surahs:
            for field in ("number", "name_ar", "name_en", "name_en_translation", "ayah_count", "revelation"):
                if row.get(field) in (None, ""):
                    reasons.append("surah %r missing/empty field %s" % (row.get("number"), field))

    sajdah = data.get("sajdah")
    if not isinstance(sajdah, list) or len(sajdah) != EXPECTED_SAJDAH_COUNT:
        reasons.append("sajdah is not a %d-entry list" % EXPECTED_SAJDAH_COUNT)
    else:
        for ref in sajdah:
            parts = ref.split(":")
            if len(parts) != 2 or not all(p.isdigit() for p in parts):
                reasons.append("sajdah ref %r does not parse as int:int" % (ref,))

    juz_start = data.get("juz_start")
    if not isinstance(juz_start, dict) or set(juz_start.keys()) != {str(i) for i in range(1, 31)}:
        reasons.append("juz_start does not have exactly the keys \"1\"..\"30\"")
    else:
        for ref in juz_start.values():
            parts = ref.split(":")
            if len(parts) != 2 or not all(p.isdigit() for p in parts):
                reasons.append("juz_start ref %r does not parse as int:int" % (ref,))

    if os.path.isfile(sha_path):
        digest = hashlib.sha256(raw).hexdigest()
        stated = read_bytes(sha_path).decode("utf-8").split()[0].lower()
        if digest != stated:
            reasons.append("sha256 mismatch: actual=%s stated=%s" % (digest, stated))
    else:
        reasons.append("data/surah_meta.sha256 does not exist")

    check_boolean("C10", not reasons,
                   "data/surah_meta.json is well-formed and its sha256 matches data/surah_meta.sha256",
                   "; ".join(reasons))


def check_c11(root):
    sha_path = os.path.join(root, "data", "quran-uthmani.sha256")
    build_pack_path = os.path.join(root, "tools", "build_pack.py")
    verify_pack_path = os.path.join(root, "tools", "verify_pack.py")
    check_m1_path = os.path.join(root, "tools", "check_m1.py")

    digests = {}
    if os.path.isfile(sha_path):
        digests["data/quran-uthmani.sha256"] = read_bytes(sha_path).decode("utf-8").split()[0].lower()
    for label, path in (
        ("build_pack.py", build_pack_path),
        ("verify_pack.py", verify_pack_path),
        ("check_m1.py", check_m1_path),
    ):
        if os.path.isfile(path):
            src = read_bytes(path).decode("utf-8", errors="replace")
            m = re.search(r'EXPECTED_CORPUS_SHA256\s*=\s*"([0-9a-fA-F]{64})"', src)
            if m:
                digests[label] = m.group(1).lower()
            else:
                digests[label] = None

    values = set(digests.values())
    ok = len(values) == 1 and None not in values
    check_boolean("C11", ok,
                   "the corpus digest is the identical string across build_pack.py, verify_pack.py, check_m1.py and data/quran-uthmani.sha256",
                   "digests found: %r" % (digests,))


def run_subprocess(args, cwd=None):
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

    check_c1(root)
    check_c2(root)
    check_c3(root)
    check_c4(root)
    check_c5(root)
    check_c6(root)
    check_c7(root)
    check_c8(root)
    check_c9(root)
    check_c10(root)
    check_c11(root)

    failed = 0
    for check_id, passed, message in CHECKS:
        if passed:
            print("PASS  %s  %s" % (check_id, message))
        else:
            failed += 1
            print("FAIL  %s  %s" % (check_id, message))

    c_total = len(CHECKS)
    c_result_ok = failed == 0
    if c_result_ok:
        print("RESULT: PASS (%d checks)" % c_total)
    else:
        print("RESULT: FAIL (%d of %d failed)" % (failed, c_total))

    check_m0_path = os.path.join(root, "tools", "check_m0.py")
    print("")
    print("=== tools/check_m0.py --root %s ===" % root)
    m0_code, m0_out = run_subprocess([sys.executable, check_m0_path, "--root", root])
    print(m0_out.rstrip("\n"))

    verify_pack_path = os.path.join(root, "tools", "verify_pack.py")
    print("")
    print("=== tools/verify_pack.py --root %s ===" % root)
    vp_code, vp_out = run_subprocess([sys.executable, verify_pack_path, "--root", root])
    print(vp_out.rstrip("\n"))

    overall_ok = c_result_ok and (m0_code == 0) and (vp_code == 0)
    print("")
    if overall_ok:
        print("check_m1.py OVERALL: PASS")
        return 0
    else:
        print("check_m1.py OVERALL: FAIL (C-checks: %s, check_m0.py: %s, verify_pack.py: %s)" % (
            "PASS" if c_result_ok else "FAIL",
            "PASS" if m0_code == 0 else "FAIL",
            "PASS" if vp_code == 0 else "FAIL",
        ))
        return 1


if __name__ == "__main__":
    sys.exit(main())
