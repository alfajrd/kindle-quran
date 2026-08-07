#!/usr/bin/env python3
"""Pure-Python reference model of the paging arithmetic in
`quran.koplugin/reader.lua`, run against the real `quran.db`.

This validates the algorithm, not the implementation. `quran.koplugin/
reader.lua` must mirror it step for step; `tools/check_m2.py` R9 is what
keeps them from drifting.

`linesOf` is synthetic here -- `ceil(codepoint_count(text) / chars_per_line)`,
minimum 1 -- because this machine cannot shape Arabic; the point is to
exercise the *arithmetic* over real ayah-length distributions, including
2:282, not to predict pixels.

Usage:
    python tools/paging_model.py [--root <repo root>]

Opens `quran.koplugin/data/quran.db` read-only, walks every surah
surah-by-surah from (1, 0) to its end at a fixed synthetic
`lines_per_screen`, and reports the total page count -- a smoke test that
the arithmetic terminates and produces a sane result over the real corpus.
The real invariants are asserted by `tests/test_paging_model.py`, not here.

Stdlib only. No network. No Lua execution.
"""
import argparse
import math
import os
import sqlite3
import sys

DEFAULT_CHARS_PER_LINE = 40
DEFAULT_LINES_PER_SCREEN = 20


# STEP W1
def line_count(text, chars_per_line):
    """Synthetic line count for `text` at `chars_per_line` columns -- ceil of
    codepoint count over columns, minimum 1 (an ayah can never be 0 lines)."""
    n = len(text)
    if chars_per_line <= 0:
        chars_per_line = 1
    return max(1, math.ceil(n / chars_per_line))


# STEP W2
def build_page_from(lines_of, ayah_count, ayah, line, lines_per_screen):
    budget = lines_per_screen
    a, l = ayah, line
    slices = []
    while budget > 0 and a <= ayah_count:
        n = lines_of(a) - l
        if n <= 0:
            a += 1
            l = 0
        else:
            take = min(n, budget)
            slices.append({"ayah": a, "first_line": l, "n_lines": take})
            budget -= take
            if take == n:
                a += 1
                l = 0
            else:
                l += take
    return {"slices": slices, "total_lines": lines_per_screen - budget}, a, l


# STEP W3
def top_of_previous_page(lines_of, ayah, line, lines_per_screen):
    budget = lines_per_screen
    a, l = ayah, line
    while budget > 0:
        if l > 0:
            take = min(budget, l)
            l -= take
            budget -= take
        elif a > 1:
            a -= 1
            l = lines_of(a)
        else:
            break
    return a, l


def open_db(root):
    db_path = os.path.join(root, "quran.koplugin", "data", "quran.db")
    return sqlite3.connect("file:%s?mode=ro" % db_path.replace("\\", "/"), uri=True)


def load_all_ayahs(conn):
    """surah -> {ayah_number: text}, one query, no per-ayah round trips."""
    rows = conn.execute("SELECT surah, ayah, text FROM ayah ORDER BY surah, ayah;").fetchall()
    data = {}
    for surah, ayah, text in rows:
        data.setdefault(surah, {})[ayah] = text
    return data


def load_ayah_counts(conn):
    return dict(conn.execute("SELECT id, ayah_count FROM surah;").fetchall())


def make_lines_of(ayah_texts, chars_per_line):
    cache = {}

    def lines_of(ayah):
        if ayah in cache:
            return cache[ayah]
        text = ayah_texts.get(ayah, "")
        n = line_count(text, chars_per_line)
        cache[ayah] = n
        return n

    return lines_of


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    default_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument("--root", default=default_root, help="path to kindle-quran/ (default: %(default)s)")
    args = parser.parse_args()
    root = os.path.abspath(args.root)

    conn = open_db(root)
    try:
        all_ayahs = load_all_ayahs(conn)
        ayah_counts = load_ayah_counts(conn)
    finally:
        conn.close()

    total_pages = 0
    for surah in range(1, 115):
        ayah_count = ayah_counts.get(surah, 0)
        lines_of = make_lines_of(all_ayahs.get(surah, {}), DEFAULT_CHARS_PER_LINE)
        a, l = 1, 0
        pages = 0
        while a <= ayah_count:
            _page, a, l = build_page_from(lines_of, ayah_count, a, l, DEFAULT_LINES_PER_SCREEN)
            pages += 1
        total_pages += pages

    print("paging_model: walked all 114 surahs, %d total page(s) at lines_per_screen=%d, chars_per_line=%d" % (
        total_pages, DEFAULT_LINES_PER_SCREEN, DEFAULT_CHARS_PER_LINE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
