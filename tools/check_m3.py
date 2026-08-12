#!/usr/bin/env python3
"""Milestone-3 checks: interleaved layout wiring, and Lua cross-references.

    python tools/check_m3.py [--root <repo root>]

WHY THIS EXISTS
---------------
There is no Lua interpreter on this machine, so nothing here executes. That
gap has already cost one wasted device trip: `luaparser` accepted a string
containing raw newlines, LuaJIT did not, and KOReader skipped the plugin in
silence while every structural check passed (check_m0's L7 now covers that
specific divergence).

Syntax is therefore proven and semantics are not. This program closes the one
semantic gap that is both cheap to check and expensive to miss: **a call to a
function that does not exist**. On the device that surfaces as
`attempt to call a nil value`, mid-page-turn, with the reader already open --
the worst place to find it and the slowest to diagnose over a USB cable.

It cannot prove the layout is correct. It proves the wiring is connected.

Stdlib only. No network.
"""
import argparse
import os
import re
import sys

CHECKS = []

# Modules whose members are called as `Name.member(...)`, and the file that is
# expected to define them.
MODULE_OWNERS = {
    "Rows": "quranrows.lua",
    "Nav": "qurannavigator.lua",
    "DB": "db.lua",
    "Settings": "quransettings.lua",
    "TextMetrics": "quranreader.lua",
}

# Members reached through the reader's own handover fields (see
# quranreader.lua's init), so `self.DB.getAyah(...)` resolves against db.lua.
SELF_FIELD_OWNERS = {
    "DB": "DB",
    "TextMetrics": "TextMetrics",
}

# `self:method(...)` inside these files resolves against the named receiver.
SELF_METHOD_OWNERS = {
    "quranreader.lua": "Reader",
    "main.lua": "Quran",
}

DEF_RE = re.compile(r"^\s*function\s+([A-Za-z_]\w*)[.:]([A-Za-z_]\w*)\s*\(", re.M)
LOCAL_FN_RE = re.compile(r"^\s*local\s+function\s+([A-Za-z_]\w*)\s*\(", re.M)
ASSIGN_FN_RE = re.compile(r"^\s*([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*=\s*function\s*\(", re.M)


def record(cid, ok, msg):
    CHECKS.append((cid, ok, msg))
    print("%-5s %-4s %s" % ("PASS" if ok else "FAIL", cid, msg))


def strip_lua_comments(src):
    """Remove --[[ ]] blocks and -- line comments, preserving line count.

    Calls inside a comment are prose, not wiring. Without this the checks
    below flag every function named in a doc comment.
    """
    out = []
    i, n = 0, len(src)
    while i < n:
        if src.startswith("--", i):
            m = re.match(r"--\[(=*)\[", src[i:])
            if m:
                close = "]" + m.group(1) + "]"
                j = src.find(close, i)
                end = n if j == -1 else j + len(close)
                out.append("\n" * src.count("\n", i, end))
                i = end
                continue
            j = src.find("\n", i)
            i = n if j == -1 else j
            continue
        if src[i] in "\"'":
            q = src[i]
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == q or src[j] == "\n":
                    break
                j += 1
            out.append(src[i:min(j + 1, n)])
            i = j + 1
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def collect(plugin_dir):
    """-> (defs, sources) where defs[owner] is the set of member names."""
    defs, sources = {}, {}
    for name in sorted(os.listdir(plugin_dir)):
        if not name.endswith(".lua"):
            continue
        src = strip_lua_comments(read(os.path.join(plugin_dir, name)))
        sources[name] = src
        for owner, member in DEF_RE.findall(src):
            defs.setdefault(owner, set()).add(member)
        for owner, member in ASSIGN_FN_RE.findall(src):
            defs.setdefault(owner, set()).add(member)
    return defs, sources


def check_module_calls(defs, sources):
    """Every `Module.member(...)` call resolves to a definition."""
    missing = []
    for fname, src in sources.items():
        for owner in MODULE_OWNERS:
            for m in re.finditer(r"\b%s\.([A-Za-z_]\w*)\s*\(" % owner, src):
                member = m.group(1)
                if member not in defs.get(owner, set()):
                    line = src.count("\n", 0, m.start()) + 1
                    missing.append("%s:%d %s.%s" % (fname, line, owner, member))
    record("X1", not missing,
           "every Module.member(...) call resolves to a definition"
           + ("" if not missing else "  -- UNRESOLVED: " + ", ".join(sorted(set(missing)))))


