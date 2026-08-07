#!/usr/bin/env python3
"""Durable regression tests for `kindle-quran/tools/check_m1.py` and
`kindle-quran/tools/verify_pack.py`.

Same discipline as `tests/test_check_m0.py`: these tests do NOT re-run the
checkers and trust them. Each test builds a deliberately corrupted COPY of
`kindle-quran/` in a throwaway temp directory, runs the real, unmodified
`tools/check_m1.py` (from that copy, `--root <copy>`) as a subprocess, and
asserts it FAILS -- and, for every mutation, asserts exactly which check
id(s) caught it. `check_m1.py` shells out to the copy's own
`tools/check_m0.py` and `tools/verify_pack.py`, and echoes their PASS/FAIL
lines verbatim, so a single subprocess call and a single regex pass over
its combined stdout is enough to see C-ids, P-ids and the M0 S/E/L/M/A-ids
all at once.

None of this ever touches the real repository tree. Every mutation happens
on a `tempfile.mkdtemp()` copy, and every test removes its own temp
directory in a `finally` block.

KNOWN LIMITATION -- READ BEFORE TRUSTING THIS SUITE AS CONTENT AUTHENTICATION
------------------------------------------------------------------------
Exactly the same limitation `tests/test_check_m0.py` documents for the M0
pin, now at corpus scale: if `data/quran-uthmani.txt`,
`data/quran-uthmani.sha256`, the in-source digest constants in
`build_pack.py`/`verify_pack.py`/`check_m1.py`, AND the committed
`quran.db` were all regenerated together from corrupted text, every check
in this suite -- and in `check_m1.py` itself -- passes. The digests here
only prove the copies committed in this repository agree with each other;
they cannot and do not prove the text still matches Tanzil. That is not a
defect in this test suite or in `check_m1.py`; it is inherent to any purely
structural/statistical check, and it is why `docs/BUILD.md` and
`data/SOURCE.md` both name the only real mitigation: a human `diff` of
`data/quran-uthmani.txt` against a hand-downloaded Tanzil file, at review
time. Nobody should mistake "this test suite passes" for proof that the
Arabic text is still byte-correct against Tanzil.

Usage:
    python kindle-quran/tests/test_check_m1.py
    (from the repo root, or any cwd -- paths are resolved from this file's
    location, not from cwd)

Also runnable under pytest, but pytest is NOT required -- every test is a
plain `test_*` function using bare `assert`, and `main()` below discovers
and runs them without it.

Stdlib only. No network. No Lua execution.
"""

import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unicodedata

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK_M1_SCRIPT = os.path.join(REPO_ROOT, "tools", "check_m1.py")

DB_REL = os.path.join("quran.koplugin", "data", "quran.db")
DB_SHA_REL = os.path.join("quran.koplugin", "data", "quran.db.sha256")
CORPUS_TXT_REL = os.path.join("data", "quran-uthmani.txt")
SURAH_META_SHA_REL = os.path.join("data", "surah_meta.sha256")
MAIN_LUA_REL = os.path.join("quran.koplugin", "main.lua")
BUILD_PACK_REL = os.path.join("tools", "build_pack.py")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def write_bytes(path, data):
    with open(path, "wb") as f:
        f.write(data)


def make_mutant_copy():
    tmp = tempfile.mkdtemp(prefix="check_m1_test_")
    dst = os.path.join(tmp, "kindle-quran")
    shutil.copytree(
        REPO_ROOT,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"),
    )
    return tmp, dst


