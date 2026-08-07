#!/usr/bin/env python3
"""Durable regression tests for `kindle-quran/tools/check_m0.py`.

These tests do NOT re-run `check_m0.py` and trust it. Each test builds a
deliberately corrupted COPY of `kindle-quran/` in a throwaway temp directory,
runs the real, unmodified `check_m0.py` against that copy (`--root <copy>`),
and asserts that it FAILS -- and, wherever the outcome is deterministic,
asserts exactly which check id(s) caught the corruption. A mutation that
`check_m0.py` does not catch is a test failure here, by design: this suite
exists so that a future edit which silently weakens `check_m0.py` (e.g.
loosening a codepoint range, dropping an assertion, "fixing" a check to make
a bad artefact pass) has something that will notice and fail loudly.

None of this ever touches the real repository tree. Every mutation happens
on a `tempfile.mkdtemp()` copy, and every test removes its own temp directory
in a `finally` block, including any `__pycache__` that might appear inside it
(there should not be any -- the checker script is invoked as a subprocess,
never imported -- but the cleanup is unconditional regardless).

KNOWN LIMITATION -- READ BEFORE TRUSTING THIS SUITE AS CONTENT AUTHENTICATION
------------------------------------------------------------------------
`check_m0.py`'s Arabic-text checks (A1-A12) were mutation-tested by hand
during the M0 test-layer review (see `.pipeline/test-results.md`, section 2)
against mutations applied to ONE of the three copies of the verse at a time
(`data/2_255.txt`, the embedded literal in `main.lua`, or `data/2_255.sha256`)
while leaving the other two at their original, correct bytes. Every such
single-copy mutation is caught -- by A2 (byte-identity between the literal
and `data/2_255.txt`), by A3 (sha256 match), or by one of the structural
checks A4-A12, and this file exercises exactly that: BOM, CRLF, NFC
normalisation, tatweel deletion, a letter swap, a stripped combining mark,
truncation, presentation-form injection, and literal-vs-txt drift, are all
applied to a single artefact and are all caught below.

BUT: if `data/2_255.txt`, the `main.lua` literal, AND `data/2_255.sha256`
are all regenerated TOGETHER from the same corrupted text (e.g. someone runs
the whole verse through `unicodedata.normalize("NFC", ...)`, or retypes one
letter, and then re-copies that same wrong text into all three places and
re-hashes it) -- `check_m0.py` passes all 31 checks. A2/A3 only prove
internal self-consistency between the three copies IN THIS REPO; they do not
and cannot prove the text still matches Tanzil. This is not a defect in
`check_m0.py`, and it is not something this test suite (or any purely
structural/statistical check) can close -- it is already documented in
`kindle-quran/quran.koplugin/data/SOURCE.md` and in `spec.md`'s own "A-hash"
assumption. The actual mitigation is a human `git diff` of the Arabic bytes
in `data/2_255.txt` against `.pipeline/ayah_2_255.txt` at merge/review time.
Nobody should mistake "this test suite passes" or "check_m0.py passes" for
proof that the Arabic text is still byte-correct against Tanzil -- only a
byte-for-byte diff against the known-good source, by a human, does that.

Usage:
    python kindle-quran/tests/test_check_m0.py
    (from the repo root, or any cwd -- paths are resolved from this file's
    location, not from cwd)

Also runnable under pytest (`pytest kindle-quran/tests/test_check_m0.py`),
but pytest is NOT required -- every test is a plain `test_*` function using
bare `assert`, and `main()` below discovers and runs them without it.

Stdlib only. No network. No Lua execution -- exactly like `check_m0.py`
itself, this suite only ever shells out to `check_m0.py`, which does not
execute Lua either.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

# kindle-quran/ -- the directory this tests/ folder lives in.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK_SCRIPT = os.path.join(REPO_ROOT, "tools", "check_m0.py")

TXT_REL = os.path.join("quran.koplugin", "data", "2_255.txt")
MAIN_LUA_REL = os.path.join("quran.koplugin", "main.lua")
SHA_REL = os.path.join("quran.koplugin", "data", "2_255.sha256")
MENU_JSON_REL = os.path.join("extensions", "quran", "menu.json")
CONFIG_XML_REL = os.path.join("extensions", "quran", "config.xml")
QURAN_SH_REL = os.path.join("extensions", "quran", "bin", "quran.sh")

BEGIN_MARKER = "-- BEGIN VERBATIM TANZIL UTHMANI 2:255 -- DO NOT EDIT, DO NOT NORMALISE, DO NOT REFLOW"
END_MARKER = "-- END VERBATIM"
LITERAL_RE = re.compile(r"\[==\[(.*?)\]==\]", re.DOTALL)


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
    """Copies the whole kindle-quran/ tree into a fresh temp directory.
    Returns (tempdir_to_remove, path_to_the_kindle-quran_copy)."""
    tmp = tempfile.mkdtemp(prefix="check_m0_test_")
    dst = os.path.join(tmp, "kindle-quran")
    shutil.copytree(
        REPO_ROOT,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return tmp, dst


def run_checker(root):
    """Runs the REAL, unmodified tools/check_m0.py (from the actual repo,
    never a copy) against `--root <root>`. Returns (returncode, {id: bool}, stdout)."""
    proc = subprocess.run(
        [sys.executable, CHECK_SCRIPT, "--root", root],
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


def mutate_txt_only(dst_root, transform):
    """Applies `transform(text: str) -> str` to data/2_255.txt ONLY, leaving
    the main.lua literal and the .sha256 file at their original, correct
    bytes -- simulating a single-copy edit."""
    path = os.path.join(dst_root, TXT_REL)
    text = read_bytes(path).decode("utf-8").strip()
    new_text = transform(text)
    write_bytes(path, new_text.encode("utf-8"))


def mutate_main_lua_literal_only(dst_root, transform):
    """Applies `transform(text: str) -> str` to the embedded [==[ ]==]
    literal inside main.lua ONLY, leaving data/2_255.txt and the .sha256
    file untouched."""
    path = os.path.join(dst_root, MAIN_LUA_REL)
    src = read_bytes(path).decode("utf-8")
    begin_idx = src.index(BEGIN_MARKER)
    end_idx = src.index(END_MARKER)
    between = src[begin_idx + len(BEGIN_MARKER):end_idx]
    m = LITERAL_RE.search(between)
    assert m is not None, "test fixture assumption broken: no [==[ ]==] literal found"
    inner = m.group(1)
    new_inner = transform(inner)
    new_between = between[:m.start(1)] + new_inner + between[m.end(1):]
    new_src = src[:begin_idx + len(BEGIN_MARKER)] + new_between + src[end_idx:]
    write_bytes(path, new_src.encode("utf-8"))


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
        assert len(statuses) == 31, "expected 31 checks to be reported, got %d\n%s" % (len(statuses), stdout)
        assert all(statuses.values()), "expected every check to PASS on an unmodified copy\n%s" % stdout
        assert "RESULT: PASS (31 checks)" in stdout, stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_bom_injection_into_txt_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, TXT_REL)
        write_bytes(path, b"\xef\xbb\xbf" + read_bytes(path))
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "E2", "A2", "A3", "A5", "A6-presentation-forms")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_crlf_in_quran_sh_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, QURAN_SH_REL)
        write_bytes(path, read_bytes(path).replace(b"\n", b"\r\n"))
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "E3", "E4")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_nfc_normalisation_of_txt_only_is_caught():
    """NFC-normalising ONLY data/2_255.txt (leaving the main.lua literal and
    the .sha256 file at their original bytes) is caught by the byte-identity
    / hash checks, NOT by any structural check -- see the module docstring's
    "KNOWN LIMITATION" for what happens if all three copies are normalised
    together instead of just this one."""
    tmp, dst = make_mutant_copy()
    try:
        mutate_txt_only(dst, lambda t: unicodedata.normalize("NFC", t))
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "A2", "A3")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_tatweel_deletion_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        mutate_txt_only(dst, lambda t: t.replace("ـ", "", 1))
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "A2", "A3", "A6-tatweel")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_letter_swap_is_caught_by_identity_checks():
    """A single base-letter substitution elsewhere in the text (away from
    any tracked shadda/wasla/superscript-alef/tatweel/lam-alef site) is NOT
    caught by any structural check (A4-A12) -- only by the exact
    byte-identity checks A2/A3, and only because the swap happened in one
    copy only here. This is exactly why A2/A3 exist, and exactly the gap the
    module docstring's "KNOWN LIMITATION" describes if all copies drift
    together instead."""
    tmp, dst = make_mutant_copy()
    try:
        def swap(t):
            idx = t.find("ع")  # ARABIC LETTER AIN
            assert idx != -1, "test fixture assumption broken: no ain in the verse"
            return t[:idx] + "غ" + t[idx + 1:]  # ARABIC LETTER GHAIN
        mutate_txt_only(dst, swap)
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "A2", "A3")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_alef_wasla_mark_stripped_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        mutate_txt_only(dst, lambda t: t.replace("ٱ", ""))
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "A2", "A3", "A10")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_truncation_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        mutate_txt_only(dst, lambda t: t[:100])
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "A2", "A3", "A12")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_presentation_form_substitution_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        # U+FE8E ARABIC LETTER ALEF FINAL FORM -- a pre-shaped, visual-order
        # presentation-form codepoint; the kind of thing A6 exists to reject.
        mutate_txt_only(dst, lambda t: t + "ﺎ")
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "A2", "A3", "A5", "A6-presentation-forms")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_broken_menu_json_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        write_bytes(os.path.join(dst, MENU_JSON_REL), b"{ this is not valid json")
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "M1")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_broken_config_xml_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        write_bytes(os.path.join(dst, CONFIG_XML_REL), b"<information><unclosed>")
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "M2")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_unparseable_main_lua_is_caught():
    tmp, dst = make_mutant_copy()
    try:
        path = os.path.join(dst, MAIN_LUA_REL)
        write_bytes(path, read_bytes(path) + b"\nfunction broken( (\n")
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "L2", "L6")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_main_lua_literal_drift_from_txt_is_caught():
    """Editing ONLY the embedded [==[ ]==] literal in main.lua (not
    data/2_255.txt, not the .sha256) must be caught by A2 -- this is the
    spec's named anti-drift assertion ("a coder who 'fixes' one copy breaks
    the build")."""
    tmp, dst = make_mutant_copy()
    try:
        mutate_main_lua_literal_only(dst, lambda t: t[:-1])  # drop the last character
        code, statuses, stdout = run_checker(dst)
        assert code == 1, stdout
        assert_failed(statuses, stdout, "A2")
        # A3 is computed purely from data/2_255.txt, which this mutation
        # never touched -- it must still PASS. If it doesn't, this test's
        # isolation assumption (that only the literal was changed) is wrong.
        assert statuses.get("A3") is True, (
            "A3 should still PASS: it is computed from data/2_255.txt, "
            "which this mutation left untouched\n" + stdout
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