def check_self_field_calls(defs, sources):
    """Every `self.Field.member(...)` call resolves (the handover fields)."""
    missing = []
    for fname, src in sources.items():
        for field, owner in SELF_FIELD_OWNERS.items():
            for m in re.finditer(r"\bself\.%s\.([A-Za-z_]\w*)\s*\(" % field, src):
                member = m.group(1)
                if member not in defs.get(owner, set()):
                    line = src.count("\n", 0, m.start()) + 1
                    missing.append("%s:%d self.%s.%s" % (fname, line, field, member))
    record("X2", not missing,
           "every self.<handover>.member(...) call resolves"
           + ("" if not missing else "  -- UNRESOLVED: " + ", ".join(sorted(set(missing)))))


def check_self_methods(defs, sources):
    """Every `self:method(...)` resolves against its file's receiver."""
    missing = []
    for fname, owner in SELF_METHOD_OWNERS.items():
        src = sources.get(fname)
        if src is None:
            continue
        known = defs.get(owner, set())
        for m in re.finditer(r"\bself:([A-Za-z_]\w*)\s*\(", src):
            member = m.group(1)
            # Widget-framework methods the plugin inherits rather than defines.
            if member in {"free", "getSize", "paintTo", "init", "onClose"}:
                continue
            if member not in known:
                line = src.count("\n", 0, m.start()) + 1
                missing.append("%s:%d self:%s" % (fname, line, member))
    record("X3", not missing,
           "every self:method(...) resolves against its receiver"
           + ("" if not missing else "  -- UNRESOLVED: " + ", ".join(sorted(set(missing)))))


def check_handover_fields(sources):
    """Everything quranrows.lua reads off `self` is set by quranreader.lua.

    quranrows.lua is handed its dependencies rather than requiring them, which
    keeps the TextBoxWidget internals behind one wrapper -- but it also means a
    field renamed in the reader fails as `nil` in the rows module, at layout
    time, on the device. This is that rename's tripwire.
    """
    rows = sources.get("quranrows.lua", "")
    reader = sources.get("quranreader.lua", "")
    if not rows or not reader:
        record("X4", False, "quranrows.lua or quranreader.lua is missing")
        return

    # `self` means two different things in quranrows.lua: the Reader inside
    # `Rows.*` functions, and the RowPage widget inside `RowPage:*` methods.
    # Only the first kind is a handover, so the widget's own methods are cut
    # out before scanning. Conflating them reported RowPage's own `items` and
    # `width` as fields the reader had failed to set.
    scanned = re.sub(r"^function\s+RowPage[.:]\w+\s*\(.*?^end\s*$", "",
                     rows, flags=re.S | re.M)

    # Fields quranrows reads but never assigns.
    read_fields = set(re.findall(r"\bself\.([A-Za-z_]\w*)", scanned))
    assigned_in_rows = set(re.findall(r"\bself\.([A-Za-z_]\w*)\s*=", scanned))
    needed = read_fields - assigned_in_rows

    set_in_reader = set(re.findall(r"\bself\.([A-Za-z_]\w*)\s*=", reader))
    # Set by Rows.computeGeometry itself, on the reader's behalf.
    set_in_rows = set(re.findall(r"\bself\.([A-Za-z_]\w*)\s*=", rows))
    # Passed in as constructor opts by main.lua (:new{} becomes self's fields).
    from_opts = {"conn", "tconn", "store", "surah", "ayah", "line", "on_close"}

    unset = sorted(needed - set_in_reader - set_in_rows - from_opts)
    record("X5", not unset,
           "every self.<field> quranrows.lua reads is set by the reader"
           + ("" if not unset else "  -- NEVER SET: " + ", ".join(unset)))


def check_m3_wiring(sources):
    """The specific connections M3 depends on, named rather than inferred."""
    reader = sources.get("quranreader.lua", "")
    rows = sources.get("quranrows.lua", "")
    settings = sources.get("quransettings.lua", "")
    main = sources.get("main.lua", "")

    # Matches either call form. The bare `require("quranrows")` spelling is
    # not wanted here -- X7 requires the guarded one -- so this only asserts
    # the dependency exists at all.
    record("X6", re.search(r'require\s*\(\s*"quranrows"|require\s*,\s*"quranrows"', reader)
           is not None,
           "quranreader.lua depends on quranrows")
    record("X7", re.search(r'pcall\s*\(\s*require\s*,\s*"quranrows"\s*\)', reader) is not None,
           "the quranrows require is pcall-guarded, so a load failure degrades "
           "to Arabic-only rather than killing the reader")
    record("X8", "display_mode" in settings and "DISPLAY_MODES" in settings,
           "quransettings.lua defines display_mode and its valid values")
    record("X9", "english_font_size" in settings and "english_line_height" in settings,
           "quransettings.lua carries independent English typography")
    record("X10", "openTranslation" in main and "tconn" in main,
           "main.lua opens a translation pack and hands it to the reader")
    record("X11", "trans_surah_intro" in sources.get("db.lua", ""),
           "db.lua can read surah introductions (the table ships empty)")

    # The basmala must never be a literal in the source -- it is read from the
    # pack. Any Arabic codepoint in the layout module means someone typed
    # scripture, which is what corrupted 2:255 once already.
    arabic = [(i + 1, ln) for i, ln in enumerate(rows.splitlines())
              if any(0x0600 <= ord(c) <= 0x06FF for c in ln)]
    record("X12", not arabic,
           "quranrows.lua contains no literal Arabic -- the basmala is read "
           "from the pack, never written down"
           + ("" if not arabic else "  -- FOUND at line(s) %s"
              % [n for n, _ in arabic[:5]]))

    # Both rule models must stay separate (§9.1).
    record("X13", "RULE_GAP_FRACTION" not in rows,
           "quranrows.lua does not reuse the per-line rule tuning -- a row "
           "rule sits in a computed gutter and needs none")

    check_m4_wiring(sources)


