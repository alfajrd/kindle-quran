#!/usr/bin/env python3
"""Milestone-0 local/CI checks for the Qur'an KOReader plugin.

Usage:
    python kindle-quran/tools/check_m0.py [--root <path to kindle-quran>]

Runs every check in ".pipeline/spec.md"'s "Test layer (a)"; never
short-circuits on the first failure. Stdlib + luaparser only. No network.
No Lua execution (there is no Lua interpreter available in this environment).

This script proves the artefact is well-formed. It proves nothing about
on-device rendering -- that is test layer (b), the manual checklist in
README.md.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET

try:
    from luaparser import ast as lua_ast
    from luaparser import astnodes as lua_astnodes
except ImportError:
    lua_ast = None
    lua_astnodes = None

CHECKS = []  # list of (id, passed: bool, message: str)


def record(check_id, passed, message):
    CHECKS.append((check_id, passed, message))


def check_boolean(check_id, condition, ok_desc, fail_reason):
    if condition:
        record(check_id, True, ok_desc)
    else:
        record(check_id, False, fail_reason)


# ---------------------------------------------------------------------------
# Text file helpers
# ---------------------------------------------------------------------------

TEXT_EXTENSIONS = {".lua", ".py", ".json", ".xml", ".sh", ".txt", ".md"}


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def iter_all_files(root):
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            yield os.path.join(dirpath, name)


def iter_text_files(root):
    for path in iter_all_files(root):
        _base, ext = os.path.splitext(path)
        if ext.lower() in TEXT_EXTENSIONS:
            yield path


# ---------------------------------------------------------------------------
# Structure checks (S1-S3)
# ---------------------------------------------------------------------------

REQUIRED_FILES = [
    "README.md",
    ".gitattributes",
    os.path.join("quran.koplugin", "_meta.lua"),
    os.path.join("quran.koplugin", "main.lua"),
    os.path.join("quran.koplugin", "data", "2_255.txt"),
    os.path.join("quran.koplugin", "data", "2_255.sha256"),
    os.path.join("quran.koplugin", "data", "SOURCE.md"),
    os.path.join("extensions", "quran", "menu.json"),
    os.path.join("extensions", "quran", "config.xml"),
    os.path.join("extensions", "quran", "bin", "quran.sh"),
    os.path.join("tools", "check_m0.py"),
]

EXPECTED_KOPLUGIN_FILES = {
    "_meta.lua",
    "main.lua",
    "db.lua",
    "quranreader.lua",
    "quransettings.lua",
    "quranrows.lua",
    "qurannavigator.lua",
    os.path.join("data", "2_255.txt"),
    os.path.join("data", "2_255.sha256"),
    os.path.join("data", "SOURCE.md"),
    os.path.join("data", "quran.db"),
    os.path.join("data", "quran.db.sha256"),
    os.path.join("data", "manifest.json"),
}

FORBIDDEN_EXTENSIONS = {".ttf", ".otf", ".db"}


def check_s1(root):
    missing = []
    for rel in REQUIRED_FILES:
        if not os.path.isfile(os.path.join(root, rel)):
            missing.append(rel)
    check_boolean(
        "S1",
        not missing,
        "every file in \"Files to create\" exists",
        "missing file(s): " + ", ".join(missing),
    )


def check_s2(root):
    koplugin_root = os.path.join(root, "quran.koplugin")
    unexpected = []
    if os.path.isdir(koplugin_root):
        for path in iter_all_files(koplugin_root):
            rel = os.path.relpath(path, koplugin_root)
            if rel not in EXPECTED_KOPLUGIN_FILES:
                unexpected.append(rel)
    else:
        unexpected.append("<quran.koplugin/ missing entirely>")
    check_boolean(
        "S2",
        not unexpected,
        "no unexpected files under quran.koplugin/",
        "unexpected file(s): " + ", ".join(unexpected),
    )


ALLOWED_DB_PATH = os.path.join("quran.koplugin", "data", "quran.db")
# A translation pack is built locally and never committed: .gitignore blocks
# `translations/*.db`, and S4 proves none is tracked. So one may legitimately
# EXIST on a developer's disk, which S3 must not report as a misplaced binary.
#
# The file being present and the file being committed are different facts, and
# only the second is a defect. Conflating them would push whoever hits this
# into deleting their own pack, or worse, into loosening the check that
# actually matters.
TRANSLATIONS_DIR = "translations"


def _rel_posix(rel):
    return rel.replace(chr(92), "/")


def check_s3(root):
    # Fonts live in fonts/ and nowhere else. M0 originally forbade every font
    # file; the font question has since been answered deliberately (Scheherazade
    # New, OFL 1.1, picked by eye on the device), so a vendored face under
    # fonts/ is now expected. Elsewhere it still means a binary landed where it
    # should not. SQLite belonged to Milestone 1, and Milestone 1 has arrived --
    # one pack, one place: quran.koplugin/data/quran.db.
    #
    # Milestone 3 adds a second legitimate .db location, translations/, on the
    # never-committed terms described above.
    offenders = []
    for path in iter_all_files(root):
        rel = os.path.relpath(path, root)
        _base, ext = os.path.splitext(path)
        if ext.lower() not in FORBIDDEN_EXTENSIONS:
            continue
        if ext.lower() == ".db":
            if rel == ALLOWED_DB_PATH:
                continue
            if os.path.dirname(_rel_posix(rel)) == TRANSLATIONS_DIR:
                continue
            offenders.append(rel)
            continue
        if os.path.dirname(_rel_posix(rel)) != "fonts":
            offenders.append(rel)
    check_boolean(
        "S3",
        not offenders,
        "fonts only under fonts/; .db only at %s or under %s/"
        % (_rel_posix(ALLOWED_DB_PATH), TRANSLATIONS_DIR),
        "misplaced binary/forbidden file(s): " + ", ".join(offenders),
    )


def check_s4(root):
    """No translation pack is tracked by git.

    This is the check S3 stopped making, and the one that matters. A
    translation pack on disk is fine; a translation pack in a public
    repository's permanent history is a redistribution nobody authorised, and
    deleting it in a later commit does not undo it.

    Asks git rather than trusting .gitignore, because an ignore rule proves
    nothing about a file that was force-added or staged before the rule
    existed. If git is unavailable the check reports FAIL rather than passing
    silently -- an unverifiable claim about redistribution is not a pass.
    """
    try:
        out = subprocess.run(
            ["git", "-C", root, "ls-files", "--", "%s/" % TRANSLATIONS_DIR],
            capture_output=True, text=True, timeout=30,
        )
        available = out.returncode == 0
        tracked = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    except (OSError, subprocess.SubprocessError):
        available, tracked = False, []

    if not available:
        check_boolean("S4", False,
                      "no translation pack is tracked by git",
                      "could not run `git ls-files` to verify")
        return

    packs = [p for p in tracked if p.lower().endswith((".db", ".sqlite", ".sqlite3"))]
    check_boolean(
        "S4",
        not packs,
        "no translation pack is tracked by git (%d file(s) tracked under %s/)"
        % (len(tracked), TRANSLATIONS_DIR),
        "TRACKED PACK(S) -- this is redistribution: " + ", ".join(packs),
    )


# ---------------------------------------------------------------------------
# Encoding / line-ending checks (E1-E4)
# ---------------------------------------------------------------------------

def check_e1(root):
    bad = []
    for path in iter_text_files(root):
        data = read_bytes(path)
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            bad.append("%s (%s)" % (os.path.relpath(path, root), exc))
    check_boolean(
        "E1",
        not bad,
        "every .lua/.py/.json/.xml/.sh/.txt/.md file decodes as UTF-8",
        "failed to decode: " + ", ".join(bad),
    )


def check_e2(root):
    bad = []
    for path in iter_text_files(root):
        data = read_bytes(path)
        if data[:3] == b"\xef\xbb\xbf":
            bad.append(os.path.relpath(path, root))
    check_boolean(
        "E2",
        not bad,
        "no file starts with a UTF-8 BOM",
        "BOM found in: " + ", ".join(bad),
    )


def check_e3(root):
    bad = []
    for path in iter_text_files(root):
        rel_e3 = os.path.relpath(path, root).replace(chr(92), "/")
        # Vendored third-party docs stay exactly as upstream shipped them;
        # rewriting someone else's licence file to satisfy our lint is the
        # wrong trade. .gitattributes marks them -text so git agrees.
        if rel_e3.startswith("fonts/"):
            continue
        data = read_bytes(path)
        if b"\r" in data:
            bad.append(os.path.relpath(path, root))
    check_boolean(
        "E3",
        not bad,
        "no \\r byte in any checked file",
        "CR byte found in: " + ", ".join(bad),
    )


def check_e4(root):
    path = os.path.join(root, "extensions", "quran", "bin", "quran.sh")
    if not os.path.isfile(path):
        record("E4", False, "bin/quran.sh does not exist")
        return
    data = read_bytes(path)
    first_line = data.split(b"\n", 1)[0]
    check_boolean(
        "E4",
        first_line == b"#!/bin/sh",
        "bin/quran.sh first line is exactly #!/bin/sh",
        "first line was %r" % (first_line,),
    )


# ---------------------------------------------------------------------------
# Lua checks (L1-L6)
# ---------------------------------------------------------------------------

def parse_lua(path):
    """Returns (tree, error) -- error is None on success."""
    if lua_ast is None:
        return None, "luaparser is not installed"
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
    except OSError as exc:
        return None, str(exc)
    try:
        tree = lua_ast.parse(src)
    except Exception as exc:  # luaparser raises its own exception types
        return None, str(exc)
    return tree, None


def check_l1_l2(root):
    meta_path = os.path.join(root, "quran.koplugin", "_meta.lua")
    main_path = os.path.join(root, "quran.koplugin", "main.lua")

    meta_tree, meta_err = parse_lua(meta_path)
    check_boolean(
        "L1",
        meta_tree is not None,
        "_meta.lua parses",
        "_meta.lua failed to parse: %s" % meta_err,
    )

    main_tree, main_err = parse_lua(main_path)
    check_boolean(
        "L2",
        main_tree is not None,
        "main.lua parses",
        "main.lua failed to parse: %s" % main_err,
    )
    return meta_tree, main_tree


def find_return_table_fields(tree):
    """Walks a Chunk's top-level body for the Return statement and returns
    its Table's Field nodes (or None if no such Return/Table is found)."""
    if tree is None:
        return None
    try:
        body = tree.body.body
    except AttributeError:
        return None
    for stmt in body:
        if lua_astnodes is not None and isinstance(stmt, lua_astnodes.Return):
            if stmt.values:
                table = stmt.values[0]
                if lua_astnodes is not None and isinstance(table, lua_astnodes.Table):
                    return table.fields
    return None