def run_build_pack(root):
    """Runs the copy's own tools/build_pack.py as a subprocess. Returns
    (returncode, stdout+stderr)."""
    proc = subprocess.run(
        [sys.executable, os.path.join(root, "tools", "build_pack.py"), "--root", root],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.returncode, proc.stdout + proc.stderr


def read_vendored_ayah(root, surah, ayah):
    """Independently parses data/quran-uthmani.txt's own copy to fetch one
    ayah's exact text -- copying bytes, never retyping Arabic."""
    path = os.path.join(root, CORPUS_TXT_REL)
    text = read_bytes(path).decode("utf-8")
    body = text[:-1] if text.endswith("\n") else text
    for line in body.split("\n"):
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        s_str, a_str, ayah_text = parts
        if s_str == str(surah) and a_str == str(ayah):
            return ayah_text
    raise AssertionError("could not find %d:%d in %s" % (surah, ayah, path))


def run_checker(root):
    """Runs the REAL, unmodified tools/check_m1.py (from the copy, which
    itself shells out to the copy's own check_m0.py/verify_pack.py) against
    `--root <root>`. Returns (returncode, {id: bool}, stdout)."""
    proc = subprocess.run(
        [sys.executable, os.path.join(root, "tools", "check_m1.py"), "--root", root],
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


def mutate_db(dst_root, fn):
    """Opens the copy's quran.db read-write, calls fn(conn), commits, closes."""
    path = os.path.join(dst_root, DB_REL)
    conn = sqlite3.connect(path)
    try:
        fn(conn)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_clean_tree_passes():
    tmp, dst = make_mutant_copy()
    try:
        code, statuses, stdout = run_checker(dst)
        assert code == 0, "expected exit 0 on an unmodified copy, got %d\n%s" % (code, stdout)
        assert statuses, "expected at least one check to be reported\n%s" % stdout
        assert all(statuses.values()), "expected every check to PASS on an unmodified copy\n%s" % stdout
        assert "check_m1.py OVERALL: PASS" in stdout, stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_drop_last_ayah_line_of_corpus_is_caught():
    # The vendored corpus is Tanzil's own download: EXPECTED_AYAH_COUNT
    # "surah|ayah|text" lines, THEN a trailer of blank lines and lines
    # starting with '#' (Tanzil's copyright block). Dropping the file's
    # literal last line would only remove trailer prose, not ayah data --
    # so this drops the last genuine AYAH line (114:6) instead, which is
    # what should actually break structural validity.
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, CORPUS_TXT_REL)
        text = read_bytes(path).decode("utf-8")
        body = text[:-1] if text.endswith("\n") else text
        lines = body.split("\n")
        EXPECTED_AYAH_COUNT = 6236
        del lines[EXPECTED_AYAH_COUNT - 1]
        new_text = "\n".join(lines) + "\n"
        write_bytes(path, new_text.encode("utf-8"))
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "C2", "C3")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_nfc_normalise_corpus_file_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, CORPUS_TXT_REL)
        text = read_bytes(path).decode("utf-8")
        write_bytes(path, unicodedata.normalize("NFC", text).encode("utf-8"))
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "C2")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_feff_injection_into_ayah_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        def mutate(conn):
            conn.execute("UPDATE ayah SET text = ? || text WHERE surah = 1 AND ayah = 2;", ("﻿",))
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P12", "P16")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_feff_injection_into_surah_name_ar_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        def mutate(conn):
            conn.execute("UPDATE surah SET name_ar = ? || name_ar WHERE id = 5;", ("﻿",))
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P12", "P27")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_presentation_form_injection_into_ayah_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        def mutate(conn):
            # U+FE8E ARABIC LETTER ALEF FINAL FORM
            conn.execute("UPDATE ayah SET text = text || ? WHERE surah = 1 AND ayah = 3;", ("ﺎ",))
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P13", "P14", "P16")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_delete_one_ayah_row_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        def mutate(conn):
            # A middle ayah of a long surah, so the remaining numbers are
            # no longer contiguous (not the surah's last ayah, which would
            # leave a smaller-but-still-contiguous run).
            conn.execute("DELETE FROM ayah WHERE surah = 2 AND ayah = 100;")
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P7", "P8", "P9", "P10", "P16", "P20")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_blank_one_ayah_text_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        def mutate(conn):
            conn.execute("UPDATE ayah SET text = '' WHERE surah = 3 AND ayah = 5;")
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P11", "P16")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_change_one_letter_of_non_2_255_ayah_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        def mutate(conn):
            row = conn.execute("SELECT text FROM ayah WHERE surah = 5 AND ayah = 10;").fetchone()
            text = row[0]
            new_text = "ب" + text[1:]
            conn.execute("UPDATE ayah SET text = ? WHERE surah = 5 AND ayah = 10;", (new_text,))
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P16")
        assert statuses.get("P22") is True, (
            "P22 checks only 2:255 and this mutation left it untouched -- it should still PASS\n" + stdout
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_change_one_letter_of_2_255_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        def mutate(conn):
            row = conn.execute("SELECT text FROM ayah WHERE surah = 2 AND ayah = 255;").fetchone()
            text = row[0]
            new_text = "ب" + text[1:]
            conn.execute("UPDATE ayah SET text = ? WHERE surah = 2 AND ayah = 255;", (new_text,))
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P16", "P22")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_change_one_surah_ayah_count_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        def mutate(conn):
            conn.execute("UPDATE surah SET ayah_count = 999 WHERE id = 10;")
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P10", "P27")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_swap_name_en_and_name_tr_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        def mutate(conn):
            row = conn.execute("SELECT name_en, name_tr FROM surah WHERE id = 12;").fetchone()
            name_en, name_tr = row
            conn.execute("UPDATE surah SET name_en = ?, name_tr = ? WHERE id = 12;", (name_tr, name_en))
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P27")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_set_revelation_to_mecca_typo_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        def mutate(conn):
            conn.execute("UPDATE surah SET revelation = 'mecca' WHERE id = 20;")
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P25", "P27")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_flip_has_bismillah_on_surah_9_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        def mutate(conn):
            conn.execute("UPDATE surah SET has_bismillah = 1 WHERE id = 9;")
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P23")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_clear_one_sajdah_flag_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        def mutate(conn):
            conn.execute("UPDATE ayah SET sajdah = 0 WHERE surah = 7 AND ayah = 206;")
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P19")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_set_sajdah_on_ayah_with_no_mark_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        def mutate(conn):
            conn.execute("UPDATE ayah SET sajdah = 1 WHERE surah = 1 AND ayah = 1;")
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P19")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_shift_juz_boundary_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        def mutate(conn):
            # 17:50 sits squarely inside juz 15 (juz 15 runs 17:1-18:74;
            # juz 16 starts at 18:75), with juz-15 ayat on both sides.
            # Reassigning it back to juz 1 is a local decrease that breaks
            # "non-decreasing in (surah, ayah) order" -- unlike moving an
            # ayah right at a boundary by one position (which can still
            # look like a valid, merely-shifted partition), this creates a
            # 15 -> 1 -> 15 dip P20's monotonicity check must catch.
            conn.execute("UPDATE ayah SET juz = 1 WHERE surah = 17 AND ayah = 50;")
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P20")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_corrupt_meta_checksum_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        def mutate(conn):
            conn.execute("UPDATE meta SET value = 'deadbeef' WHERE key = 'checksum';")
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P17")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_corrupt_quran_db_sha256_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, DB_SHA_REL)
        write_bytes(path, b"0" * 64 + b"  quran.db\n")
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P24")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_corrupt_surah_meta_sha256_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, SURAH_META_SHA_REL)
        write_bytes(path, b"0" * 64 + b"  surah_meta.json\n")
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "C10", "P27")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_unicodedata_normalize_call_added_to_tools_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, BUILD_PACK_REL)
        src = read_bytes(path).decode("utf-8")
        src += "\n\n# test mutation\nimport unicodedata\n_x = unicodedata.normalize('NFC', 'a')\n"
        write_bytes(path, src.encode("utf-8"))
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "C4")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_main_lua_displaying_pin_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, MAIN_LUA_REL)
        src = read_bytes(path).decode("utf-8")
        assert src.rstrip().endswith("return Quran"), "test fixture assumption broken: main.lua does not end with 'return Quran'"
        mutated = src.rstrip()
        mutated = mutated[: -len("return Quran")] + "local text = PIN_2_255\n\nreturn Quran\n"
        write_bytes(path, mutated.encode("utf-8"))
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "C6")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Errata mechanism -- these exercise tools/build_pack.py directly, since
# check_m1.py never rebuilds the pack (it only checks already-built
# artefacts). Every mutation below still only ever copies bytes that are
# already present in the tree (from data/errata.tsv or
# data/quran-uthmani.txt) -- never retypes or constructs Arabic.
# ---------------------------------------------------------------------------

