#!/usr/bin/env python3
"""Builds `quran.koplugin/data/quran.db` from the vendored, committed corpus.

    python tools/build_pack.py [--root <repo root>] [--out quran.koplugin/data/quran.db]
                               [--build-date YYYY-MM-DD]

Reads `data/quran-uthmani.txt` and `data/surah_meta.json` -- never the
staged `.pipeline/` inputs, never the network -- re-derives and re-asserts
every structural fact about the corpus (see spec.md's "Assertions") on every
run, then writes a fresh SQLite pack.

Deterministic in *content*, not in file bytes: fixed page size, fixed
insertion order, `build_date` is a pinned constant (never `datetime.now()`).
The on-disk layout of the resulting .db file can still vary across SQLite
versions -- that is expected and is exactly why `verify_pack.py` re-derives
the canonical serialisation from the db's own rows rather than comparing
file bytes.

Deliberately does NOT share code with `verify_pack.py` (see D4 in
spec.md) -- a shared helper that mis-serialises or mis-hashes would corrupt
the build and the verification identically, and the checks would pass on
wrong data. This duplication of `derive_sajdah`/`assign_juz`/digest logic
across the two files is intentional; do not "DRY it up".

Stdlib only. No network. No `unicodedata.normalize`, ever.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile

EXPECTED_CORPUS_SHA256 = "5e6accd845ed3668a0ed45937a4626957b1f38d05598e3df573c6ad39fb45621"
EXPECTED_SURAH_COUNT = 114
EXPECTED_AYAH_COUNT = 6236
EXPECTED_SAJDAH_COUNT = 15
EXPECTED_JUZ_COUNT = 30
EXPECTED_MECCAN = 86
EXPECTED_MEDINAN = 28
SAJDAH_MARK = "۩"
REVELATION_MAP = {"Meccan": "meccan", "Medinan": "medinan"}
DEFAULT_BUILD_DATE = "2026-08-07"
APPLICATION_ID = 0x51524E31
SCHEMA_VERSION = 1
BUILDER = "build_pack.py 1.0.0"

PRESENTATION_FORM_RANGES = ((0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
WHITELIST_RANGES = ((0x0020, 0x0020), (0x0600, 0x06FF), (0x08A0, 0x08FF))

DDL = """
CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE surah (
  id            INTEGER PRIMARY KEY,
  name_ar       TEXT NOT NULL,
  name_en       TEXT NOT NULL,
  name_tr       TEXT NOT NULL,
  ayah_count    INTEGER NOT NULL,
  revelation    TEXT NOT NULL,
  has_bismillah INTEGER NOT NULL
);

CREATE TABLE ayah (
  surah  INTEGER NOT NULL REFERENCES surah(id),
  ayah   INTEGER NOT NULL,
  text   TEXT NOT NULL,
  sajdah INTEGER NOT NULL DEFAULT 0,
  juz    INTEGER NOT NULL,
  PRIMARY KEY (surah, ayah)
);

CREATE TABLE translation (
  trans_id TEXT NOT NULL,
  surah    INTEGER NOT NULL,
  ayah     INTEGER NOT NULL,
  text     TEXT NOT NULL,
  PRIMARY KEY (trans_id, surah, ayah)
);