def field_key_name(field):
    key = getattr(field, "key", None)
    return getattr(key, "id", None)


def field_string_value(field):
    value = getattr(field, "value", None)
    if lua_astnodes is not None and isinstance(value, lua_astnodes.String):
        s = value.s
        if isinstance(s, bytes):
            return s.decode("utf-8", errors="replace")
        return s
    return None


def check_l3_l4(root, meta_tree, main_tree):
    fields = find_return_table_fields(meta_tree)
    if fields is None:
        record("L3", False, "could not find a Return<Table> in _meta.lua")
        record("L4", False, "could not find a Return<Table> in _meta.lua")
        return

    keys = {field_key_name(f) for f in fields}
    required_keys = {"name", "fullname", "description", "version"}
    missing_keys = required_keys - keys
    check_boolean(
        "L3",
        not missing_keys,
        "_meta.lua's returned table has keys name/fullname/description/version",
        "missing key(s): " + ", ".join(sorted(missing_keys)),
    )

    name_value = None
    for f in fields:
        if field_key_name(f) == "name":
            name_value = field_string_value(f)
            break

    main_path = os.path.join(root, "quran.koplugin", "main.lua")
    main_src = ""
    if os.path.isfile(main_path):
        main_src = read_bytes(main_path).decode("utf-8", errors="replace")

    l4_ok = (name_value == "quran") and ('name = "quran"' in main_src)
    reasons = []
    if name_value != "quran":
        reasons.append("_meta.lua name = %r (expected 'quran')" % (name_value,))
    if 'name = "quran"' not in main_src:
        reasons.append('main.lua does not contain name = "quran"')
    check_boolean(
        "L4",
        l4_ok,
        "_meta.lua's name is 'quran' and main.lua contains name = \"quran\"",
        "; ".join(reasons),
    )