ERRATA_TSV_REL = os.path.join("data", "errata.tsv")


def test_errata_before_hash_mismatch_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, ERRATA_TSV_REL)
        text = read_bytes(path).decode("utf-8")
        # Corrupt the 'before' hash of the 95:1 row (first hex character
        # flipped) so it can never match sha256(current text) -- this is
        # exactly the "Tanzil already fixed it upstream" scenario the build
        # must refuse to silently paper over.
        mutated = text.replace("95\t1\tda9f21d0", "95\t1\tea9f21d0")
        assert mutated != text, "test fixture assumption broken: before-hash prefix not found"
        write_bytes(path, mutated.encode("utf-8"))
        code, stdout = run_build_pack(dst)
        assert code == 1, stdout
        assert "BUILD FAILED" in stdout, stdout
        assert "before" in stdout.lower(), stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_erratum_applied_twice_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, ERRATA_TSV_REL)
        text = read_bytes(path).decode("utf-8")
        lines = text.split("\n")
        data_lines = [l for l in lines if l and not l.startswith("#")]
        ninety_five = next(l for l in data_lines if l.startswith("95\t1\t"))
        # Duplicate the 95:1 row. The first application succeeds; the
        # second finds sha256(current) already equals 'after', not
        # 'before', and must fail -- never silently re-apply or no-op.
        mutated = text.rstrip("\n") + "\n" + ninety_five + "\n"
        write_bytes(path, mutated.encode("utf-8"))
        code, stdout = run_build_pack(dst)
        assert code == 1, stdout
        assert "BUILD FAILED" in stdout, stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_tampered_errata_tsv_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, ERRATA_TSV_REL)
        text = read_bytes(path).decode("utf-8")
        # Truncate the 95:1 row's 'after' hash to a malformed length --
        # structurally invalid, not just a wrong value.
        mutated = text.replace(
            "1e01f20fba7652508755f9808d04405f68116fd284c642b3abe6ebcea1e1eda6",
            "1e01f20f",
        )
        assert mutated != text, "test fixture assumption broken: after-hash not found"
        write_bytes(path, mutated.encode("utf-8"))
        code, stdout = run_build_pack(dst)
        assert code == 1, stdout
        assert "BUILD FAILED" in stdout, stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_pack_with_shadda_not_removed_is_caught():
    # Build cleanly, then tamper with the already-built db directly,
    # reverting 95:1 back to its pre-erratum (still-shadda'd) text -- the
    # exact bytes copied from data/quran-uthmani.txt (the vendored file
    # still legitimately carries the defect), never retyped. verify_pack.py
    # must catch this via P29 (and P16, since the pack-wide digest also
    # shifts).
    tmp, dst = make_mutant_copy()
    try:
        before_text = read_vendored_ayah(dst, 95, 1)

        def mutate(conn):
            conn.execute("UPDATE ayah SET text = ? WHERE surah = 95 AND ayah = 1;", (before_text,))
        mutate_db(dst, mutate)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "P16", "P29")
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