CREATE INDEX idx_ayah_juz ON ayah(juz);
"""


class BuildError(Exception):
    """Raised to abort the build; message names the offending item."""


def _in_ranges(cp, ranges):
    for lo, hi in ranges:
        if lo <= cp <= hi:
            return True
    return False


def check_text_codepoints(label, text):
    for ch in text:
        cp = ord(ch)
        if cp == 0xFEFF:
            raise BuildError("%s: contains U+FEFF" % label)
        if _in_ranges(cp, PRESENTATION_FORM_RANGES):
            raise BuildError("%s: contains Arabic presentation form U+%04X" % (label, cp))
        if not _in_ranges(cp, WHITELIST_RANGES):
            raise BuildError("%s: codepoint U+%04X outside whitelist" % (label, cp))


def read_corpus(path):
    """Reads data/quran-uthmani.txt in binary, decodes utf-8 strict, asserts
    the digest, parses into rows sorted by (surah, ayah)."""
    with open(path, "rb") as f:
        raw = f.read()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_CORPUS_SHA256:
        raise BuildError("corpus sha256 = %s, expected %s" % (digest, EXPECTED_CORPUS_SHA256))

    text = raw.decode("utf-8", errors="strict")
    if text.count("\r") > 0:
        raise BuildError("corpus contains a \\r byte")
    if not text.endswith("\n"):
        raise BuildError("corpus does not end with a trailing newline")
    lines = text[:-1].split("\n")
    if any(line == "" for line in lines):
        raise BuildError("corpus contains a blank line")

    rows = []
    for line in lines:
        parts = line.split("|", 2)
        if len(parts) != 3:
            raise BuildError("corpus line %r is not surah|ayah|text" % (line,))
        s_str, a_str, ayah_text = parts
        if str(int(s_str)) != s_str or str(int(a_str)) != a_str:
            raise BuildError("corpus line %r does not round-trip as int:int" % (line,))
        if "|" in ayah_text:
            raise BuildError("%s:%s: text contains the '|' delimiter" % (s_str, a_str))
        rows.append((int(s_str), int(a_str), ayah_text))

    ordered = sorted(rows, key=lambda r: (r[0], r[1]))
    if ordered != rows:
        raise BuildError("corpus lines are not in ascending (surah, ayah) order")

    return rows


def read_meta(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def derive_sajdah(rows):
    return {(s, a) for s, a, text in rows if SAJDAH_MARK in text}


def assign_juz(rows, juz_start):
    boundaries = []
    for k, v in juz_start.items():
        s_str, a_str = v.split(":")
        boundaries.append((int(k), int(s_str), int(a_str)))
    boundaries.sort(key=lambda b: b[0])
    if [b[0] for b in boundaries] != list(range(1, EXPECTED_JUZ_COUNT + 1)):
        raise BuildError("juz_start does not have exactly keys 1..%d" % EXPECTED_JUZ_COUNT)
    positions = [(b[1], b[2]) for b in boundaries]
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise BuildError("juz_start boundaries are not strictly increasing in (surah, ayah)")
    if positions[0] != (1, 1):
        raise BuildError("juz 1 does not start at 1:1")

    sorted_rows = sorted(rows, key=lambda r: (r[0], r[1]))
    result = {}
    bi = 0
    n = len(boundaries)
    for s, a, _text in sorted_rows:
        while bi + 1 < n and (s, a) >= (boundaries[bi + 1][1], boundaries[bi + 1][2]):
            bi += 1
        result[(s, a)] = boundaries[bi][0]
    return result


def run_corpus_assertions(rows):
    """Assertions 1-9 against the parsed rows."""
    surah_ids = sorted({s for s, _a, _t in rows})
    if surah_ids != list(range(1, EXPECTED_SURAH_COUNT + 1)):
        raise BuildError("corpus surah ids are not exactly 1..%d: got %r" % (
            EXPECTED_SURAH_COUNT, surah_ids))

    if len(rows) != EXPECTED_AYAH_COUNT:
        raise BuildError("corpus has %d ayat, expected %d" % (len(rows), EXPECTED_AYAH_COUNT))

    per_surah = {}
    for s, a, _t in rows:
        per_surah.setdefault(s, []).append(a)
    for s, alist in per_surah.items():
        alist_sorted = sorted(alist)
        if len(alist_sorted) != len(set(alist_sorted)):
            raise BuildError("surah %d has duplicate ayah numbers" % s)
        if alist_sorted != list(range(1, len(alist_sorted) + 1)):
            raise BuildError("surah %d ayah numbers are not contiguous 1..n: got %r" % (s, alist_sorted))

    for s, a, text in rows:
        check_text_codepoints("%d:%d" % (s, a), text)
        if text == "" or text.strip() == "":
            raise BuildError("%d:%d: empty or whitespace-only text" % (s, a))
        if "\n" in text or "\r" in text or "\t" in text:
            raise BuildError("%d:%d: contains \\n, \\r or \\t" % (s, a))
        if text != text.strip():
            raise BuildError("%d:%d: leading or trailing space" % (s, a))
        if "  " in text:
            raise BuildError("%d:%d: contains a double space" % (s, a))

    return per_surah


def run_meta_assertions(meta, per_surah):
    """Assertions 12-17 against the staged metadata, cross-validated against
    the corpus's own per-surah counts."""
    surahs = meta["surahs"]
    if len(surahs) != EXPECTED_SURAH_COUNT:
        raise BuildError("surah_meta.json has %d surah entries, expected %d" % (
            len(surahs), EXPECTED_SURAH_COUNT))
    numbers = sorted(row["number"] for row in surahs)
    if numbers != list(range(1, EXPECTED_SURAH_COUNT + 1)):
        raise BuildError("surah_meta.json 'number' values are not exactly 1..%d" % EXPECTED_SURAH_COUNT)

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
                raise BuildError("surah %d: field %r is not a non-empty string" % (n, field))
        check_text_codepoints("surah %d name_ar" % n, row["name_ar"])
    if mismatches:
        detail = "; ".join(
            "surah %d: surah_meta says %d, corpus has %d" % m for m in mismatches
        )
        raise BuildError("surah_meta.json ayah_count disagrees with the corpus: " + detail)

    meccan = 0
    medinan = 0
    for row in surahs:
        raw = row["revelation"]
        if raw not in REVELATION_MAP:
            raise BuildError("surah %d: revelation %r is not 'Meccan' or 'Medinan'" % (row["number"], raw))
        if REVELATION_MAP[raw] == "meccan":
            meccan += 1
        else:
            medinan += 1
    if (meccan, medinan) != (EXPECTED_MECCAN, EXPECTED_MEDINAN):
        raise BuildError("revelation split is %d meccan / %d medinan, expected %d/%d" % (
            meccan, medinan, EXPECTED_MECCAN, EXPECTED_MEDINAN))


