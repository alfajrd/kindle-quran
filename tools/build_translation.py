#!/usr/bin/env python3
"""Builds a side-loadable translation pack from a verse-by-verse source archive.

    python tools/build_translation.py --src <archive.zip>
                                      [--trans-id itani]
                                      [--out translations/<trans_id>.db]
                                      [--build-date YYYY-MM-DD]
                                      [--allow-unpinned]

The Arabic pack (`build_pack.py`) and this are deliberately separate programs
producing separate files. The Arabic is settled -- Tanzil, CC BY 3.0, vendored
and committed. Translations are not: each carries its own licence, most are
unresolved (`docs/BACKLOG.md` B1), and none is committed to this repository.
Keeping them in a second .db is what lets the translation be swapped, or
absent, without touching the scripture.

WHAT THIS DOES NOT DO
---------------------
It does not download anything. Point `--src` at an archive you obtained
yourself, under a licence you have checked. The pinned digest below records
which archive this program was written against; it is a reproducibility
statement, not a licence, and not an endorsement of any particular source.

The output goes to `translations/`, which `.gitignore` blocks. That is
deliberate and should not be worked around: see `translations/README.md`.

VERBATIM, LIKE THE ARABIC
-------------------------
The text is stored exactly as read -- no normalisation, no quote
straightening, no whitespace collapsing beyond stripping the line terminator
the archive format imposes. Two reasons. Every translation worth using is
under a licence whose least ambiguous term is the one about not modifying it
(ClearQuran's is CC BY-NC-ND, whose ND clause is precisely this), and the
project already learned in `docs/ERRATA.md` that a pipeline which "tidies"
scripture is a pipeline that silently corrupts it.

Stdlib only. No network. No `unicodedata.normalize`, ever.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import zipfile

SCHEMA_VERSION = 1

# The archive this program was written and verified against:
# ClearQuran "verse by verse", edition A (Allah), Talal Itani.
# Recorded so a rebuild can prove it used the same bytes. A different archive
# is not an error -- pass --allow-unpinned -- but it is not this one, and the
# structural assertions below become the only guarantee you have.
PINNED_SOURCE_SHA256 = "4d46b054fc73ca56477843d276cf0000b9f6ddfe0f751e7c7e9017b96b68b38b"

# Filenames in the archive: "SSS-AAA.txt", ayah 000 being the surah's basmala.
ENTRY_RE = re.compile(r"^(\d{3})-(\d{3})\.txt$")

TOTAL_AYAT = 6236
TOTAL_SURAHS = 114
# Surah 1's basmala is ayah 1 of the surah itself, and surah 9 has none. So a
# complete source carries 114 - 2 = 112 basmala entries, and exactly those.
SURAHS_WITHOUT_SEPARATE_BASMALA = (1, 9)
EXPECTED_BASMALA_COUNT = TOTAL_SURAHS - len(SURAHS_WITHOUT_SEPARATE_BASMALA)

BASMALA_AYAH = 0

SCHEMA = """
CREATE TABLE trans_meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE translation (
  trans_id TEXT NOT NULL,
  surah    INTEGER NOT NULL,
  ayah     INTEGER NOT NULL,   -- 0 = the surah's basmala, where it has one
  text     TEXT NOT NULL,
  PRIMARY KEY (trans_id, surah, ayah)
);

-- Ships in the schema from the start, and may legitimately be empty.
--
-- Surah introductions are the translator's own prose, with their own
-- copyright, distinct from the verse translation. A reader who swaps
-- translations should get that translation's intros, so this is keyed by
-- trans_id like everything else.
--
-- No obtainable translation currently has them: the one that does (The Clear
-- Quran, Khattab) is under an exclusive licence and is not distributable --
-- see docs/BACKLOG.md. The reader must therefore treat a missing intro as
-- "nothing to show" rather than an error, which it has to do anyway, since no
-- future pack is guaranteed to carry them.
CREATE TABLE trans_surah_intro (
  trans_id TEXT NOT NULL,
  surah    INTEGER NOT NULL,
  text     TEXT NOT NULL,
  PRIMARY KEY (trans_id, surah)
);

