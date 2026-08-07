#!/usr/bin/env python3
"""Invariant tests for `tools/paging_model.py` -- forward/back are exact
inverses, no line lost or repeated, over the real `quran.db`.

Same discipline as `tests/test_check_m0.py` / `tests/test_check_m1.py`:
plain `test_*` functions, bare `assert`, `main()` discovers and runs them
without pytest. This suite imports `tools/paging_model.py` directly (it
does not shell out to it) -- unlike `tests/test_check_m2.py`, which must
run the real `check_m2.py` as a subprocess to test its CLI behaviour,
there is no CLI behaviour to test here, only the three pure functions.

Usage:
    python kindle-quran/tests/test_paging_model.py

Stdlib only. No network. No Lua execution.
"""

import os
import sqlite3
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))
import paging_model  # noqa: E402  (path insert must happen first)

DB_PATH = os.path.join(REPO_ROOT, "quran.koplugin", "data", "quran.db")


# ---------------------------------------------------------------------------
# Shared fixtures -- loaded once, real corpus, no Arabic retyped or altered.
# ---------------------------------------------------------------------------

def _load():
    conn = sqlite3.connect("file:%s?mode=ro" % DB_PATH.replace("\\", "/"), uri=True)
    try:
        all_ayahs = paging_model.load_all_ayahs(conn)
        ayah_counts = paging_model.load_ayah_counts(conn)
    finally:
        conn.close()
    return all_ayahs, ayah_counts


ALL_AYAHS, AYAH_COUNTS = _load()


def lines_of_for(surah, chars_per_line=40):
    return paging_model.make_lines_of(ALL_AYAHS.get(surah, {}), chars_per_line)


def walk_forward(surah, lines_per_screen, chars_per_line=40, start=(1, 0)):
    """Walks every forward page of `surah` from `start` to its end. Returns
    a list of (top_ayah, top_line, page, next_ayah, next_line) tuples, one
    per page, in order."""
    ayah_count = AYAH_COUNTS[surah]
    lines_of = lines_of_for(surah, chars_per_line)
    a, l = start
    pages = []
    # Bounded: a page always consumes at least one line (linesOf >= 1), so
    # this cannot loop more than there are lines in the surah.
    guard = 0
    guard_limit = sum(lines_of(x) for x in range(1, ayah_count + 1)) + 10
    while a <= ayah_count:
        page, next_a, next_l = paging_model.build_page_from(lines_of, ayah_count, a, l, lines_per_screen)
        pages.append((a, l, page, next_a, next_l))
        a, l = next_a, next_l
        guard += 1
        assert guard <= guard_limit, "walk_forward did not terminate for surah %d" % surah
    return pages


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_forward_then_back_is_identity():
    # A representative spread: shortest surahs, the longest surah (2, with
    # 2:282), a mid-length one, and the last surah -- at a small
    # lines_per_screen so each surah produces several pages worth of start
    # positions to exercise.
    #
    # "next" is only a *reachable* page top for pages before the last one --
    # the final page's "next" is a beyond-the-surah sentinel (ayah >
    # ayah_count) that real navigation never turns into a page top (NEXT on
    # the last page shows the "End of surah" toast instead of advancing
    # there, per D1/D10). The identity is only claimed, and only holds, for
    # reachable page tops -- see `.pipeline/spec.md` §6.2.
    for surah in (1, 2, 9, 18, 67, 112, 113, 114):
        ayah_count = AYAH_COUNTS[surah]
        lines_of = lines_of_for(surah)
        pages = walk_forward(surah, lines_per_screen=5)
        assert pages, "surah %d produced no pages" % surah
        for (top_a, top_l, _page, next_a, next_l) in pages:
            if next_a > ayah_count:
                continue
            back_a, back_l = paging_model.top_of_previous_page(lines_of, next_a, next_l, lines_per_screen=5)
            assert (back_a, back_l) == (top_a, top_l), (
                "surah %d: top_of_previous_page(build_page_from(%d, %d).next) = (%d, %d), expected (%d, %d)"
                % (surah, top_a, top_l, back_a, back_l, top_a, top_l)
            )