def build(root, out_path, build_date):
    corpus_path = os.path.join(root, "data", "quran-uthmani.txt")
    meta_path = os.path.join(root, "data", "surah_meta.json")
    meta_sha_path = os.path.join(root, "data", "surah_meta.sha256")

    rows = read_corpus(corpus_path)
    per_surah = run_corpus_assertions(rows)

    with open(meta_path, "rb") as f:
        meta_bytes = f.read()
    meta_digest = hashlib.sha256(meta_bytes).hexdigest()
    with open(meta_sha_path, "r", encoding="utf-8") as f:
        expected_meta_digest = f.read().split()[0].lower()
    if meta_digest != expected_meta_digest:
        raise BuildError("data/surah_meta.json sha256 = %s does not match data/surah_meta.sha256 = %s" % (
            meta_digest, expected_meta_digest))
    meta = json.loads(meta_bytes.decode("utf-8"))
    run_meta_assertions(meta, per_surah)

    sajdah_set = derive_sajdah(rows)
    if len(sajdah_set) != EXPECTED_SAJDAH_COUNT:
        raise BuildError("derived sajdah count = %d, expected %d" % (len(sajdah_set), EXPECTED_SAJDAH_COUNT))
    staged_sajdah = set()
    for ref in meta["sajdah"]:
        s_str, a_str = ref.split(":")
        staged_sajdah.add((int(s_str), int(a_str)))
    if sajdah_set != staged_sajdah:
        raise BuildError(
            "sajdah derivation disagrees with surah_meta.json.sajdah: "
            "only in derived scan: %r; only in staged list: %r" % (
                sorted(sajdah_set - staged_sajdah), sorted(staged_sajdah - sajdah_set)))

    juz_of = assign_juz(rows, meta["juz_start"])
    if len(juz_of) != EXPECTED_AYAH_COUNT:
        raise BuildError("juz assignment covers %d ayat, expected %d" % (len(juz_of), EXPECTED_AYAH_COUNT))
    if set(juz_of.values()) != set(range(1, EXPECTED_JUZ_COUNT + 1)):
        raise BuildError("juz partition does not cover all 30 juz")
    covered = len(juz_of)
    missing = EXPECTED_AYAH_COUNT - covered
    overlapping = 0

    corpus_digest = hashlib.sha256(open(corpus_path, "rb").read()).hexdigest()

    surah_by_id = {row["number"]: row for row in meta["surahs"]}

    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".quran.db.", dir=os.path.dirname(out_path) or ".")
    os.close(tmp_fd)
    os.remove(tmp_path)  # sqlite3.connect must create it fresh

    try:
        conn = sqlite3.connect(tmp_path)
        try:
            conn.execute("PRAGMA page_size = 4096;")
            conn.execute("PRAGMA encoding = 'UTF-8';")
            conn.executescript(DDL)
            conn.execute("PRAGMA application_id = %d;" % APPLICATION_ID)
            conn.execute("PRAGMA user_version = %d;" % SCHEMA_VERSION)

            surah_rows = []
            for n in range(1, EXPECTED_SURAH_COUNT + 1):
                row = surah_by_id[n]
                has_bismillah = 0 if n == 9 else 1
                surah_rows.append((
                    n,
                    row["name_ar"],
                    row["name_en_translation"],
                    row["name_en"],
                    row["ayah_count"],
                    REVELATION_MAP[row["revelation"]],
                    has_bismillah,
                ))
            conn.executemany(
                "INSERT INTO surah (id, name_ar, name_en, name_tr, ayah_count, revelation, has_bismillah) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                surah_rows,
            )

            ayah_rows = []
            for s, a, text in sorted(rows, key=lambda r: (r[0], r[1])):
                sajdah_flag = 1 if (s, a) in sajdah_set else 0
                ayah_rows.append((s, a, text, sajdah_flag, juz_of[(s, a)]))
            conn.executemany(
                "INSERT INTO ayah (surah, ayah, text, sajdah, juz) VALUES (?, ?, ?, ?, ?)",
                ayah_rows,
            )

            terms = (
                "Tanzil Qur'an Text is available under the Tanzil Terms of Use: "
                "the text may be freely copied, distributed and used, with or "
                "without modification, for any purpose, provided the Qur'anic "
                "Arabic text itself is not modified in any manner, and a proper "
                "attribution to Tanzil (https://tanzil.net) is made."
            )
            meta_rows = sorted([
                ("pack_id", "quran-uthmani"),
                ("schema_version", str(SCHEMA_VERSION)),
                ("name", "Qur'an — Uthmani"),
                ("language", "ar"),
                ("direction", "rtl"),
                ("text_edition", "Tanzil Uthmani"),
                ("source_url", "https://tanzil.net"),
                ("attribution", "Tanzil Qur'an Text (Uthmani), https://tanzil.net"),
                ("licence", "Free to use with attribution; the Qur'anic text must not be modified."),
                ("terms", terms),
                ("build_date", build_date),
                ("checksum", corpus_digest),
                ("surah_count", str(EXPECTED_SURAH_COUNT)),
                ("ayah_count", str(EXPECTED_AYAH_COUNT)),
                ("builder", BUILDER),
            ], key=lambda kv: kv[0])
            conn.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", meta_rows)

            conn.commit()

            check_row = conn.execute("PRAGMA integrity_check;").fetchone()
            if check_row is None or check_row[0] != "ok":
                raise BuildError("PRAGMA integrity_check did not return 'ok': %r" % (check_row,))

            conn.execute("VACUUM;")
        finally:
            conn.close()

        # Reopen the finished file read-only, round-trip every string.
        ro_conn = sqlite3.connect("file:%s?mode=ro" % tmp_path, uri=True)
        try:
            ayah_by_key = {(s, a): text for s, a, text in rows}
            for s, a, db_text in ro_conn.execute("SELECT surah, ayah, text FROM ayah"):
                if ayah_by_key[(s, a)] != db_text:
                    raise BuildError("round-trip mismatch at %d:%d" % (s, a))
            for n, db_name_ar in ro_conn.execute("SELECT id, name_ar FROM surah"):
                if surah_by_id[n]["name_ar"] != db_name_ar:
                    raise BuildError("round-trip mismatch for surah %d name_ar" % n)
        finally:
            ro_conn.close()

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        os.replace(tmp_path, out_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    db_bytes = open(out_path, "rb").read()
    db_digest = hashlib.sha256(db_bytes).hexdigest()
    with open(out_path + ".sha256", "wb") as f:
        f.write(("%s  quran.db\n" % db_digest).encode("utf-8"))

    manifest = {
        "pack_id": "quran-uthmani",
        "schema_version": SCHEMA_VERSION,
        "name": "Qur'an — Uthmani",
        "language": "ar",
        "direction": "rtl",
        "text_edition": "Tanzil Uthmani",
        "source_url": "https://tanzil.net",
        "attribution": "Tanzil Qur'an Text (Uthmani), https://tanzil.net",
        "build_date": build_date,
        "surah_count": EXPECTED_SURAH_COUNT,
        "ayah_count": EXPECTED_AYAH_COUNT,
        "corpus_sha256": corpus_digest,
        "db_sha256": db_digest,
    }
    manifest_path = os.path.join(os.path.dirname(out_path), "manifest.json")
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    print("corpus sha256 = %s" % corpus_digest)
    print("db sha256 = %s" % db_digest)
    print("surahs = %d, ayat = %d" % (EXPECTED_SURAH_COUNT, len(rows)))
    print("sajdah = %d (derived)" % len(sajdah_set))
    print("juz partition: %d covered / %d missing / %d overlapping" % (covered, missing, overlapping))
    print("RESULT: PASS")
    return db_digest


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    default_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument("--root", default=default_root, help="path to kindle-quran/ (default: %(default)s)")
    parser.add_argument("--out", default=None, help="output path for quran.db (default: <root>/quran.koplugin/data/quran.db)")
    parser.add_argument("--build-date", default=DEFAULT_BUILD_DATE, help="pinned build_date (default: %(default)s)")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    root = os.path.abspath(args.root)
    out_path = args.out or os.path.join(root, "quran.koplugin", "data", "quran.db")
    if not os.path.isabs(out_path):
        out_path = os.path.join(root, out_path)

    try:
        build(root, out_path, args.build_date)
    except BuildError as exc:
        print("BUILD FAILED: %s" % exc)
        print("RESULT: FAIL")
        return 1
    except (OSError, ValueError, sqlite3.Error) as exc:
        print("BUILD FAILED: %s" % exc)
        print("RESULT: FAIL")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