CREATE INDEX idx_translation_surah ON translation (trans_id, surah);
"""


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_entry(zf, name):
    """Decode one entry, stripping only the BOM and the line terminator.

    `utf-8-sig` because these archives are Windows-authored and the BOM is
    routine; a stray U+FEFF entering the text is exactly the defect that hit
    the Arabic corpus on 1:1 (docs/ERRATA.md). Newlines are normalised to \\n
    and the trailing one removed -- that is a file-format artefact, not
    content. Nothing else is touched.
    """
    raw = zf.read(name).decode("utf-8-sig")
    return raw.replace("\r\n", "\n").replace("\r", "\n").strip("\n")


def read_source(path):
    """-> (verses, basmalas) keyed by (surah, ayah) / surah."""
    verses = {}
    basmalas = {}
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        for name in names:
            base = os.path.basename(name)
            m = ENTRY_RE.match(base)
            if not m:
                continue
            surah, ayah = int(m.group(1)), int(m.group(2))
            text = read_entry(zf, name)
            if ayah == BASMALA_AYAH:
                basmalas[surah] = text
            else:
                verses[(surah, ayah)] = text
    return verses, basmalas


def fail(msg):
    raise SystemExit("ASSERTION FAILED: " + msg)


def run_assertions(verses, basmalas, per_surah):
    """Every structural fact re-derived and re-checked on every build.

    A silently truncated scripture is the worst bug this project can ship, and
    a translation is no less scripture-shaped than the Arabic. The Arabic
    builder makes the same argument at more length; the checks here are its
    counterpart for a source whose shape we do not control.
    """
    if len(verses) != TOTAL_AYAT:
        fail("expected %d verses, found %d" % (TOTAL_AYAT, len(verses)))

    surahs = sorted({s for s, _ in verses})
    if surahs != list(range(1, TOTAL_SURAHS + 1)):
        fail("surah ids are not exactly 1..%d (found %d distinct)"
             % (TOTAL_SURAHS, len(surahs)))

    for surah in surahs:
        expected = per_surah[surah]
        got = sorted(a for s, a in verses if s == surah)
        if len(got) != expected:
            fail("surah %d: expected %d ayat, found %d" % (surah, expected, len(got)))
        if got != list(range(1, expected + 1)):
            fail("surah %d: ayah numbers are not contiguous 1..%d" % (surah, expected))

    empty = [k for k, v in verses.items() if not v.strip()]
    if empty:
        fail("%d verse(s) are empty, first %s" % (len(empty), empty[0]))

    # Basmala coverage: present for every surah that has one, absent for the
    # two that do not. Getting this wrong in either direction means the source
    # numbers its verses differently from the Arabic pack, and the two would
    # silently misalign at read time.
    if len(basmalas) != EXPECTED_BASMALA_COUNT:
        fail("expected %d basmala entries, found %d"
             % (EXPECTED_BASMALA_COUNT, len(basmalas)))
    for surah in SURAHS_WITHOUT_SEPARATE_BASMALA:
        if surah in basmalas:
            fail("surah %d must not carry a separate basmala entry" % surah)
    missing = [s for s in surahs
               if s not in SURAHS_WITHOUT_SEPARATE_BASMALA and s not in basmalas]
    if missing:
        fail("no basmala entry for surah(s) %s" % missing[:5])

    distinct = set(basmalas.values())
    if len(distinct) != 1:
        fail("basmala text is not identical across surahs (%d variants)" % len(distinct))

    # A translation pack containing Arabic means the wrong file was passed --
    # most of these archives ship an Arabic sibling beside the English one.
    for (surah, ayah), text in verses.items():
        for ch in text:
            if 0x0600 <= ord(ch) <= 0x06FF or 0xFB50 <= ord(ch) <= 0xFEFF:
                fail("%d:%d contains Arabic-range U+%04X -- is this a translation?"
                     % (surah, ayah, ord(ch)))


def canonical_digest(trans_id, verses, basmalas):
    """Digest of the pack's content, independent of SQLite's file layout.

    Same reasoning as the Arabic pack: hash a canonical serialisation derived
    from the rows, so a rebuild on another SQLite version still verifies.
    """
    h = hashlib.sha256()
    for surah in range(1, TOTAL_SURAHS + 1):
        if surah in basmalas:
            h.update(("%s|%d|%d|%s\n" % (trans_id, surah, BASMALA_AYAH,
                                         basmalas[surah])).encode("utf-8"))
        ayat = sorted(a for s, a in verses if s == surah)
        for ayah in ayat:
            h.update(("%s|%d|%d|%s\n" % (trans_id, surah, ayah,
                                         verses[(surah, ayah)])).encode("utf-8"))
    return h.hexdigest()


def build(src, out_path, trans_id, meta_overrides, build_date, allow_unpinned):
    digest = sha256_file(src)
    if digest != PINNED_SOURCE_SHA256:
        msg = ("source archive sha256 %s does not match the pinned %s"
               % (digest, PINNED_SOURCE_SHA256))
        if not allow_unpinned:
            raise SystemExit(
                "ASSERTION FAILED: " + msg
                + "\n\nThis program was written against that archive. If you "
                  "intend to build\nfrom a different one, pass --allow-unpinned "
                  "and read the structural\nassertions -- they become your only "
                  "guarantee.")
        print("WARNING: %s (proceeding, --allow-unpinned)" % msg)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "data", "surah_meta.json"), encoding="utf-8") as fh:
        surah_meta = json.load(fh)["surahs"]
    per_surah = {s["number"]: s["ayah_count"] for s in surah_meta}
    if sum(per_surah.values()) != TOTAL_AYAT:
        fail("surah_meta.json ayah counts sum to %d, not %d"
             % (sum(per_surah.values()), TOTAL_AYAT))

    verses, basmalas = read_source(src)
    run_assertions(verses, basmalas, per_surah)
    checksum = canonical_digest(trans_id, verses, basmalas)

    meta = {
        "schema_version": str(SCHEMA_VERSION),
        "trans_id": trans_id,
        "build_date": build_date,
        "source_sha256": digest,
        "checksum": checksum,
        "ayah_count": str(len(verses)),
        "basmala_count": str(len(basmalas)),
        "intro_count": "0",
    }
    meta.update(meta_overrides)
    for required in ("name", "translator", "licence", "source_url", "attribution"):
        if not meta.get(required):
            fail("meta.%s is required -- a pack with no licence recorded is a "
                 "pack nobody can later reason about" % required)

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db", dir=os.path.dirname(out_path) or ".")
    os.close(tmp_fd)
    os.unlink(tmp_path)
    try:
        conn = sqlite3.connect(tmp_path)
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO trans_meta (key, value) VALUES (?, ?);",
                         sorted(meta.items()))
        rows = []
        for surah in range(1, TOTAL_SURAHS + 1):
            if surah in basmalas:
                rows.append((trans_id, surah, BASMALA_AYAH, basmalas[surah]))
            for ayah in sorted(a for s, a in verses if s == surah):
                rows.append((trans_id, surah, ayah, verses[(surah, ayah)]))
        conn.executemany(
            "INSERT INTO translation (trans_id, surah, ayah, text) VALUES (?, ?, ?, ?);",
            rows)
        conn.commit()

        got = conn.execute("SELECT COUNT(*) FROM translation WHERE ayah > 0;").fetchone()[0]
        if got != TOTAL_AYAT:
            fail("post-write verse count is %d, not %d" % (got, TOTAL_AYAT))
        conn.execute("VACUUM;")
        conn.close()
        os.replace(tmp_path, out_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    return meta, len(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="verse-by-verse source archive (.zip)")
    ap.add_argument("--trans-id", default="itani")
    ap.add_argument("--out", default=None)
    ap.add_argument("--build-date", default="2026-08-12")
    ap.add_argument("--allow-unpinned", action="store_true")
    ap.add_argument("--name", default="The Quran: Modern English Translation")
    ap.add_argument("--translator", default="Talal Itani")
    ap.add_argument("--licence", default="CC BY-NC-ND")
    ap.add_argument("--source-url", default="https://www.clearquran.com/")
    ap.add_argument("--attribution",
                    default="Translated by Talal Itani. www.ClearQuran.com. "
                            "Provided under the Creative Commons "
                            "Attribution-NonCommercial-NoDerivs licence.")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = args.out or os.path.join(root, "translations", "%s.db" % args.trans_id)
    os.makedirs(os.path.dirname(out), exist_ok=True)

    overrides = {
        "name": args.name,
        "translator": args.translator,
        "licence": args.licence,
        "source_url": args.source_url,
        "attribution": args.attribution,
    }
    meta, rows = build(args.src, out, args.trans_id, overrides,
                       args.build_date, args.allow_unpinned)

    print("wrote %s" % out)
    print("  rows        %d  (%s verses + %s basmala)"
          % (rows, meta["ayah_count"], meta["basmala_count"]))
    print("  checksum    %s" % meta["checksum"])
    print("  source      %s" % meta["source_sha256"])
    print("  licence     %s" % meta["licence"])
    print("  intros      %s  (schema present; see docs/BACKLOG.md)" % meta["intro_count"])


if __name__ == "__main__":
    main()