def _unterminated_short_strings(src):
    """(line, quote) for Lua short strings that run into end-of-line.

    Lua short strings (' or ") may not contain a raw newline -- only [[ ]]
    long strings may. Long strings and comments are skipped so their contents
    are not scanned.
    """
    DQ, SQ, BS, NL = chr(34), chr(39), chr(92), chr(10)
    out = []
    i, n, line = 0, len(src), 1
    long_open = re.compile(r"(--)?\[(=*)\[")
    while i < n:
        c = src[i]
        if c == NL:
            line += 1
            i += 1
            continue
        m = long_open.match(src, i)
        if m:
            close = "]" + m.group(2) + "]"
            j = src.find(close, m.end())
            end = n if j == -1 else j + len(close)
            line += src.count(NL, i, end)
            i = end
            continue
        if src.startswith("--", i):
            j = src.find(NL, i)
            i = n if j == -1 else j
            continue
        if c == DQ or c == SQ:
            j, closed = i + 1, False
            while j < n:
                if src[j] == BS:
                    j += 2
                    continue
                if src[j] == c:
                    closed = True
                    break
                if src[j] == NL:
                    break
                j += 1
            if not closed:
                out.append((line, c))
            i = j + 1
            continue
        i += 1
    return out


def check_l7(root):
    """No Lua short string spans a line.

    luaparser accepts this; LuaJIT does not, and KOReader skips a plugin that
    fails to load without a word. That combination cost a device trip once --
    every structural check passed while the plugin was dead. This is the one
    luaparser/LuaJIT divergence known to have bitten this project.
    """
    offenders = []
    koplugin = os.path.join(root, "quran.koplugin")
    if os.path.isdir(koplugin):
        for name in sorted(os.listdir(koplugin)):
            if not name.endswith(".lua"):
                continue
            path = os.path.join(koplugin, name)
            src = read_bytes(path).decode("utf-8", errors="strict")
            for line_no, quote in _unterminated_short_strings(src):
                offenders.append("%s:%d (%s)" % (name, line_no, quote))
    check_boolean(
        "L7",
        not offenders,
        "no Lua short string spans a line (luaparser accepts this; LuaJIT does not)",
        "unterminated short string at: " + ", ".join(offenders),
    )

