# Provenance — `2_255.txt`

- **Source**: Tanzil Uthmani edition of the Qur'an (`quran-uthmani.txt`), the
  standard Uthmani-script text distributed by Tanzil ( https://tanzil.net/download/ ,
  "Simple Enhanced" / Uthmani edition, downloaded from the Tanzil text-download
  page for the Uthmani script variant).
- **Verse**: 2:255 (Ayat al-Kursi), extracted verbatim, byte-for-byte, from the
  Tanzil Uthmani text. Nothing added, nothing removed, nothing normalised.
- **How it entered this repo**: originally, the text was fetched and
  verified by the M0 pipeline orchestrator (not the coder of that
  milestone) and staged at `.pipeline/ayah_2_255.txt` (797 bytes, UTF-8, no
  trailing newline, sha256
  `920a0a6c784cd0ec7dae3a75c1539fae4cf7b31051880f5085e4cd5239de06f8`), copied
  unchanged into `2_255.txt` and into `main.lua`'s verbatim literal.
  Recorded date those M0 files were assembled: 2026-08-06. That text came
  from alquran.cloud's mirror of Tanzil, which — as the corpus-scale
  replacement in `data/SOURCE.md` documents — differs from a genuine Tanzil
  download in material ways (different hamza encoding, different meem
  signs). When the corpus was replaced with a direct Tanzil download,
  2:255 was **re-extracted from that direct download** (797 → 791 bytes;
  three spurious small-meem marks the mirror had introduced are absent from
  the genuine Tanzil text) and both `2_255.txt` and `main.lua`'s verbatim
  literal were updated to the new bytes, copied through unchanged — never
  retyped. New sha256:
  `b036974542211b4c684147cc80b1943b932229e7d59d8e872035144f4aaaef9c`.
- **Edition name**: Tanzil Uthmani (`quran-uthmani.txt`), the same edition used
  by the wider project (`d:\Nekoweb\dev\quran-spec-v1.md` §3).
- **Tanzil's terms**: Tanzil's text-usage policy requires that the Qur'anic
  Arabic text **not be modified** in any way when redistributed, and that
  Tanzil be credited as the source. Both are honoured here: the bytes are
  copied unmodified (see `2_255.sha256`), and this file is the attribution
  record. Attribution string: "Tanzil Qur'an Text (Uthmani), https://tanzil.net".
- **Codepoint census** (informational, not a checked assertion beyond what
  `tools/check_m0.py` enforces): 424 codepoints / 791 UTF-8 bytes (was 427 /
  797 under the old, mirror-sourced pin — see "Correction (corpus
  replacement)" below); alef wasla (U+0671) x10; superscript alef (U+0670)
  x5; small waw (U+06E5) x4; shadda (U+0651) x13; sukun (U+0652) x23; maddah
  (U+0622-adjacent maddah forms) x4; tatweel (U+0640) **x1** — see next
  paragraph; ten lam-alef ligature sites; zero Arabic presentation-form
  codepoints; zero U+06DD.

## Note on the tatweel assertion (A6)

The text contains **exactly one** tatweel (U+0640), inside `وَلَا يَـُٔودُهُۥ`
("yauduhu" — "wearies Him"), where the tatweel carries a hamza above it and is
correct Uthmani orthography, not a typo or a copy-paste artefact. An earlier
draft of the M0 checker asserted "zero tatweel characters" as a generic
sanity rule; that assertion was **wrong** and has been corrected to assert
`== 1` before this milestone's text was committed, per the rule in the spec
that a failing presence/absence assertion against genuinely verbatim Tanzil
text means the assertion is wrong, never the text. No character was ever
removed from the Arabic to satisfy a check.

## Correction (Milestone 1) — how this file's provenance chain actually ran, historically

The paragraph above ("How it entered this repo") originally implied 2:255
was fetched directly from Tanzil for this file. On closer accounting during
Milestone 1, that was not quite what happened: the actual retrieval route
was **Tanzil Uthmani, obtained via alquran.cloud's `quran-uthmani`
edition**, which claims to redistribute the Tanzil text unmodified. At the
time, this exact verse — extracted from that same bulk fetch and hashed
independently — produced the identical digest already pinned
(`920a0a6c784cd0ec7dae3a75c1539fae4cf7b31051880f5085e4cd5239de06f8`), so the
mirror and the M0-reviewed text agreed with each other. That agreement did
**not**, it turned out, mean the mirror agreed with Tanzil — see the next
section.

## Correction (corpus replacement) — the mirror did not actually match Tanzil

Supplied with a genuine, direct Tanzil download for the whole corpus, only
2561 of 6236 ayat matched the mirror-sourced text byte-for-byte — different
hamza encoding, different meem signs. 2:255 was one of the ayat that
differed: the mirror's version carried three spurious small-meem marks
(U+06ED, U+06ED, U+06E2) that the genuine Tanzil text does not have. The old
pin (`920a0a6c78…`, 427 codepoints / 797 bytes, reviewed by a human at
Milestone 0 against *that* text) is retired. The new pin
(`b036974542211b4c684147cc80b1943b932229e7d59d8e872035144f4aaaef9c`, 424
codepoints / 791 bytes) was re-extracted from the direct Tanzil download —
the same file now vendored at `data/quran-uthmani.txt` — copied through
unchanged into `2_255.txt` and `main.lua`'s verbatim literal, never
retyped. This ayah is unaffected by the E1 basmala erratum
(`docs/ERRATA.md`): 2:255 has no basmala prefix, so nothing about it is
touched by `data/errata.tsv`. The M0 codepoint-by-codepoint human review is
not automatically re-validated by this substitution — it is recorded here as
a known limitation, same as the general one below.

## Limitation of the SHA-256 guard

`2_255.sha256` is generated from whatever bytes happen to be committed in
`2_255.txt` — it proves the two copies of the text inside this repository
(`data/2_255.txt` and the embedded literal in `main.lua`) stay identical over
time (`check_m0.py` check A3), but it cannot by itself prove the text
originally came from Tanzil. That provenance claim rests on this document and
on the structural sanity checks in `check_m0.py` (A4–A12: codepoint
whitelist, forbidden-codepoint checks, lam-alef/shadda/superscript-alef/alef-
wasla presence, stacked-harakat presence, and the 380–480 codepoint length
band). Nobody should treat a passing hash check as proof of Tanzil
provenance on its own.