def check_m4_wiring(sources):
    """Milestone 4: the navigator."""
    nav = sources.get("qurannavigator.lua", "")
    reader = sources.get("quranreader.lua", "")
    main = sources.get("main.lua", "")
    db = sources.get("db.lua", "")

    record("X14", bool(nav), "qurannavigator.lua exists")
    record("X15",
           "listSurahs" in db and "listJuz" in db and "juzOf" in db,
           "db.lua exposes the surah list, the juz list and juz lookup")

    # The navigator must take DATA, not a live connection: a menu waits
    # indefinitely for a tap and may be dismissed, so a connection held across
    # it is one nobody closes.
    holds_conn = re.search(r"function\s+Nav\.show\w+\(opts\)(.{0,600}?)opts\.conn", nav, re.S)
    record("X16", holds_conn is None,
           "no Nav.show* function reads opts.conn -- pickers take data, so a "
           "dismissed menu cannot leak a connection"
           + ("" if holds_conn is None else "  -- opts.conn used in a show* function"))

    # Every route that opens a picker must close its connection.
    opens = main.count("DB.open(db_path)")
    record("X17", "DB.close(conn)" in main and "Nav.loadData" in main,
           "main.lua loads navigator data and closes its connection (%d open sites)" % opens)

    # Jumping surahs must refresh the per-surah state; using the old
    # ayah_count is how a reader pages past the end of a short surah.
    goto = re.search(r"function\s+Reader:goTo\b(.*?)\nend\n", reader, re.S)
    body = goto.group(1) if goto else ""
    record("X18",
           bool(goto) and "getSurahAyahCount" in body and "ayah_count" in body
           and "line_count_cache" in body and "row_cache" in body,
           "Reader:goTo re-reads ayah_count and drops both measurement caches "
           "when the surah changes")

    # The reference parser must anchor its patterns. Unanchored, "2:255x"
    # silently becomes a jump to 2:255 instead of an error.
    pats = re.findall(r'match\("([^"]+)"\)', nav)
    unanchored = [p for p in pats if not (p.startswith("^") and p.endswith("$"))]
    record("X19", pats and not unanchored,
           "every reference-parser pattern is anchored (%d found), so trailing "
           "junk is an error rather than a silent jump" % len(pats)
           + ("" if not unanchored else "  -- UNANCHORED: %s" % unanchored))

    # An explicit destination must beat the remembered position, or picking a
    # juz boundary would land wherever you last stopped in that surah.
    #
    # Checks the ASSIGNMENT, not the mention. The first version of this check
    # tested `"at_ayah" in main`, which the parameter name and a comment
    # satisfied on their own -- it passed with the override disabled.
    override = re.search(
        r"if\s+type\(at_ayah\)\s*==\s*\"number\".*?\n\s*ayah,\s*line\s*=\s*at_ayah\s*,\s*0",
        main, re.S)
    record("X20", override is not None,
           "an explicit destination actually overrides position memory "
           "(the assignment, not just the parameter)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = ap.parse_args()

    plugin_dir = os.path.join(args.root, "quran.koplugin")
    if not os.path.isdir(plugin_dir):
        raise SystemExit("no quran.koplugin/ under %s" % args.root)

    defs, sources = collect(plugin_dir)
    check_module_calls(defs, sources)
    check_self_field_calls(defs, sources)
    check_self_methods(defs, sources)
    check_handover_fields(sources)
    check_m3_wiring(sources)

    failed = [c for c in CHECKS if not c[1]]
    print()
    print("RESULT: %s (%d checks)"
          % ("PASS" if not failed else "FAIL (%d of %d failed)" % (len(failed), len(CHECKS)),
             len(CHECKS)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
