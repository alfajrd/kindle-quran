#!/usr/bin/env python3
"""One-off importer: staged JSON -> vendored, checked corpus + metadata.

    python tools/import_corpus.py --json <path to quran_uthmani_full.json> \
                                   --meta <path to surah_meta.json> \
                                   [--root <repo root>] [--expect-sha256 5e6acc...]

This is NOT part of the build (see `tools/build_pack.py`, which re-derives
and re-asserts everything below from the committed `data/` files on every
run). This script exists once, to turn the pipeline's staged inputs into
`data/quran-uthmani.txt` and `data/surah_meta.json`, and is committed so that
step is auditable rather than something that happened off-screen.

The coder reads the staged JSON. The coder never retypes any Arabic, from it
or about it -- every string below is copied through opaque, byte-for-byte,
from whatever `--json`/`--meta` point at.

Writes NOTHING unless every assertion in this file passes first. On any
failure: print the failure, naming the offending `surah` or `surah:ayah`,
and exit 1 with no file touched.

Nothing here proves the staged JSON came from Tanzil -- only a human `diff`
against a hand-downloaded Tanzil file does that (see `data/SOURCE.md` and
`docs/BUILD.md`). This script proves only that the staged JSON has not
drifted from the digest it was staged with, and that its metadata
cross-validates against its own corpus.

Stdlib only. No network. No `unicodedata.normalize`, ever -- 5771 of the
6236 ayat are not NFC-stable; normalising here would corrupt the Qur'an.
"""
import argparse
import hashlib
import json
import os
import sys

EXPECTED_CORPUS_SHA256 = "5e6accd845ed3668a0ed45937a4626957b1f38d05598e3df573c6ad39fb45621"
EXPECTED_SURAH_COUNT = 114
EXPECTED_AYAH_COUNT = 6236
EXPECTED_SAJDAH_COUNT = 15
EXPECTED_JUZ_COUNT = 30
EXPECTED_MECCAN = 86
EXPECTED_MEDINAN = 28
SAJDAH_MARK = "۩"
REVELATION_MAP = {"Meccan": "meccan", "Medinan": "medinan"}