def test_forward_pass_covers_every_line_exactly_once():
    for surah in (1, 2, 9, 18, 67, 112, 113, 114):
        ayah_count = AYAH_COUNTS[surah]
        lines_of = lines_of_for(surah)
        expected = []
        for a in range(1, ayah_count + 1):
            for l in range(lines_of(a)):
                expected.append((a, l))

        pages = walk_forward(surah, lines_per_screen=5)
        actual = []
        for (_top_a, _top_l, page, _next_a, _next_l) in pages:
            for slice_ in page["slices"]:
                a = slice_["ayah"]
                for l in range(slice_["first_line"], slice_["first_line"] + slice_["n_lines"]):
                    actual.append((a, l))

        assert actual == expected, "surah %d: forward pass did not cover every line exactly once, in order" % surah


def test_no_empty_page_before_end_of_surah():
    for surah in (1, 2, 9, 18, 67, 112, 113, 114):
        pages = walk_forward(surah, lines_per_screen=5)
        for i, (_top_a, _top_l, page, _next_a, _next_l) in enumerate(pages):
            if i < len(pages) - 1:
                assert page["total_lines"] == 5, (
                    "surah %d page %d: total_lines=%d, expected the full lines_per_screen=5 (not the last page)"
                    % (surah, i, page["total_lines"])
                )


def test_ayah_longer_than_a_screen_splits_and_reassembles():
    # 2:282 is the longest ayah in the corpus by a wide margin. At a small
    # lines_per_screen it must span multiple pages and reassemble with no
    # line lost or repeated.
    surah = 2
    lines_of = lines_of_for(surah)
    n_282 = lines_of(282)
    assert n_282 > 3, "test fixture assumption broken: 2:282 is not long enough to exercise a split (got %d lines)" % n_282

    lines_per_screen = 3
    ayah_count = AYAH_COUNTS[surah]
    pages = walk_forward(surah, lines_per_screen=lines_per_screen)

    # Every occupied (ayah=282, line) index appears exactly once, across
    # possibly several pages, in ascending line order.
    lines_282 = []
    for (_top_a, _top_l, page, _next_a, _next_l) in pages:
        for slice_ in page["slices"]:
            if slice_["ayah"] == 282:
                for l in range(slice_["first_line"], slice_["first_line"] + slice_["n_lines"]):
                    lines_282.append(l)
    assert lines_282 == list(range(n_282)), (
        "2:282 (%d lines) did not reassemble cleanly across pages at lines_per_screen=%d: got %r"
        % (n_282, lines_per_screen, lines_282)
    )
    assert len(pages) > 1, "expected surah 2 to need more than one page at lines_per_screen=%d" % lines_per_screen
    del ayah_count  # not otherwise used; kept for readability of the setup above


def test_lines_per_screen_of_one():
    # The degenerate case: one line per page. Must terminate and stay an
    # exact forward/back inverse for a short surah (excluding the last
    # page's "next", which is a beyond-the-surah sentinel -- see the note
    # in test_forward_then_back_is_identity).
    surah = 114
    ayah_count = AYAH_COUNTS[surah]
    lines_of = lines_of_for(surah)
    pages = walk_forward(surah, lines_per_screen=1)
    assert pages, "surah 114 produced no pages at lines_per_screen=1"
    for (top_a, top_l, page, next_a, next_l) in pages:
        assert page["total_lines"] <= 1
        if next_a > ayah_count:
            continue
        back_a, back_l = paging_model.top_of_previous_page(lines_of, next_a, next_l, lines_per_screen=1)
        assert (back_a, back_l) == (top_a, top_l)


def test_backward_clamps_at_start_of_surah():
    for lines_per_screen in (1, 3, 5, 20):
        for surah in (1, 2, 114):
            lines_of = lines_of_for(surah)
            a, l = paging_model.top_of_previous_page(lines_of, 1, 0, lines_per_screen)
            assert (a, l) == (1, 0), (
                "surah %d, lines_per_screen=%d: top_of_previous_page(1, 0) = (%d, %d), expected (1, 0)"
                % (surah, lines_per_screen, a, l)
            )
            assert a >= 1 and l >= 0


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
