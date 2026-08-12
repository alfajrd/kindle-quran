#!/usr/bin/env python3
"""Adds surah introductions to an existing translation pack.

    python tools/build_surah_info.py --src <chapter_info.json>
                                     [--pack translations/itani.db]
                                     [--intro-id maududi]

The introductions are the LAST thing in `trans_surah_intro`, which has shipped
empty since the schema was written (docs/BACKLOG.md B1). This fills it.

WHOSE WORDS THESE ARE
---------------------
Not the translator's. The verse translation in the pack is Talal Itani's; these
introductions are Sayyid Abul Ala Maududi's, from Tafhim al-Qur'an. Two
different authors under two different licences in one file, so they are keyed
under their OWN `intro_id` and the pack records `intro_source` beside it.
Filing them under the translator's id would quietly attribute one man's writing
to another.

The Clear Quran's introductions -- the ones originally wanted -- remain
unobtainable: Furqaan Institute holds an exclusive licence (docs/BACKLOG.md).

LICENCE POSITION, STATED PLAINLY
--------------------------------
Maududi died in 1979, so Tafhim al-Qur'an is under copyright in every life+70
jurisdiction until roughly 2049. quran.com and QUL both serve it publicly and
neither records a licence grant. **Availability is not permission** -- the same
trap this project already documented for translations.

So this is a personal-use tool, on the same terms as everything else here: the
output goes to `translations/`, which `.gitignore` blocks and `check_m0.py` S4
proves is untracked. Nothing here may be redistributed.

WHAT IT DOES TO THE TEXT
------------------------
Converts the source HTML to plain text, because the reader renders plain text.
That is a format conversion and nothing else: no summarising, no truncation, no
rewording. Headings become `## Name` lines so the structure survives.

It also strips U+FEFF. Surah 101's source has one sitting inside a heading --
the same defect that nearly put a byte-order mark into Al-Fatiha's first words
(docs/ERRATA.md). Asserted absent afterwards rather than hoped for.

Stdlib only. No network -- point --src at a file you fetched yourself.
"""
import argparse
import html
import json
import os
import re
import sqlite3
import sys

TOTAL_SURAHS = 114

SCHEMA = """
CREATE TABLE IF NOT EXISTS trans_surah_intro (
  trans_id TEXT NOT NULL,
  surah    INTEGER NOT NULL,
  text     TEXT NOT NULL,
  PRIMARY KEY (trans_id, surah)
);
"""


def to_plain_text(raw):
    """HTML -> plain text, preserving the heading structure.

    Deliberately simple and deliberately lossy only in markup. Anything that
    changed the WORDS would make the pack a paraphrase of a copyrighted work
    rather than a copy of it, which is worse on every axis: less accurate to
    read and no better legally.
    """
    t = raw
    t = re.sub(r"<\s*h[1-6][^>]*>", "\n\n## ", t, flags=re.I)
    t = re.sub(r"<\s*/\s*h[1-6]\s*>", "\n", t, flags=re.I)
    t = re.sub(r"<\s*/\s*(p|div|li|tr)\s*>", "\n\n", t, flags=re.I)
    t = re.sub(r"<\s*br\s*/?\s*>", "\n", t, flags=re.I)
    t = re.sub(r"<\s*li[^>]*>", "- ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)

    # U+FEFF anywhere is a defect, not content. Surah 101's source carries one
    # inside a heading.
    t = t.replace("﻿", "")
    # Non-breaking space reads as a space; other C0 controls are not content.
    t = t.replace(" ", " ")
    t = "".join(ch for ch in t if ch == "\n" or ch == "\t" or ord(ch) >= 0x20)

    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def fail(msg):
    raise SystemExit("ASSERTION FAILED: " + msg)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="JSON: {surah: {text, source}}")
    ap.add_argument("--pack", default=os.path.join(root, "translations", "itani.db"))
    ap.add_argument("--intro-id", default="maududi")
    args = ap.parse_args()

    if not os.path.exists(args.pack):
        raise SystemExit("no pack at %s -- run build_translation.py first" % args.pack)

    with open(args.src, encoding="utf-8") as fh:
        raw = json.load(fh)

    intros, sources = {}, set()
    for key, value in raw.items():
        surah = int(key)
        text = to_plain_text(value["text"] if isinstance(value, dict) else value)
        if isinstance(value, dict) and value.get("source"):
            sources.add(value["source"])
        intros[surah] = text

    # --- assertions -------------------------------------------------------
    missing = [s for s in range(1, TOTAL_SURAHS + 1) if s not in intros]
    if missing:
        fail("no introduction for surah(s) %s" % missing[:8])
    extra = [s for s in intros if s < 1 or s > TOTAL_SURAHS]
    if extra:
        fail("introduction for non-existent surah(s) %s" % extra[:5])

    empty = [s for s, t in intros.items() if not t.strip()]
    if empty:
        fail("empty introduction for surah(s) %s" % empty[:5])

    with_bom = [s for s, t in intros.items() if "﻿" in t]
    if with_bom:
        fail("U+FEFF survived in surah(s) %s" % with_bom[:5])

    with_tags = [s for s, t in intros.items() if re.search(r"<[a-zA-Z/][^>]*>", t)]
    if with_tags:
        fail("HTML markup survived in surah(s) %s" % with_tags[:5])

    if len(sources) > 1:
        fail("mixed sources in one pack: %s" % sorted(sources))

    # --- write ------------------------------------------------------------
    conn = sqlite3.connect(args.pack)
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM trans_surah_intro WHERE trans_id = ?;", (args.intro_id,))
    conn.executemany(
        "INSERT INTO trans_surah_intro (trans_id, surah, text) VALUES (?, ?, ?);",
        [(args.intro_id, s, intros[s]) for s in sorted(intros)])

    source = sorted(sources)[0] if sources else "unrecorded"
    for key, value in (("intro_id", args.intro_id),
                       ("intro_source", source),
                       ("intro_count", str(len(intros))),
                       ("intro_licence", "copyright of its author; personal use only, "
                                         "not redistributable")):
        conn.execute("INSERT OR REPLACE INTO trans_meta (key, value) VALUES (?, ?);",
                     (key, value))
    conn.commit()

    n = conn.execute("SELECT COUNT(*) FROM trans_surah_intro WHERE trans_id = ?;",
                     (args.intro_id,)).fetchone()[0]
    if n != TOTAL_SURAHS:
        fail("wrote %d introductions, expected %d" % (n, TOTAL_SURAHS))
    conn.execute("VACUUM;")
    conn.close()

    lengths = sorted(len(t) for t in intros.values())
    print("wrote %d introductions to %s" % (n, args.pack))
    print("  intro_id   %s" % args.intro_id)
    print("  source     %s" % source)
    print("  length     shortest %d, median %d, longest %d chars"
          % (lengths[0], lengths[len(lengths) // 2], lengths[-1]))
    print("  licence    personal use only -- translations/ is gitignored, S4 enforces it")


if __name__ == "__main__":
    main()