PRESENTATION_FORM_RANGES = ((0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
WHITELIST_RANGES = ((0x0020, 0x0020), (0x0600, 0x06FF), (0x08A0, 0x08FF))


class ImportError_(Exception):
    """Raised to abort the import; message names the offending item."""


def _in_ranges(cp, ranges):
    for lo, hi in ranges:
        if lo <= cp <= hi:
            return True
    return False


def check_text_codepoints(label, text):
    for ch in text:
        cp = ord(ch)
        if cp == 0xFEFF:
            raise ImportError_("%s: contains U+FEFF" % label)
        if _in_ranges(cp, PRESENTATION_FORM_RANGES):
            raise ImportError_("%s: contains Arabic presentation form U+%04X" % (label, cp))
        if not _in_ranges(cp, WHITELIST_RANGES):
            raise ImportError_("%s: codepoint U+%04X outside whitelist" % (label, cp))


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_corpus_json(data):
    """data: {"surah:ayah": text}. Returns rows sorted by (surah, ayah)."""
    rows = []
    for key, text in data.items():
        parts = key.split(":")
        if len(parts) != 2:
            raise ImportError_("corpus key %r is not of the form surah:ayah" % (key,))
        s_str, a_str = parts
        if str(int(s_str)) != s_str or str(int(a_str)) != a_str:
            raise ImportError_("corpus key %r does not round-trip as int:int" % (key,))
        s, a = int(s_str), int(a_str)
        if not isinstance(text, str):
            raise ImportError_("%s: value is not a string" % key)
        rows.append((s, a, text))
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows


def canonical_bytes(rows):
    """rows: iterable of (surah:int, ayah:int, text:str)."""
    buf = bytearray()
    for s, a, text in rows:
        buf += ("%d|%d|%s\n" % (s, a, text)).encode("utf-8")
    return bytes(buf)


def corpus_sha256(rows):
    return hashlib.sha256(canonical_bytes(rows)).hexdigest()


def derive_sajdah(rows):
    return {(s, a) for s, a, text in rows if SAJDAH_MARK in text}


def assign_juz(rows, juz_start):
    boundaries = []
    for k, v in juz_start.items():
        s_str, a_str = v.split(":")
        boundaries.append((int(k), int(s_str), int(a_str)))
    boundaries.sort(key=lambda b: b[0])
    if [b[0] for b in boundaries] != list(range(1, EXPECTED_JUZ_COUNT + 1)):
        raise ImportError_("juz_start does not have exactly keys 1..%d" % EXPECTED_JUZ_COUNT)
    positions = [(b[1], b[2]) for b in boundaries]
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise ImportError_("juz_start boundaries are not strictly increasing in (surah, ayah)")
    if positions[0] != (1, 1):
        raise ImportError_("juz 1 does not start at 1:1")

    sorted_rows = sorted(rows, key=lambda r: (r[0], r[1]))
    result = {}
    bi = 0
    n = len(boundaries)
    for s, a, _text in sorted_rows:
        while bi + 1 < n and (s, a) >= (boundaries[bi + 1][1], boundaries[bi + 1][2]):
            bi += 1
        result[(s, a)] = boundaries[bi][0]
    return result


def run_assertions(rows, meta):
    """Assertions 1-17 from spec.md's "Assertions" section, against the
    parsed corpus rows and the staged metadata. Raises ImportError_ on the
    first failure it hits, naming the offending surah or surah:ayah."""

    # 1: exactly 114 surahs, ids exactly 1..114, no gaps.
    surah_ids = sorted({s for s, _a, _t in rows})
    if surah_ids != list(range(1, EXPECTED_SURAH_COUNT + 1)):
        raise ImportError_("corpus surah ids are not exactly 1..%d: got %r" % (
            EXPECTED_SURAH_COUNT, surah_ids))

    # 2: exactly 6236 ayat.
    if len(rows) != EXPECTED_AYAH_COUNT:
        raise ImportError_("corpus has %d ayat, expected %d" % (len(rows), EXPECTED_AYAH_COUNT))

    # 3: ayah numbering contiguous 1..n within every surah.
    per_surah = {}
    for s, a, _t in rows:
        per_surah.setdefault(s, []).append(a)
    for s, alist in per_surah.items():
        alist_sorted = sorted(alist)
        if len(alist_sorted) != len(set(alist_sorted)):
            raise ImportError_("surah %d has duplicate ayah numbers" % s)
        if alist_sorted != list(range(1, len(alist_sorted) + 1)):
            raise ImportError_("surah %d ayah numbers are not contiguous 1..n: got %r" % (s, alist_sorted))

    # 4: corpus digest.
    digest = corpus_sha256(rows)
    if digest != EXPECTED_CORPUS_SHA256:
        raise ImportError_("corpus sha256 = %s, expected %s" % (digest, EXPECTED_CORPUS_SHA256))

    # 5-7, 15: codepoint checks on every ayah text.
    for s, a, text in rows:
        check_text_codepoints("%d:%d" % (s, a), text)

    # 8: no ayah empty/whitespace-only; no \n/\r/\t; no leading/trailing/double space.
    for s, a, text in rows:
        if text == "" or text.strip() == "":
            raise ImportError_("%d:%d: empty or whitespace-only text" % (s, a))
        if "\n" in text or "\r" in text or "\t" in text:
            raise ImportError_("%d:%d: contains \\n, \\r or \\t" % (s, a))
        if text != text.strip():
            raise ImportError_("%d:%d: leading or trailing space" % (s, a))
        if "  " in text:
            raise ImportError_("%d:%d: contains a double space" % (s, a))
        if "|" in text:
            raise ImportError_("%d:%d: text contains the '|' delimiter" % (s, a))

    # 10: sajdah, derived, cross-checked against surah_meta.json.sajdah.
    derived = derive_sajdah(rows)
    if len(derived) != EXPECTED_SAJDAH_COUNT:
        raise ImportError_("derived sajdah count = %d, expected %d" % (len(derived), EXPECTED_SAJDAH_COUNT))
    staged_sajdah = set()
    for ref in meta["sajdah"]:
        s_str, a_str = ref.split(":")
        staged_sajdah.add((int(s_str), int(a_str)))
    only_derived = derived - staged_sajdah
    only_staged = staged_sajdah - derived
    if only_derived or only_staged:
        raise ImportError_(
            "sajdah derivation disagrees with surah_meta.json.sajdah: "
            "only in derived scan: %r; only in staged list: %r" % (
                sorted(only_derived), sorted(only_staged)))

    # 11: juz, as a partition.
    juz_of = assign_juz(rows, meta["juz_start"])
    if len(juz_of) != EXPECTED_AYAH_COUNT:
        raise ImportError_("juz assignment covers %d ayat, expected %d" % (
            len(juz_of), EXPECTED_AYAH_COUNT))
    juz_values = set(juz_of.values())
    if juz_values != set(range(1, EXPECTED_JUZ_COUNT + 1)):
        missing_juz = set(range(1, EXPECTED_JUZ_COUNT + 1)) - juz_values
        raise ImportError_("juz partition leaves juz %r empty" % sorted(missing_juz))
    sorted_rows = sorted(rows, key=lambda r: (r[0], r[1]))
    prev = None
    for s, a, _t in sorted_rows:
        j = juz_of[(s, a)]
        if prev is not None and j < prev:
            raise ImportError_("juz is not non-decreasing at %d:%d" % (s, a))
        prev = j

    # 12-14: metadata cross-validation.
    surahs = meta["surahs"]
    if len(surahs) != EXPECTED_SURAH_COUNT:
        raise ImportError_("surah_meta.json has %d surah entries, expected %d" % (
            len(surahs), EXPECTED_SURAH_COUNT))
    numbers = sorted(row["number"] for row in surahs)
    if numbers != list(range(1, EXPECTED_SURAH_COUNT + 1)):
        raise ImportError_("surah_meta.json 'number' values are not exactly 1..%d" % EXPECTED_SURAH_COUNT)

    corpus_counts = {s: len(alist) for s, alist in per_surah.items()}
    mismatches = []
    for row in surahs:
        n = row["number"]
        expected = row["ayah_count"]
        actual = corpus_counts.get(n, 0)
        if expected != actual:
            mismatches.append((n, expected, actual))
        for field in ("name_ar", "name_en", "name_en_translation"):
            value = row.get(field)
            if not isinstance(value, str) or not value:
                raise ImportError_("surah %d: field %r is not a non-empty string" % (n, field))
        check_text_codepoints("surah %d name_ar" % n, row["name_ar"])
    if mismatches:
        detail = "; ".join(
            "surah %d: surah_meta says %d, corpus has %d" % m for m in mismatches
        )
        raise ImportError_("surah_meta.json ayah_count disagrees with the corpus: " + detail)

    # 16: revelation, strict lookup, split exactly 86/28.
    meccan = 0
    medinan = 0
    for row in surahs:
        raw = row["revelation"]
        if raw not in REVELATION_MAP:
            raise ImportError_("surah %d: revelation %r is not 'Meccan' or 'Medinan'" % (row["number"], raw))
        mapped = REVELATION_MAP[raw]
        if mapped == "meccan":
            meccan += 1
        else:
            medinan += 1
    if (meccan, medinan) != (EXPECTED_MECCAN, EXPECTED_MEDINAN):
        raise ImportError_("revelation split is %d meccan / %d medinan, expected %d/%d" % (
            meccan, medinan, EXPECTED_MECCAN, EXPECTED_MEDINAN))

    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    default_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument("--json", required=True, help="path to quran_uthmani_full.json")
    parser.add_argument("--meta", required=True, help="path to surah_meta.json")
    parser.add_argument("--root", default=default_root, help="path to kindle-quran/ (default: %(default)s)")
    parser.add_argument("--expect-sha256", default=EXPECTED_CORPUS_SHA256,
                         help="expected corpus sha256 (default: the pinned constant)")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    root = os.path.abspath(args.root)

    try:
        corpus_data = read_json(args.json)
        meta_data = read_json(args.meta)
        rows = parse_corpus_json(corpus_data)
        digest = run_assertions(rows, meta_data)
        if digest != args.expect_sha256:
            raise ImportError_("corpus sha256 = %s, --expect-sha256 said %s" % (digest, args.expect_sha256))
    except ImportError_ as exc:
        print("IMPORT FAILED: %s" % exc)
        return 1
    except (OSError, ValueError) as exc:
        print("IMPORT FAILED: %s" % exc)
        return 1

    # Every assertion passed. Now, and only now, write the outputs.
    data_dir = os.path.join(root, "data")
    os.makedirs(data_dir, exist_ok=True)

    txt_path = os.path.join(data_dir, "quran-uthmani.txt")
    corpus_bytes = canonical_bytes(rows)
    with open(txt_path, "wb") as f:
        f.write(corpus_bytes)

    sha_path = os.path.join(data_dir, "quran-uthmani.sha256")
    with open(sha_path, "wb") as f:
        f.write(("%s  quran-uthmani.txt\n" % digest).encode("utf-8"))

    # data/surah_meta.json: byte-for-byte copy of the staged file.
    with open(args.meta, "rb") as f:
        meta_bytes = f.read()
    meta_out_path = os.path.join(data_dir, "surah_meta.json")
    with open(meta_out_path, "wb") as f:
        f.write(meta_bytes)

    meta_digest = hashlib.sha256(meta_bytes).hexdigest()
    meta_sha_path = os.path.join(data_dir, "surah_meta.sha256")
    with open(meta_sha_path, "wb") as f:
        f.write(("%s  surah_meta.json\n" % meta_digest).encode("utf-8"))

    print("corpus sha256 = %s" % digest)
    print("surah_meta sha256 = %s" % meta_digest)
    print("rows written = %d" % len(rows))
    print("surahs written = %d" % len(meta_data["surahs"]))
    print("IMPORT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
