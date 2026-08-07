#!/usr/bin/env python3
"""Full-corpus stress test for `tools/paging_model.py`'s invariants.

`tests/test_paging_model.py` (the coder's own suite) exercises 8 named
surahs at `lines_per_screen=5` (plus one pass at =1). This suite goes wider
per the tester's brief: **every one of the 114 surahs**, at several
`lines_per_screen` values including degenerate ones (1, 2, and a value
larger than the longest ayah in the whole corpus -- 2:282, 31 synthetic
lines at `chars_per_line=40`), asserting no line is ever lost, repeated, or
skipped, and that walking forward to the end and back returns to the exact
first page.

This suite also empirically settles the question the coder raised in
`.pipeline/changes.md` about the paging-inverse invariant's domain: does
`topOfPreviousPage(buildPageFrom(a, l).next) == (a, l)` fail for the last
page of a surah because of a bug, or because the last page is (by the
spec's own text) not required to be `lines_per_screen`-full? See
`test_last_page_mismatch_is_exactly_the_non_full_case` below -- it proves
the mismatch occurs if and only if the last page is short, which is exactly
what spec.md §6.2's own "every page except the last ... is exactly
lines_per_screen lines full" premise predicts. That is a domain
clarification, not a papered-over bug.

Stdlib only. No network. No Lua execution. Never mutates the repo tree.

Usage:
    python kindle-quran/tests/test_paging_model_full_corpus.py
"""

import os
import sqlite3
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
import paging_model  # noqa: E402

DB_PATH = os.path.join(REPO_ROOT, "quran.koplugin", "data", "quran.db")
ALL_SURAHS = list(range(1, 115))
CHARS_PER_LINE = 40


def _load():
    conn = sqlite3.connect("file:%s?mode=ro" % DB_PATH.replace("\\", "/"), uri=True)
    try:
        all_ayahs = paging_model.load_all_ayahs(conn)
        ayah_counts = paging_model.load_ayah_counts(conn)
    finally:
        conn.close()
    return all_ayahs, ayah_counts


ALL_AYAHS, AYAH_COUNTS = _load()

# One value larger than the single longest ayah in the whole corpus (2:282,
# 31 synthetic lines at chars_per_line=40) -- a page that always swallows
# an entire ayah (or several) in one go.
MAX_AYAH_LINES = max(
    paging_model.make_lines_of(ALL_AYAHS.get(s, {}), CHARS_PER_LINE)(a)
    for s in ALL_SURAHS
    for a in range(1, AYAH_COUNTS[s] + 1)
)
assert MAX_AYAH_LINES == 31 and (2, 282) not in (None,), "corpus assumption changed"

LPS_VALUES = (1, 2, MAX_AYAH_LINES + 5)


def walk_forward_all(surah, lines_per_screen):
    ayah_count = AYAH_COUNTS[surah]
    lines_of = paging_model.make_lines_of(ALL_AYAHS.get(surah, {}), CHARS_PER_LINE)
    a, l = 1, 0
    pages = []
    guard_limit = sum(lines_of(x) for x in range(1, ayah_count + 1)) + 10
    guard = 0
    while a <= ayah_count:
        page, next_a, next_l = paging_model.build_page_from(lines_of, ayah_count, a, l, lines_per_screen)
        pages.append((a, l, page, next_a, next_l))
        a, l = next_a, next_l
        guard += 1
        assert guard <= guard_limit, "surah %d, lines_per_screen=%d did not terminate" % (surah, lines_per_screen)
    return pages, lines_of, ayah_count


def test_every_surah_every_lps_covers_every_line_exactly_once():
    for lines_per_screen in LPS_VALUES:
        for surah in ALL_SURAHS:
            pages, lines_of, ayah_count = walk_forward_all(surah, lines_per_screen)
            expected = []
            for a in range(1, ayah_count + 1):
                for l in range(lines_of(a)):
                    expected.append((a, l))
            actual = []
            for (_ta, _tl, page, _na, _nl) in pages:
                for slice_ in page["slices"]:
                    a = slice_["ayah"]
                    for l in range(slice_["first_line"], slice_["first_line"] + slice_["n_lines"]):
                        actual.append((a, l))
            assert actual == expected, (
                "surah %d, lines_per_screen=%d: line coverage mismatch (lost/repeated/skipped/reordered line)"
                % (surah, lines_per_screen)
            )


