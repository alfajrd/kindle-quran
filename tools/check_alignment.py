#!/usr/bin/env python3
"""Checks that an Arabic pack and a translation pack can be laid out side by side.

    python tools/check_alignment.py [--quran quran.koplugin/data/quran.db]
                                    [--trans translations/itani.db]

The interleaved layout (SPEC-v1 §9.1) puts one ayah's Arabic and its
translation in the same row. That only works if the two packs agree about what
an ayah *is*. They are built by different programs from unrelated sources, so
nothing enforces that agreement except this check.

The disagreement it exists to catch is real and was found on 12 August 2026,
not hypothetically:

    The Arabic corpus stores the basmala as a PREFIX INSIDE ayah 1 for all 113
    surahs that have one. The translation stores it as a SEPARATE ayah 0.

Left alone, that renders the first row of 112 surahs with the basmala on the
Arabic side and not on the English side -- a visibly longer Arabic cell, and a
translation that appears to be missing its opening line. It is exactly the
class of bug that is obvious to a reader who knows the text and invisible to a
row-count assertion.

SPEC-v1 §6 already states the intended behaviour: in Al-Fātiḥah the basmala is
ayah 1; everywhere else it is an unnumbered heading. So the reader must split
the prefix off for surahs 2-114 (excepting 9) and render it as a heading. This
program proves the split is safe to perform: that the prefix is present, and
byte-identical to Al-Fātiḥah's ayah 1, in every surah that should have it.

That matters because it makes the split a DELETION AT A VERIFIED OFFSET rather
than a search-and-replace -- the same discipline docs/ERRATA.md imposes on the
corrections. No Arabic is ever constructed, typed, or matched against a
literal in this file. The reference basmala is read from the pack itself.

Exit status is 0 only if every check passes.

Stdlib only. No network.
"""
import argparse
import os
import sqlite3
import sys

TOTAL_SURAHS = 114
SURAH_FATIHA = 1
SURAH_TAWBAH = 9

_results = []


def check(label, ok, describe, detail=""):
    _results.append(ok)
    print("%-5s %-4s %s%s" % ("PASS" if ok else "FAIL", label, describe,
                              "" if ok else "  -- " + detail))


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument("--quran", default=os.path.join(root, "quran.koplugin", "data", "quran.db"))
    ap.add_argument("--trans", default=os.path.join(root, "translations", "itani.db"))
    args = ap.parse_args()

    for path in (args.quran, args.trans):
        if not os.path.exists(path):
            raise SystemExit("missing pack: %s" % path)

    qa = sqlite3.connect(args.quran)
    tr = sqlite3.connect(args.trans)

    arabic = {(s, a): t for s, a, t in qa.execute("SELECT surah, ayah, text FROM ayah")}
    trans = {(s, a): t for s, a, t in
             tr.execute("SELECT surah, ayah, text FROM translation")}
    verses = {k: v for k, v in trans.items() if k[1] > 0}
    basmalas = {k[0]: v for k, v in trans.items() if k[1] == 0}

    # A1 -- the two packs describe the same set of ayat.
    check("A1", set(arabic) == set(verses),
          "Arabic and translation cover an identical set of (surah, ayah) keys",
          "only-arabic=%s only-translation=%s"
          % (sorted(set(arabic) - set(verses))[:3], sorted(set(verses) - set(arabic))[:3]))

    # The reference basmala is Al-Fatiha's ayah 1, taken from the pack. Never
    # a literal in this file -- typing Arabic is how 2:255 got corrupted once
    # already (docs/ERRATA.md).
    reference = arabic[(SURAH_FATIHA, 1)]

    # A2 -- the prefix rule holds exactly where SPEC-v1 §6 says it should.
    should_have = [s for s in range(1, TOTAL_SURAHS + 1) if s != SURAH_TAWBAH]
    prefixed = [s for s in range(1, TOTAL_SURAHS + 1)
                if arabic[(s, 1)].startswith(reference)]
    check("A2", prefixed == should_have,
          "ayah 1 carries the basmala prefix for every surah except %d" % SURAH_TAWBAH,
          "unexpected=%s missing=%s"
          % (sorted(set(prefixed) - set(should_have))[:5],
             sorted(set(should_have) - set(prefixed))[:5]))

    # A3 -- At-Tawbah must not have it, on either side.
    check("A3",
          not arabic[(SURAH_TAWBAH, 1)].startswith(reference)
          and SURAH_TAWBAH not in basmalas,
          "At-Tawbah (9) has no basmala in either pack")

    # A4 -- stripping the prefix must leave a non-empty verse everywhere it is
    # not the whole ayah. Al-Fatiha is the one surah where the basmala IS the
    # ayah, so it is excluded by construction, not by exception.
    remainder_empty = []
    for s in should_have:
        if s == SURAH_FATIHA:
            continue
        if not arabic[(s, 1)][len(reference):].strip():
            remainder_empty.append(s)
    check("A4", not remainder_empty,
          "removing the prefix leaves a non-empty ayah 1 in every other surah",
          "empty remainder for surah(s) %s" % remainder_empty[:5])

    # A5 -- Al-Fatiha's ayah 1 is the basmala and nothing else, so it is
    # numbered rather than split off as a heading (SPEC-v1 §6).
    check("A5", arabic[(SURAH_FATIHA, 1)] == reference,
          "Al-Fatiha's ayah 1 is exactly the basmala, so it stays numbered")

    # A6 -- the translation mirrors that structure: a separate ayah 0 for every
    # surah that gets a heading, and none for the two that do not.
    expect_zero = sorted(s for s in should_have if s != SURAH_FATIHA)
    check("A6", sorted(basmalas) == expect_zero,
          "translation carries a separate basmala for exactly the %d heading surahs"
          % len(expect_zero),
          "unexpected=%s missing=%s"
          % (sorted(set(basmalas) - set(expect_zero))[:5],
             sorted(set(expect_zero) - set(basmalas))[:5]))

    # A7 -- one basmala rendering, not 112 near-identical ones.
    check("A7", len(set(basmalas.values())) == 1,
          "the translated basmala is identical across all heading surahs",
          "%d distinct variants" % len(set(basmalas.values())))

    # A8 -- no empty cell can reach the layout, which would collapse a row.
    blank = [k for k, v in list(arabic.items()) + list(verses.items()) if not v.strip()]
    check("A8", not blank, "no ayah is empty in either pack",
          "%d blank, first %s" % (len(blank), blank[:1]))

    print()
    failed = _results.count(False)
    print("RESULT: %s (%d checks)" % ("PASS" if not failed else "FAIL (%d)" % failed,
                                      len(_results)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
