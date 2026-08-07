#!/usr/bin/env python3
"""Loud, standalone validator for `quran.koplugin/data/quran.db`.

    python tools/verify_pack.py [<db path>] [--root <repo root>]

Deliberately shares NO code with `tools/build_pack.py` or any other project
module (see D4 in spec.md): a shared helper that serialised or hashed the
corpus would corrupt the build and this verification identically, and every
check below would pass on wrong data. Every helper in this file is its own
copy, re-typed, not imported.

Opens the db read-only (`sqlite3.connect("file:...?mode=ro", uri=True)`) and
never writes to it. Output contract identical to `tools/check_m0.py`: one
`PASS  <id>  <desc>` / `FAIL  <id>  <reason>` line per check, never
short-circuits, a final `RESULT: PASS (n checks)` / `RESULT: FAIL (k of n
failed)` line, exit 0/1.

This proves the pack's CONTENT is byte-identical, table by table, to the
canonical serialisation of the verified corpus. It does NOT prove the .db
file is byte-reproducible across SQLite versions (see D3) -- that is not a
claim this project makes. It does NOT prove Tanzil provenance on its own --
see `data/SOURCE.md` for what does.

Stdlib only (`sqlite3`, `hashlib`, `json`, `os`, `sys`, `argparse`, `re`).
No network. No `unicodedata.normalize`, ever.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
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
APPLICATION_ID = 0x51524E31

PRESENTATION_FORM_RANGES = ((0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
WHITELIST_RANGES = ((0x0020, 0x0020), (0x0600, 0x06FF), (0x08A0, 0x08FF))

REQUIRED_META_KEYS = [
    "pack_id", "schema_version", "name", "language", "direction",
    "text_edition", "source_url", "attribution", "licence", "terms",
    "build_date", "checksum", "surah_count", "ayah_count", "builder",
]

# The spec's P26 whitelist is "printable ASCII plus -, ', space". Two of the
# 114 staged surah_meta.json name_en_translation values are genuinely
# comma-separated alternate meanings ("The Power, Fate" for surah 97, "The
# Declining Day, Epoch" for surah 103) -- verbatim, trusted metadata, not a
# typo and not something this pipeline may retype to satisfy a check. Per
# the M0 rule (a failing presence/absence assertion against genuinely
# verbatim/trusted text means the assertion is wrong, never the data), the
# whitelist below adds ',' to what P26 accepts. See data/SOURCE.md.
LATIN_ALLOWED_RE = re.compile(r"^[A-Za-z\-', ]+$")

CHECKS = []  # list of (id, passed: bool, message: str)


def record(check_id, passed, message):
    CHECKS.append((check_id, passed, message))


def check_boolean(check_id, condition, ok_desc, fail_reason):
    if condition:
        record(check_id, True, ok_desc)
    else:
        record(check_id, False, fail_reason)


def _in_ranges(cp, ranges):
    for lo, hi in ranges:
        if lo <= cp <= hi:
            return True
    return False


def canonical_bytes(rows):
    """rows: iterable of (surah:int, ayah:int, text:str), ascending order."""
    buf = bytearray()
    for s, a, text in rows:
        buf += ("%d|%d|%s\n" % (s, a, text)).encode("utf-8")
    return bytes(buf)


def connect_ro(db_path):
    uri = "file:%s?mode=ro" % db_path.replace("\\", "/")
    return sqlite3.connect(uri, uri=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    default_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument("db_path", nargs="?", default=None, help="path to quran.db")
    parser.add_argument("--root", default=default_root, help="path to kindle-quran/ (default: %(default)s)")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    root = os.path.abspath(args.root)
    db_path = args.db_path or os.path.join(root, "quran.koplugin", "data", "quran.db")
    db_path = os.path.abspath(db_path)

    # P1: db file exists and opens.
    conn = None
    if not os.path.isfile(db_path):
        record("P1", False, "db file does not exist: %s" % db_path)
    else:
        try:
            conn = connect_ro(db_path)
            conn.execute("SELECT 1;")
            record("P1", True, "db file exists and opens read-only")
        except sqlite3.Error as exc:
            record("P1", False, "db file exists but failed to open: %s" % exc)
            conn = None

    if conn is None:
        # Cannot run any further checks meaningfully; record them all as
        # failed so the output contract (one line per check) still holds.
        for check_id in [
            "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10", "P11",
            "P12", "P13", "P14", "P15", "P16", "P17", "P18", "P19", "P20",
            "P21", "P22", "P23", "P24", "P25", "P26", "P27",
        ]:
            record(check_id, False, "db could not be opened (see P1)")
        return _finish()

    try:
        # P2: integrity_check
        row = conn.execute("PRAGMA integrity_check;").fetchone()
        check_boolean("P2", row is not None and row[0] == "ok",
                       "PRAGMA integrity_check == ok",
                       "PRAGMA integrity_check returned %r" % (row,))

        # P3: encoding
        row = conn.execute("PRAGMA encoding;").fetchone()
        encoding = row[0] if row else None
        check_boolean("P3", encoding == "UTF-8",
                       "PRAGMA encoding == UTF-8",
                       "PRAGMA encoding == %r" % (encoding,))

        # P4: user_version / application_id
        user_version = conn.execute("PRAGMA user_version;").fetchone()[0]
        application_id = conn.execute("PRAGMA application_id;").fetchone()[0]
        check_boolean("P4", user_version == 1 and application_id == APPLICATION_ID,
                       "PRAGMA user_version == 1 and application_id == 0x51524E31",
                       "user_version=%r application_id=%r (expected 1, 0x%X)" % (
                           user_version, application_id, APPLICATION_ID))

        # P5: tables exist
        existing_tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';")
        }
        required_tables = {"meta", "surah", "ayah", "translation"}
        missing_tables = required_tables - existing_tables
        check_boolean("P5", not missing_tables,
                       "tables meta, surah, ayah, translation all exist",
                       "missing table(s): " + ", ".join(sorted(missing_tables)))

        if missing_tables:
            for check_id in [
                "P6", "P7", "P8", "P9", "P10", "P11", "P12", "P13", "P14",
                "P15", "P16", "P17", "P18", "P19", "P20", "P21", "P22",
                "P23", "P24", "P25", "P26", "P27",
            ]:
                record(check_id, False, "required table missing (see P5)")
            return _finish(conn)

        surah_rows = conn.execute(
            "SELECT id, name_ar, name_en, name_tr, ayah_count, revelation, has_bismillah FROM surah ORDER BY id;"
        ).fetchall()
        ayah_rows = conn.execute(
            "SELECT surah, ayah, text, sajdah, juz FROM ayah ORDER BY surah, ayah;"
        ).fetchall()
        meta_rows = dict(conn.execute("SELECT key, value FROM meta;").fetchall())

        # P6: surah row count and ids
        surah_ids = [r[0] for r in surah_rows]
        check_boolean("P6", len(surah_rows) == EXPECTED_SURAH_COUNT and surah_ids == list(range(1, EXPECTED_SURAH_COUNT + 1)),
                       "surah has exactly %d rows, ids exactly 1..%d" % (EXPECTED_SURAH_COUNT, EXPECTED_SURAH_COUNT),
                       "surah has %d rows, ids %r" % (len(surah_rows), surah_ids))

        # P7: ayah row count
        check_boolean("P7", len(ayah_rows) == EXPECTED_AYAH_COUNT,
                       "ayah has exactly %d rows" % EXPECTED_AYAH_COUNT,
                       "ayah has %d rows" % len(ayah_rows))

        # P8: per-surah ayah numbering contiguous 1..n
        per_surah = {}
        for s, a, _t, _sj, _j in ayah_rows:
            per_surah.setdefault(s, []).append(a)
        bad_surahs = []
        for s, alist in per_surah.items():
            sorted_alist = sorted(alist)
            if sorted_alist != list(range(1, len(sorted_alist) + 1)) or len(alist) != len(set(alist)):
                bad_surahs.append(s)
        check_boolean("P8", not bad_surahs,
                       "for every surah, ayah numbers are exactly 1..n",
                       "surah(s) with bad ayah numbering: %r" % (sorted(bad_surahs),))

        # P9: per-surah counts sum to 6236
        total_from_surahs = sum(len(alist) for alist in per_surah.values())
        check_boolean("P9", total_from_surahs == EXPECTED_AYAH_COUNT,
                       "per-surah row counts sum to exactly %d" % EXPECTED_AYAH_COUNT,
                       "per-surah row counts sum to %d" % total_from_surahs)

        # P10: surah.ayah_count == actual row count per surah
        mismatches = []
        for sid, _name_ar, _name_en, _name_tr, ayah_count, _rev, _hb in surah_rows:
            actual = len(per_surah.get(sid, []))
            if ayah_count != actual:
                mismatches.append("surah %d: ayah_count=%d actual=%d" % (sid, ayah_count, actual))
        check_boolean("P10", not mismatches,
                       "surah.ayah_count matches actual ayah row counts for all %d surahs" % EXPECTED_SURAH_COUNT,
                       "disagreement(s): " + "; ".join(mismatches))

        # P11: no empty/whitespace-only text, no empty surah name column
        empty_texts = [(s, a) for s, a, t, _sj, _j in ayah_rows if t is None or t.strip() == ""]
        empty_names = []
        for sid, name_ar, name_en, name_tr, _ac, _rev, _hb in surah_rows:
            for col, val in (("name_ar", name_ar), ("name_en", name_en), ("name_tr", name_tr)):
                if val is None or val.strip() == "":
                    empty_names.append("surah %d.%s" % (sid, col))
        check_boolean("P11", not empty_texts and not empty_names,
                       "no ayah text is empty/whitespace-only; no surah name column is empty",
                       "empty ayah text(s): %r; empty name column(s): %r" % (empty_texts, empty_names))

        # P12: zero U+FEFF anywhere in text columns
        feff_locations = []
        for s, a, t, _sj, _j in ayah_rows:
            if "﻿" in (t or ""):
                feff_locations.append("ayah %d:%d" % (s, a))
        for sid, name_ar, name_en, name_tr, _ac, _rev, _hb in surah_rows:
            for col, val in (("name_ar", name_ar), ("name_en", name_en), ("name_tr", name_tr)):
                if "﻿" in (val or ""):
                    feff_locations.append("surah %d.%s" % (sid, col))
        for key, val in meta_rows.items():
            if "﻿" in (val or ""):
                feff_locations.append("meta.%s" % key)
        check_boolean("P12", not feff_locations,
                       "zero U+FEFF in any text column of any table",
                       "U+FEFF found at: " + ", ".join(feff_locations))

        # P13: zero Arabic presentation forms in ayah.text and surah.name_ar
        pf_locations = []
        for s, a, t, _sj, _j in ayah_rows:
            if any(_in_ranges(ord(ch), PRESENTATION_FORM_RANGES) for ch in (t or "")):
                pf_locations.append("ayah %d:%d" % (s, a))
        for sid, name_ar, _name_en, _name_tr, _ac, _rev, _hb in surah_rows:
            if any(_in_ranges(ord(ch), PRESENTATION_FORM_RANGES) for ch in (name_ar or "")):
                pf_locations.append("surah %d.name_ar" % sid)
        check_boolean("P13", not pf_locations,
                       "zero Arabic presentation forms (U+FB50-FDFF, U+FE70-FEFF) in ayah.text and surah.name_ar",
                       "presentation form(s) found at: " + ", ".join(pf_locations))

        # P14: codepoint whitelist for ayah.text and surah.name_ar
        offenders = []
        for s, a, t, _sj, _j in ayah_rows:
            for ch in (t or ""):
                cp = ord(ch)
                if not _in_ranges(cp, WHITELIST_RANGES):
                    offenders.append("U+%04X at ayah %d:%d" % (cp, s, a))
        for sid, name_ar, _name_en, _name_tr, _ac, _rev, _hb in surah_rows:
            for ch in (name_ar or ""):
                cp = ord(ch)
                if not _in_ranges(cp, WHITELIST_RANGES):
                    offenders.append("U+%04X at surah %d.name_ar" % (cp, sid))
        check_boolean("P14", not offenders,
                       "codepoint whitelist (U+0020, U+0600-06FF, U+08A0-08FF) obeyed in ayah.text and surah.name_ar",
                       "offender(s): " + ", ".join(offenders))

        # P15: no \n \r \t, no leading/trailing space, no double space
        bad_whitespace = []
        for s, a, t, _sj, _j in ayah_rows:
            text = t or ""
            if "\n" in text or "\r" in text or "\t" in text or text != text.strip() or "  " in text:
                bad_whitespace.append("%d:%d" % (s, a))
        check_boolean("P15", not bad_whitespace,
                       "no \\n, \\r, \\t, leading/trailing space or double space in any ayah text",
                       "offending ayah(s): " + ", ".join(bad_whitespace))

        # P16: canonical serialisation re-derived from db rows hashes to the pin
        rederived = canonical_bytes([(s, a, t) for s, a, t, _sj, _j in ayah_rows])
        rederived_digest = hashlib.sha256(rederived).hexdigest()
        check_boolean("P16", rederived_digest == EXPECTED_CORPUS_SHA256,
                       "canonical serialisation re-derived from db rows hashes to %s" % EXPECTED_CORPUS_SHA256,
                       "re-derived digest = %s, expected %s" % (rederived_digest, EXPECTED_CORPUS_SHA256))

        # P17: required meta keys present/non-empty; checksum/surah_count/ayah_count
        missing_meta = [k for k in REQUIRED_META_KEYS if not meta_rows.get(k)]
        checksum_ok = meta_rows.get("checksum") == EXPECTED_CORPUS_SHA256
        surah_count_ok = meta_rows.get("surah_count") == str(EXPECTED_SURAH_COUNT)
        ayah_count_ok = meta_rows.get("ayah_count") == str(EXPECTED_AYAH_COUNT)
        check_boolean("P17", not missing_meta and checksum_ok and surah_count_ok and ayah_count_ok,
                       "every required meta key present and non-empty; checksum/surah_count/ayah_count correct",
                       "missing key(s): %r; checksum_ok=%r surah_count_ok=%r ayah_count_ok=%r" % (
                           missing_meta, checksum_ok, surah_count_ok, ayah_count_ok))

        # P18: attribution/source_url contain tanzil.net; licence/terms non-empty
        attribution_ok = "tanzil.net" in (meta_rows.get("attribution") or "")
        source_url_ok = "tanzil.net" in (meta_rows.get("source_url") or "")
        licence_ok = bool(meta_rows.get("licence"))
        terms_ok = bool(meta_rows.get("terms"))
        check_boolean("P18", attribution_ok and source_url_ok and licence_ok and terms_ok,
                       "meta.attribution/source_url mention tanzil.net; meta.licence/terms non-empty",
                       "attribution_ok=%r source_url_ok=%r licence_ok=%r terms_ok=%r" % (
                           attribution_ok, source_url_ok, licence_ok, terms_ok))

        # P19: sajdah is exactly the U+06E9 scan, both directions
        wrong_flag = []
        sajdah_flag_count = 0
        for s, a, t, sajdah_flag, _j in ayah_rows:
            has_mark = SAJDAH_MARK in (t or "")
            if sajdah_flag:
                sajdah_flag_count += 1
            if bool(sajdah_flag) != has_mark:
                wrong_flag.append("%d:%d" % (s, a))
        check_boolean("P19", not wrong_flag and sajdah_flag_count == EXPECTED_SAJDAH_COUNT,
                       "sajdah flag agrees with U+06E9 scan in both directions, count == %d" % EXPECTED_SAJDAH_COUNT,
                       "disagreement(s): %r; sajdah_flag_count=%d" % (wrong_flag, sajdah_flag_count))

        # P20: juz is an exact partition
        juz_values = [j for _s, _a, _t, _sj, j in ayah_rows]
        juz_in_range = all(1 <= j <= EXPECTED_JUZ_COUNT for j in juz_values)
        juz_present = set(juz_values)
        all_30_nonempty = juz_present == set(range(1, EXPECTED_JUZ_COUNT + 1))
        covered = len(ayah_rows)
        missing = EXPECTED_AYAH_COUNT - covered if covered < EXPECTED_AYAH_COUNT else 0
        overlapping = 0  # PRIMARY KEY (surah, ayah) makes duplicate rows impossible
        ordered_ayah_rows = sorted(ayah_rows, key=lambda r: (r[0], r[1]))
        non_decreasing = True
        prev_j = None
        for _s, _a, _t, _sj, j in ordered_ayah_rows:
            if prev_j is not None and j < prev_j:
                non_decreasing = False
                break
            prev_j = j
        partition_ok = (
            juz_in_range and all_30_nonempty and covered == EXPECTED_AYAH_COUNT
            and missing == 0 and overlapping == 0 and non_decreasing
        )
        check_boolean("P20", partition_ok,
                       "juz is an exact partition: 1..30, all non-empty, %d covered / 0 missing / 0 overlapping, non-decreasing" % EXPECTED_AYAH_COUNT,
                       "covered=%d missing=%d overlapping=%d all_30_nonempty=%r non_decreasing=%r juz_in_range=%r" % (
                           covered, missing, overlapping, all_30_nonempty, non_decreasing, juz_in_range))

        # P21: translation row counts, per trans_id, == 6236
        trans_counts = {}
        for trans_id, in conn.execute("SELECT DISTINCT trans_id FROM translation;"):
            count = conn.execute("SELECT COUNT(*) FROM translation WHERE trans_id = ?;", (trans_id,)).fetchone()[0]
            trans_counts[trans_id] = count
        bad_trans = {k: v for k, v in trans_counts.items() if v != EXPECTED_AYAH_COUNT}
        check_boolean("P21", not bad_trans,
                       "for each distinct translation.trans_id, row count == %d (vacuously true while empty)" % EXPECTED_AYAH_COUNT,
                       "trans_id(s) with wrong row count: %r" % (bad_trans,))

        # P22: db row (2,255) equals quran.koplugin/data/2_255.txt (stripped)
        pin_path = os.path.join(root, "quran.koplugin", "data", "2_255.txt")
        db_2_255 = None
        for s, a, t, _sj, _j in ayah_rows:
            if (s, a) == (2, 255):
                db_2_255 = t
                break
        if not os.path.isfile(pin_path):
            record("P22", False, "pin file does not exist: %s" % pin_path)
        elif db_2_255 is None:
            record("P22", False, "db has no row for 2:255")
        else:
            pin_text = open(pin_path, "r", encoding="utf-8").read().strip()
            check_boolean("P22", db_2_255 == pin_text,
                           "db row (2,255) equals quran.koplugin/data/2_255.txt (stripped)",
                           "db 2:255 differs from the M0 pin")

        # P23: has_bismillah == 0 for surah 9, == 1 for all others
        bismillah_bad = []
        for sid, _na, _ne, _nt, _ac, _rev, hb in surah_rows:
            expected_hb = 0 if sid == 9 else 1
            if hb != expected_hb:
                bismillah_bad.append(sid)
        check_boolean("P23", not bismillah_bad,
                       "has_bismillah == 0 for surah 9 and == 1 for all 113 others",
                       "surah(s) with wrong has_bismillah: %r" % (bismillah_bad,))

        # P24: sha256 of db file matches quran.db.sha256
        sha_path = db_path + ".sha256"
        if not os.path.isfile(sha_path):
            record("P24", False, "quran.db.sha256 does not exist: %s" % sha_path)
        else:
            actual_db_sha = hashlib.sha256(open(db_path, "rb").read()).hexdigest()
            stated = open(sha_path, "r", encoding="utf-8").read().split()[0].lower()
            check_boolean("P24", actual_db_sha == stated,
                           "sha256 of db file matches quran.db.sha256",
                           "actual=%s stated=%s" % (actual_db_sha, stated))

        # P25: revelation split
        revelations = [r[5] for r in surah_rows]
        rev_domain_ok = all(r in ("meccan", "medinan") for r in revelations)
        meccan = revelations.count("meccan")
        medinan = revelations.count("medinan")
        check_boolean("P25", rev_domain_ok and meccan == EXPECTED_MECCAN and medinan == EXPECTED_MEDINAN,
                       "revelation in {meccan, medinan} for all 114, split exactly %d/%d" % (EXPECTED_MECCAN, EXPECTED_MEDINAN),
                       "rev_domain_ok=%r meccan=%d medinan=%d" % (rev_domain_ok, meccan, medinan))

        # P26: surah name columns non-empty; Latin columns restricted charset
        p26_bad = []
        for sid, name_ar, name_en, name_tr, _ac, _rev, _hb in surah_rows:
            if not name_ar:
                p26_bad.append("surah %d.name_ar empty" % sid)
            for col, val in (("name_en", name_en), ("name_tr", name_tr)):
                if not val:
                    p26_bad.append("surah %d.%s empty" % (sid, col))
                elif not LATIN_ALLOWED_RE.match(val):
                    p26_bad.append("surah %d.%s contains disallowed character(s): %r" % (sid, col, val))
        check_boolean("P26", not p26_bad,
                       "every surah name_ar/name_en/name_tr non-empty; Latin columns restricted to ASCII letters, -, ', ',', space",
                       "; ".join(p26_bad))

        # P27: surah rows match data/surah_meta.json field-for-field, after D-mapping
        surah_meta_path = os.path.join(root, "data", "surah_meta.json")
        surah_meta_sha_path = os.path.join(root, "data", "surah_meta.sha256")
        p27_reasons = []
        if not os.path.isfile(surah_meta_path):
            p27_reasons.append("data/surah_meta.json does not exist")
        else:
            meta_json_bytes = open(surah_meta_path, "rb").read()
            meta_json_digest = hashlib.sha256(meta_json_bytes).hexdigest()
            if os.path.isfile(surah_meta_sha_path):
                stated_meta_sha = open(surah_meta_sha_path, "r", encoding="utf-8").read().split()[0].lower()
                if meta_json_digest != stated_meta_sha:
                    p27_reasons.append("data/surah_meta.json sha256 does not match data/surah_meta.sha256")
            else:
                p27_reasons.append("data/surah_meta.sha256 does not exist")

            surah_meta = json.loads(meta_json_bytes.decode("utf-8"))
            meta_by_id = {row["number"]: row for row in surah_meta["surahs"]}
            db_by_id = {r[0]: r for r in surah_rows}
            for n in range(1, EXPECTED_SURAH_COUNT + 1):
                src = meta_by_id.get(n)
                db_row = db_by_id.get(n)
                if src is None or db_row is None:
                    p27_reasons.append("surah %d missing from source or db" % n)
                    continue
                _sid, name_ar, name_en, name_tr, ayah_count, revelation, _hb = db_row
                expected_name_tr = src["name_en"]
                expected_name_en = src["name_en_translation"]
                expected_revelation = REVELATION_MAP.get(src["revelation"])
                if name_ar != src["name_ar"]:
                    p27_reasons.append("surah %d name_ar mismatch" % n)
                if name_tr != expected_name_tr:
                    p27_reasons.append("surah %d name_tr mismatch (expected name_en<-name_en)" % n)
                if name_en != expected_name_en:
                    p27_reasons.append("surah %d name_en mismatch (expected name_en<-name_en_translation)" % n)
                if ayah_count != src["ayah_count"]:
                    p27_reasons.append("surah %d ayah_count mismatch" % n)
                if revelation != expected_revelation:
                    p27_reasons.append("surah %d revelation mismatch" % n)
        check_boolean("P27", not p27_reasons,
                       "surah rows match data/surah_meta.json field-for-field after the D-mapping; sha256 matches",
                       "; ".join(p27_reasons))

    finally:
        conn.close()

    return _finish()


def _finish(_conn=None):
    failed = 0
    for check_id, passed, message in CHECKS:
        if passed:
            print("PASS  %s  %s" % (check_id, message))
        else:
            failed += 1
            print("FAIL  %s  %s" % (check_id, message))

    total = len(CHECKS)
    if failed == 0:
        print("RESULT: PASS (%d checks)" % total)
        return 0
    else:
        print("RESULT: FAIL (%d of %d failed)" % (failed, total))
        return 1


if __name__ == "__main__":
    sys.exit(main())
