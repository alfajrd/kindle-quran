# Third-party material

This repository redistributes work that is not ours. Each item below names its
source and the terms we redistribute it under. If you fork or repackage this,
these obligations travel with you.

---

## Qur'anic text — Tanzil Uthmani

- **File (Milestone 0 pin):** `quran.koplugin/data/2_255.txt`, and the
  verbatim literal inside `quran.koplugin/main.lua`
- **File (whole text):** `data/quran-uthmani.txt` — all 6236 ayat,
  `surah|ayah|text` per line, plus Tanzil's own trailing copyright block,
  vendored byte-exact and pinned by SHA-256
  (`18c719bb3ba26d32ef457f40dad77cd28c4c5a34156833e26a8e5fcfdd246fb1`).
  Built into `quran.koplugin/data/quran.db`, which carries the same
  attribution and terms in its `meta` table, along with a `meta.checksum`
  of the pack's own content (post-errata, see below):
  `9ce47bd964c51283a4d31a36f0a8529723a82feb3900551de31e323e09a611aa`.
- **Source:** Tanzil Qur'an Text (Uthmani) — <https://tanzil.net>, a
  **direct download** from Tanzil's own download form (see `data/SOURCE.md`
  and `docs/BUILD.md` for the full chain and the independent-verification
  procedure). An earlier revision of this repository sourced the whole text
  indirectly, via alquran.cloud's `quran-uthmani` mirror; that mirror
  turned out to differ from Tanzil's own text in material ways (only 2561
  of 6236 ayat matched byte-for-byte) and has been replaced outright, not
  edited.
- **Attribution string:** `Tanzil Qur'an Text (Uthmani), https://tanzil.net`

**Licence: Creative Commons Attribution 3.0 (CC BY 3.0)**, per Tanzil's
Terms of Use. Its terms require that the Qur'anic Arabic text be
redistributed **unmodified** and that Tanzil be credited. Both are honoured:

- the vendored bytes are copied unchanged, pinned by SHA-256
  (2:255: `b036974542211b4c684147cc80b1943b932229e7d59d8e872035144f4aaaef9c`;
  whole text as vendored: `18c719bb3ba26d32ef457f40dad77cd28c4c5a34156833e26a8e5fcfdd246fb1`)
- `tools/check_m0.py`, `tools/build_pack.py` and `tools/verify_pack.py` all
  fail loudly if a single byte of the vendored text changes
- one confirmed defect in the vendored text (a spurious mark on the basmala
  of 95:1 and 97:1; see `docs/ERRATA.md` E1) is corrected **only at build
  time**, from a declared, hash-verified erratum
  (`data/errata.tsv`) — the vendored file itself is never edited, which is
  what "unmodified" requires
- full provenance is recorded in `quran.koplugin/data/SOURCE.md` (2:255) and
  `data/SOURCE.md` (the whole text)

**Do not "clean", normalise, reflow or re-encode this text.** It is not
NFC-stable — 5771 of the 6236 ayat *change* under Unicode normalisation. A
well-meaning tidy-up is the most likely way this text gets corrupted.

---

## Font — Scheherazade New

- **File:** `fonts/ScheherazadeNew-Regular.ttf` (v4.500)
- **Copyright:** © 2006–2024 SIL International
- **Licence:** SIL Open Font License 1.1 — full text in `fonts/OFL.txt`
- **Source:** <https://github.com/silnrsi/font-scheherazade>

The OFL permits redistribution, bundling and sale of the font **with** the
software, provided the licence accompanies it and the font is not sold on its
own. `fonts/OFL.txt` and `fonts/FONTLOG.txt` are included unmodified for that
reason — including their original CRLF line endings.

---

## Deliberately NOT included

**KFGQPC Uthmanic Script HAFS.** This is the King Fahd Glorious Qur'an Printing
Complex typeface — the official Madani mushaf face, and the most authentic
option for Uthmani text. It is **proprietary**: it may not be reproduced or
modified without express written approval, which makes it incompatible with
redistribution here.

You may install it on your own device and point `ARABIC_FONT` at it. We cannot
ship it. If this project ever wants that typeface distributed, it needs written
permission from the Complex first.

---

## Runtime dependency

This is a plugin for **KOReader** (<https://github.com/koreader/koreader>),
which is licensed AGPL-3.0. KOReader is not bundled here — it is a separate
program the user installs — but this plugin is useless without it.


### Known defect in the upstream text

Tanzil's Uthmani edition carries a spurious `U+0651` SHADDA on the basmala of
95:1 and 97:1, where 111 other surahs have none. Their own simple and minimal
editions do not have it, which identifies it as an upstream defect rather
than a variant reading.

It is **not corrected in the vendored file.** "Unmodified" means unmodified,
and editing scripture to tidy a checksum is not a licence-compliant act.
`data/quran-uthmani.txt` still carries the defect, byte-exact, forever. The
correction is applied only at **build time**, from a declared, hash-verified
erratum in `data/errata.tsv` (`tools/build_pack.py` locates the ayah,
verifies the hash before, applies one hash-verified codepoint deletion,
verifies the hash after — any mismatch is a hard build failure), so the
*pack* (`quran.koplugin/data/quran.db`) carries the corrected text while the
*vendored source* does not. See `docs/ERRATA.md` for the evidence and the
decision.
