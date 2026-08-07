# Third-party material

This repository redistributes work that is not ours. Each item below names its
source and the terms we redistribute it under. If you fork or repackage this,
these obligations travel with you.

---

## Qur'anic text — Tanzil Uthmani

- **File (Milestone 0 pin):** `quran.koplugin/data/2_255.txt`, and the
  verbatim literal inside `quran.koplugin/main.lua`
- **File (Milestone 1, the whole text):** `data/quran-uthmani.txt` — all
  6236 ayat, `surah|ayah|text` per line, vendored and pinned by SHA-256
  (`5e6accd845ed3668a0ed45937a4626957b1f38d05598e3df573c6ad39fb45621`).
  Built into `quran.koplugin/data/quran.db`, which carries the same
  attribution and terms in its `meta` table.
- **Source:** Tanzil Qur'an Text (Uthmani) — <https://tanzil.net>. The
  whole-text file was obtained via alquran.cloud's `quran-uthmani`
  redistribution of that same Tanzil edition (tanzil.net serves the text
  through a download form, not a fetchable URL — see `data/SOURCE.md` and
  `docs/BUILD.md` for the full chain and the independent-verification
  procedure).
- **Attribution string:** `Tanzil Qur'an Text (Uthmani), https://tanzil.net`

**Licence: Creative Commons Attribution 3.0 (CC BY 3.0)**, per Tanzil's
Terms of Use. Its terms require that the Qur'anic Arabic text be
redistributed **unmodified** and that Tanzil be credited. Both are honoured:

- the bytes are copied unchanged, pinned by SHA-256
  (2:255: `920a0a6c784cd0ec7dae3a75c1539fae4cf7b31051880f5085e4cd5239de06f8`;
  whole text: `5e6accd845ed3668a0ed45937a4626957b1f38d05598e3df573c6ad39fb45621`)
- `tools/check_m0.py`, `tools/build_pack.py` and `tools/verify_pack.py` all
  fail loudly if a single byte changes
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

It is **not corrected here.** "Unmodified" means unmodified, and editing
scripture to tidy a checksum is not a licence-compliant act. See
`docs/ERRATA.md` for the evidence and the decision.
