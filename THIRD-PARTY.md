# Third-party material

This repository redistributes work that is not ours. Each item below names its
source and the terms we redistribute it under. If you fork or repackage this,
these obligations travel with you.

---

## Qur'anic text — Tanzil Uthmani

- **File:** `quran.koplugin/data/2_255.txt`, and the verbatim literal inside
  `quran.koplugin/main.lua`
- **Source:** Tanzil Qur'an Text (Uthmani) — <https://tanzil.net>
- **Attribution string:** `Tanzil Qur'an Text (Uthmani), https://tanzil.net`

Tanzil's terms require that the Qur'anic Arabic text be redistributed
**unmodified** and that Tanzil be credited. Both are honoured:

- the bytes are copied unchanged, pinned by SHA-256
  (`920a0a6c784cd0ec7dae3a75c1539fae4cf7b31051880f5085e4cd5239de06f8`)
- `tools/check_m0.py` fails the build if a single byte changes
- full provenance is recorded in `quran.koplugin/data/SOURCE.md`

**Do not "clean", normalise, reflow or re-encode this text.** It is not
NFC-stable — Unicode normalisation *changes* it. A well-meaning tidy-up is the
most likely way this file gets corrupted.

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