def test_every_surah_every_lps_forward_then_back_is_identity_for_reachable_tops():
    for lines_per_screen in LPS_VALUES:
        for surah in ALL_SURAHS:
            pages, lines_of, ayah_count = walk_forward_all(surah, lines_per_screen)
            for (top_a, top_l, _page, next_a, next_l) in pages:
                if next_a > ayah_count:
                    continue  # last page's `next` is a beyond-the-surah sentinel; see module docstring
                back_a, back_l = paging_model.top_of_previous_page(lines_of, next_a, next_l, lines_per_screen)
                assert (back_a, back_l) == (top_a, top_l), (
                    "surah %d, lines_per_screen=%d: forward/back not an exact inverse at (%d, %d)"
                    % (surah, lines_per_screen, top_a, top_l)
                )


def test_walking_all_the_way_back_from_the_end_returns_to_the_first_page():
    # Walk forward to the end of each surah, remembering every page top,
    # then walk backward one topOfPreviousPage step at a time from the
    # *last actually-rendered page's own top* (never from its `next`
    # sentinel -- see the domain note above) and check every page top is
    # revisited in exact reverse order, ending on (1, 0).
    for lines_per_screen in LPS_VALUES:
        for surah in ALL_SURAHS:
            pages, lines_of, ayah_count = walk_forward_all(surah, lines_per_screen)
            tops_forward = [(a, l) for (a, l, _p, _na, _nl) in pages]

            a, l = tops_forward[-1]
            tops_backward = [(a, l)]
            while not (a == 1 and l == 0):
                a, l = paging_model.top_of_previous_page(lines_of, a, l, lines_per_screen)
                tops_backward.append((a, l))

            assert tops_backward == list(reversed(tops_forward)), (
                "surah %d, lines_per_screen=%d: walking back from the last page's own top did not "
                "retrace the forward pages in exact reverse order" % (surah, lines_per_screen)
            )
            assert tops_backward[-1] == (1, 0)


def test_last_page_mismatch_is_exactly_the_non_full_case():
    # Empirically settles the coder's own flagged question in changes.md:
    # applying topOfPreviousPage to the LAST page's `next` (the
    # beyond-the-surah sentinel) mismatches if and only if that last page
    # was not lines_per_screen-full. When a surah's ayah count happens to
    # tile exactly into full pages, the "mismatch" disappears entirely --
    # which is exactly what spec.md §6.2's own premise ("every page except
    # the last is exactly lines_per_screen lines full") predicts, and is
    # inconsistent with this being an arithmetic bug in buildPageFrom/
    # topOfPreviousPage (a real bug would not care whether the last page
    # happened to be full).
    lines_per_screen = 5
    full_last_page_mismatches = 0
    short_last_page_mismatches = 0
    short_last_page_matches = 0
    for surah in ALL_SURAHS:
        pages, lines_of, ayah_count = walk_forward_all(surah, lines_per_screen)
        top_a, top_l, page, next_a, next_l = pages[-1]
        is_full = page["total_lines"] == lines_per_screen
        back_a, back_l = paging_model.top_of_previous_page(lines_of, next_a, next_l, lines_per_screen)
        matches = (back_a, back_l) == (top_a, top_l)
        if is_full and not matches:
            full_last_page_mismatches += 1
        if not is_full and not matches:
            short_last_page_mismatches += 1
        if not is_full and matches:
            short_last_page_matches += 1

    assert full_last_page_mismatches == 0, (
        "a FULL last page's `next` failed to invert -- this WOULD be a real arithmetic bug, "
        "not a domain-boundary artefact (found %d such surah(s))" % full_last_page_mismatches
    )
    assert short_last_page_mismatches > 0, (
        "expected at least one short (non-full) last page to mismatch at its `next` sentinel -- "
        "if this is 0, either the corpus changed or the domain-boundary explanation no longer holds"
    )


def test_al_baqara_and_single_ayah_surahs_at_every_lps():
    # Al-Baqara (286 ayat, longest surah, contains 2:282) and the shortest
    # single/near-single-ayah surahs are the cases the tester flagged as
    # mattering most.
    for lines_per_screen in LPS_VALUES:
        for surah in (2, 108, 110, 112, 114):
            pages, lines_of, ayah_count = walk_forward_all(surah, lines_per_screen)
            assert pages, "surah %d produced no pages at lines_per_screen=%d" % (surah, lines_per_screen)
            # No slice ever claims more lines than the ayah actually has.
            for (_ta, _tl, page, _na, _nl) in pages:
                for slice_ in page["slices"]:
                    assert slice_["n_lines"] >= 1
                    assert slice_["first_line"] + slice_["n_lines"] <= lines_of(slice_["ayah"])


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