def check_l5(root):
    main_path = os.path.join(root, "quran.koplugin", "main.lua")
    if not os.path.isfile(main_path):
        record("L5", False, "main.lua does not exist")
        return
    src = read_bytes(main_path).decode("utf-8", errors="replace")
    check_boolean(
        "L5",
        "is_doc_only = false" in src,
        "main.lua contains is_doc_only = false",
        "main.lua does not contain 'is_doc_only = false'",
    )


def check_l6(main_tree):
    if main_tree is None:
        record("L6", False, "main.lua did not parse; cannot check last statement")
        return
    try:
        body = main_tree.body.body
    except AttributeError:
        record("L6", False, "could not read main.lua's top-level statement list")
        return
    if not body:
        record("L6", False, "main.lua has no statements")
        return
    last = body[-1]
    is_return = lua_astnodes is not None and isinstance(last, lua_astnodes.Return)
    check_boolean(
        "L6",
        is_return,
        "main.lua's last statement is a return of the plugin table",
        "main.lua's last statement is %s, not Return" % type(last).__name__,
    )


# ---------------------------------------------------------------------------
# Manifest checks (M1-M2)
# ---------------------------------------------------------------------------

def check_m1(root):
    menu_path = os.path.join(root, "extensions", "quran", "menu.json")
    if not os.path.isfile(menu_path):
        record("M1", False, "extensions/quran/menu.json does not exist")
        return
    try:
        data = json.loads(read_bytes(menu_path).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        record("M1", False, "menu.json is not valid JSON: %s" % exc)
        return

    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        record("M1", False, "menu.json has no non-empty 'items' array")
        return

    first = items[0]
    name = first.get("name") if isinstance(first, dict) else None
    action = first.get("action") if isinstance(first, dict) else None

    reasons = []
    if not isinstance(name, str) or not name:
        reasons.append("items[0].name is not a non-empty string")
    if not isinstance(action, str) or not action:
        reasons.append("items[0].action is not a non-empty string")
    else:
        action_path = os.path.join(root, "extensions", "quran", action)
        if not os.path.exists(action_path):
            reasons.append("items[0].action path does not exist: %s" % action_path)

    check_boolean(
        "M1",
        not reasons,
        "menu.json is valid, non-empty, and its action path exists",
        "; ".join(reasons),
    )


def check_m2(root):
    config_path = os.path.join(root, "extensions", "quran", "config.xml")
    if not os.path.isfile(config_path):
        record("M2", False, "extensions/quran/config.xml does not exist")
        return
    try:
        ET.parse(config_path)
    except ET.ParseError as exc:
        record("M2", False, "config.xml failed to parse: %s" % exc)
        return
    record("M2", True, "config.xml parses with xml.etree.ElementTree")


# ---------------------------------------------------------------------------
# The Arabic string checks (A1-A12)
# ---------------------------------------------------------------------------

BEGIN_MARKER = "-- BEGIN VERBATIM TANZIL UTHMANI 2:255 -- DO NOT EDIT, DO NOT NORMALISE, DO NOT REFLOW"
END_MARKER = "-- END VERBATIM"


def extract_embedded_ayah(main_src):
    """Returns (E, error). E is the unwrapped, stripped text between the
    markers, or None if the markers are not exactly-once-each and in
    order."""
    begin_count = main_src.count(BEGIN_MARKER)
    end_count = main_src.count(END_MARKER)
    if begin_count != 1 or end_count != 1:
        return None, "BEGIN marker appears %d time(s), END marker appears %d time(s) (expected 1 each)" % (
            begin_count, end_count,
        )
    begin_idx = main_src.index(BEGIN_MARKER)
    end_idx = main_src.index(END_MARKER)
    if begin_idx >= end_idx:
        return None, "BEGIN marker does not appear before END marker"

    between = main_src[begin_idx + len(BEGIN_MARKER):end_idx]
    match = re.search(r"\[==\[(.*?)\]==\]", between, re.DOTALL)
    if not match:
        return None, "no [==[ ... ]==] long-bracket literal found between the markers"
    raw = match.group(1)
    return raw.strip(), None


def check_a1_a3(root):
    main_path = os.path.join(root, "quran.koplugin", "main.lua")
    txt_path = os.path.join(root, "quran.koplugin", "data", "2_255.txt")
    sha_path = os.path.join(root, "quran.koplugin", "data", "2_255.sha256")

    if not os.path.isfile(main_path) or not os.path.isfile(txt_path):
        record("A1", False, "main.lua or data/2_255.txt does not exist")
        record("A2", False, "main.lua or data/2_255.txt does not exist")
        record("A3", False, "data/2_255.txt or data/2_255.sha256 does not exist")
        return None, None

    main_src = read_bytes(main_path).decode("utf-8")
    T = read_bytes(txt_path).decode("utf-8").strip()

    E, err = extract_embedded_ayah(main_src)
    check_boolean(
        "A1",
        E is not None,
        "BEGIN/END VERBATIM markers exist exactly once each, in order",
        err or "",
    )

    if E is None:
        record("A2", False, "could not extract embedded literal (see A1)")
    else:
        check_boolean(
            "A2",
            E == T,
            "embedded literal in main.lua is byte-identical to data/2_255.txt",
            "embedded literal and data/2_255.txt differ",
        )

    import hashlib
    actual_hash = hashlib.sha256(T.encode("utf-8")).hexdigest()
    if not os.path.isfile(sha_path):
        record("A3", False, "data/2_255.sha256 does not exist")
    else:
        sha_content = read_bytes(sha_path).decode("utf-8").strip()
        expected_hash = sha_content.split()[0].lower() if sha_content else ""
        check_boolean(
            "A3",
            actual_hash == expected_hash,
            "sha256(T) matches data/2_255.sha256",
            "sha256(T) = %s, file says %s" % (actual_hash, expected_hash),
        )

    return T, E


def check_a4(T):
    if T is None:
        record("A4", False, "T unavailable (see A1-A3)")
        return
    reasons = []
    if "\n" in T:
        reasons.append("contains \\n")
    if "\r" in T:
        reasons.append("contains \\r")
    if "\t" in T:
        reasons.append("contains \\t")
    if "  " in T:
        reasons.append("contains a double space")
    check_boolean(
        "A4",
        not reasons,
        "T contains no \\n, \\r, \\t, and no double space",
        "; ".join(reasons),
    )


def check_a5(T):
    if T is None:
        record("A5", False, "T unavailable (see A1-A3)")
        return
    offenders = []
    for ch in T:
        cp = ord(ch)
        if cp == 0x0020:
            continue
        if 0x0600 <= cp <= 0x06FF:
            continue
        if 0x08A0 <= cp <= 0x08FF:
            continue
        offenders.append("U+%04X" % cp)
    check_boolean(
        "A5",
        not offenders,
        "every codepoint of T is U+0020, U+0600-06FF, or U+08A0-08FF",
        "offending codepoint(s): " + ", ".join(sorted(set(offenders))),
    )


def check_a6(T):
    if T is None:
        record("A6-presentation-forms", False, "T unavailable (see A1-A3)")
        record("A6-tatweel", False, "T unavailable (see A1-A3)")
        record("A6-indic-digits", False, "T unavailable (see A1-A3)")
        record("A6-eoa-marker", False, "T unavailable (see A1-A3)")
        record("A6-ascii", False, "T unavailable (see A1-A3)")
        return

    presentation_forms = [ch for ch in T if 0xFB50 <= ord(ch) <= 0xFDFF or 0xFE70 <= ord(ch) <= 0xFEFF]
    check_boolean(
        "A6-presentation-forms",
        not presentation_forms,
        "no Arabic presentation-form codepoints (U+FB50-FDFF, U+FE70-FEFF)",
        "found %d presentation-form codepoint(s)" % len(presentation_forms),
    )

    tatweel_count = T.count("ـ")
    check_boolean(
        "A6-tatweel",
        tatweel_count == 1,
        "exactly one tatweel (U+0640), as in the authentic text",
        "found %d tatweel codepoint(s) (expected exactly 1)" % tatweel_count,
    )

    indic_digits = [ch for ch in T if 0x0660 <= ord(ch) <= 0x0669 or 0x06F0 <= ord(ch) <= 0x06F9]
    check_boolean(
        "A6-indic-digits",
        not indic_digits,
        "no Arabic-Indic digits (U+0660-0669, U+06F0-06F9)",
        "found %d Arabic-Indic digit(s)" % len(indic_digits),
    )

    check_boolean(
        "A6-eoa-marker",
        "۝" not in T,
        "no U+06DD end-of-ayah marker",
        "found U+06DD",
    )

    non_space_ascii = [ch for ch in T if ord(ch) < 0x80 and ch != " "]
    check_boolean(
        "A6-ascii",
        not non_space_ascii,
        "no ASCII other than U+0020",
        "found ASCII character(s): " + ", ".join(sorted(set(non_space_ascii))),
    )


def base_letter_sequence(T):
    """T with all Unicode category Mn (non-spacing mark) codepoints removed."""
    return "".join(ch for ch in T if unicodedata.category(ch) != "Mn")


def check_a7(T):
    if T is None:
        record("A7", False, "T unavailable (see A1-A3)")
        return
    B = base_letter_sequence(T)
    found = False
    for i in range(len(B) - 1):
        if B[i] == "ل" and B[i + 1] in ("ا", "آ"):
            found = True
            break
    check_boolean(
        "A7",
        found,
        "base-letter sequence B contains a lam-alef ligature site (U+0644 followed by U+0627 or U+0622)",
        "no lam-alef ligature site found in B",
    )


def check_a8(T):
    if T is None:
        record("A8", False, "T unavailable (see A1-A3)")
        return
    count = T.count("ّ")
    check_boolean(
        "A8",
        count >= 3,
        "T contains at least three shadda (U+0651) (found %d)" % count,
        "only %d shadda found (need >= 3)" % count,
    )


def check_a9(T):
    if T is None:
        record("A9", False, "T unavailable (see A1-A3)")
        return
    count = T.count("ٰ")
    check_boolean(
        "A9",
        count >= 1,
        "T contains at least one superscript alef (U+0670) (found %d)" % count,
        "no superscript alef found",
    )


def check_a10(T):
    if T is None:
        record("A10", False, "T unavailable (see A1-A3)")
        return
    count = T.count("ٱ")
    check_boolean(
        "A10",
        count >= 1,
        "T contains at least one alef wasla (U+0671) (found %d)" % count,
        "no alef wasla found",
    )


def check_a11(T):
    if T is None:
        record("A11", False, "T unavailable (see A1-A3)")
        return
    found = False
    i = 0
    n = len(T)
    while i < n:
        if unicodedata.category(T[i]) != "Mn":
            j = i + 1
            mn_run = 0
            while j < n and unicodedata.category(T[j]) == "Mn":
                mn_run += 1
                j += 1
            if mn_run >= 2:
                found = True
                break
            i = j if j > i else i + 1
        else:
            i += 1
    check_boolean(
        "A11",
        found,
        "T contains a base character followed by two or more consecutive Mn codepoints (stacked harakat)",
        "no stacked-harakat site found",
    )


def check_a12(T):
    if T is None:
        record("A12", False, "T unavailable (see A1-A3)")
        return
    length = len(T)
    check_boolean(
        "A12",
        380 <= length <= 480,
        "T length (%d codepoints) is within the 380-480 sanity band" % length,
        "T length is %d codepoints (expected 380-480)" % length,
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument("--root", default=default_root, help="path to kindle-quran/ (default: %(default)s)")
    args = parser.parse_args()
    root = os.path.abspath(args.root)

    check_s1(root)
    check_s2(root)
    check_s3(root)
    check_s4(root)

    check_e1(root)
    check_e2(root)
    check_e3(root)
    check_e4(root)

    meta_tree, main_tree = check_l1_l2(root)
    check_l3_l4(root, meta_tree, main_tree)
    check_l5(root)
    check_l6(main_tree)

    check_l7(root)
    check_m1(root)
    check_m2(root)

    T, _E = check_a1_a3(root)
    check_a4(T)
    check_a5(T)
    check_a6(T)
    check_a7(T)
    check_a8(T)
    check_a9(T)
    check_a10(T)
    check_a11(T)
    check_a12(T)

    failed = 0
    for check_id, passed, message in CHECKS:
        if passed:
            print("PASS  %s  %s" % (check_id, message))
        else:
            failed += 1
            print("FAIL  %s  %s" % (check_id, message))

    total = len(CHECKS)
    if failed == 0:
        print("RESULT: PASS (%d checks)" % total)
        return 0
    else:
        print("RESULT: FAIL (%d of %d failed)" % (failed, total))
        return 1


if __name__ == "__main__":
    sys.exit(main())
