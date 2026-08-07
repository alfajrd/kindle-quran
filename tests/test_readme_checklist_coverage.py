#!/usr/bin/env python3
"""Coverage audit of README.md's "Milestone 2 -- on-device checklist"
(D1-D12) against spec.md §11's named edge cases.

This is not a test of `check_m2.py` (R10 already proves D1..D12 exist as
table rows) -- it is a test of whether the checklist, if followed exactly
as written, would ever put a human tester's eyes on two specific things
spec.md itself calls out as risk: 2:282 (edge case 2, "a single ayah longer
than one screen ... 2:282 is the case, test it") and the min/max font-size
button going inert without erroring (edge case 15).

Uses `tools/paging_model.py`'s real arithmetic over the real corpus to make
the 2:282 claim a computed fact, not a guess. Never mutates the repo tree,
never touches implementation code.

Usage:
    python kindle-quran/tests/test_readme_checklist_coverage.py
"""

import os
import re
import sqlite3
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
import paging_model  # noqa: E402

README_PATH = os.path.join(REPO_ROOT, "README.md")
DB_PATH = os.path.join(REPO_ROOT, "quran.koplugin", "data", "quran.db")


def _load():
    conn = sqlite3.connect("file:%s?mode=ro" % DB_PATH.replace("\\", "/"), uri=True)
    try:
        all_ayahs = paging_model.load_all_ayahs(conn)
        ayah_counts = paging_model.load_ayah_counts(conn)
    finally:
        conn.close()
    return all_ayahs, ayah_counts


ALL_AYAHS, AYAH_COUNTS = _load()


def _readme_d_section():
    src = open(README_PATH, encoding="utf-8").read()
    heading = "## Milestone 2 — on-device checklist"
    assert heading in src
    section = src[src.index(heading):]
    nxt = re.search(r"\n## ", section[1:])
    if nxt:
        section = section[:nxt.start() + 1]
    return section


def test_d5_d6_five_taps_never_reaches_2_282_at_any_plausible_lines_per_screen():
    # D5/D6 (README.md): "Open 'read Al-Baqara (2)'. Tap right five times.
    # ... Tap left five times." That is the ENTIRE on-device exercise of
    # surah 2's paging. spec.md §11 edge case 2 explicitly names 2:282 as
    # "the case, test it" for an ayah longer than one screen splitting and
    # reassembling across pages. This test proves, over a wide plausible
    # range of `lines_per_screen` (the on-device value depends on the
    # tester's font size, unknown here, but §10's "~20 lines" estimate and
    # the min/max font sizes bound it), that five forward taps from the
    # start of surah 2 never gets anywhere near ayah 282 (near the very end
    # of a 286-ayah surah) -- so D5/D6 as written cannot be the on-device
    # confirmation of edge case 2, no matter how carefully a tester follows
    # them. Some other, currently-undocumented on-device step is needed to
    # actually exercise 2:282's split/reassembly on a real device.
    surah = 2
    ayah_count = AYAH_COUNTS[surah]
    lines_of = paging_model.make_lines_of(ALL_AYAHS[surah], 40)
    for lines_per_screen in (10, 15, 20, 25, 30, 40):
        a, l = 1, 0
        for _tap in range(5):
            if a > ayah_count:
                break
            _page, a, l = paging_model.build_page_from(lines_of, ayah_count, a, l, lines_per_screen)
        assert a < 282, (
            "lines_per_screen=%d: five forward taps from 2:1 already reached ayah %d -- "
            "if this ever becomes >= 282, revisit this finding, it may no longer hold"
            % (lines_per_screen, a)
        )


def test_d7_does_not_mention_exercising_the_font_size_min_or_max_limit():
    # spec.md §11 edge case 15: "Font size at its min or max: the
    # corresponding button is inert, not an error, and does not close the
    # dialog." D7 as written only says "Raise Arabic size twice" -- with
    # the default 34 and a step of 2, two raises lands at 38, nowhere near
    # the max of 60 (13 steps away) or the min of 26. No D-item's text
    # mentions pushing a control to its limit. This is a real, uncovered
    # edge case in the on-device checklist as written (not a bug in the
    # implementation -- see reader.lua's `font_minus_cb`/`font_plus_cb`
    # nil-when-at-limit logic, which does implement edge case 15 correctly;
    # it is simply never exercised by the ten-minute checklist).
    section = _readme_d_section()
    d7_match = re.search(r"\|\s*D7\s*\|(.*)\|", section)
    assert d7_match, "D7 row not found"
    d7_text = d7_match.group(0).lower()
    limit_words = ("min", "max", "inert", "limit", "60", "26")
    mentioned = [w for w in limit_words if w in d7_text]
    assert not mentioned, (
        "D7's text now mentions %r -- if the checklist has been extended to exercise the "
        "font-size limit, update this test and test-results.md" % mentioned
    )


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
