# Provenance — `quran-uthmani.txt` and `surah_meta.json`

## The governing principle (D0)

Prefer assertions derived from the text itself, or that structurally
validate against it, over assertions that trust a transcribed constant.
Where a constant is unavoidable, say plainly that it is a trusted input and
name what verified it. This document exists to discharge that obligation for
the two files in this directory.

| Trusted input | What verified it |
|---|---|
| `quran-uthmani.txt` — the corpus | 114 surahs / 6236 ayat / contiguous numbering, checked structurally by `tools/import_corpus.py` and re-checked on every `tools/build_pack.py` run; 2:255 hashes to the exact pin a human reviewed codepoint-by-codepoint in Milestone 0; canonical digest `5e6accd845ed3668a0ed45937a4626957b1f38d05598e3df573c6ad39fb45621` |
| `surah_meta.json` — 114 surah rows, sajdah refs, juz starts | Cross-validated against the corpus: all 114 `ayah_count` values match the per-surah counts in the corpus exactly. Two independent representations agreeing, not one source asserting. Its `sajdah` list matches a U+06E9 scan of the corpus (15 marks, both directions); its `juz_start` values form an exact partition of all 6236 ayat (0 missing, 0 overlapping) |
| `quran.koplugin/data/2_255.txt` | Reviewed by a human, byte by byte, at Milestone 0 |

Every one of those verifications is re-asserted by the pipeline, in the
pack, at build time and at verify time (`tools/build_pack.py`,
`tools/verify_pack.py`). None of it is taken on trust at runtime.

## Retrieval chain, as it actually happened

- **`quran-uthmani.txt`**: Tanzil Uthmani edition of the Qur'an text,
  obtained via **alquran.cloud's `quran-uthmani` edition**, which
  redistributes the Tanzil Uthmani text. This is **not** a direct download
  from tanzil.net — tanzil.net serves its text through a download form, and
  direct file URLs 404, so an unattended fetch from Tanzil directly was not
  possible. The bulk fetch was staged for this milestone's coder at
  `.pipeline/quran_uthmani_full.json` (keys `"surah:ayah"`, UTF-8) before
  implementation began; `tools/import_corpus.py` turned that staged JSON,
  unmodified, into the two files in this directory. The coder that ran the
  import did not re-fetch, retype, or re-derive the Arabic.
- **Tie to the already-reviewed text**: 2:255, extracted from this bulk
  corpus, hashes to the exact pin already shipped and independently
  reviewed codepoint-by-codepoint in Milestone 0
  (`920a0a6c784cd0ec7dae3a75c1539fae4cf7b31051880f5085e4cd5239de06f8`,
  see `quran.koplugin/data/SOURCE.md`). The bulk corpus is therefore the
  same edition as the text already in this repository.
- **`surah_meta.json`**: 114 surah names (Arabic, transliteration, English
  meaning), ayah counts, revelation type, the sajdah cross-check list and
  the juz-start map, staged at `.pipeline/surah_meta.json` and copied
  through byte-for-byte by `tools/import_corpus.py`.

## The defect found and corrected

The alquran.cloud response prepended a **U+FEFF byte-order mark to 1:1** —
the opening ayah of Al-Fatiha. Left alone it would have been stored as part
of the text and rendered as an invisible character at the very start of the
Qur'an. It was stripped (leading U+FEFF only; nothing else altered) before
the corpus was staged for this milestone, and the staged JSON, the corpus
digest above, and every copy in this repository all reflect the cleaned
text. `tools/import_corpus.py`, `tools/build_pack.py` and
`tools/verify_pack.py` each independently assert **zero U+FEFF anywhere, at
every stage** — this is a transport-layer artefact, a defect to reject
loudly, never to silently pass through.

## Tanzil's terms

Tanzil's text-usage policy requires that the Qur'anic Arabic text **not be
modified** in any way when redistributed, and that Tanzil be credited as the
source. Both are honoured here: the bytes are copied unmodified end to end
(vendored → `data/quran-uthmani.txt` → `quran.koplugin/data/quran.db`, each
step checksum-guarded), and `quran.db`'s `meta` table carries the
attribution string and Tanzil's terms verbatim so a future About screen can
display them (`attribution`, `licence`, `terms` keys — see the schema in
`.pipeline/spec.md` §"`meta` rows").

## The digests

```
sha256(data/quran-uthmani.txt)  = 5e6accd845ed3668a0ed45937a4626957b1f38d05598e3df573c6ad39fb45621
sha256(data/surah_meta.json)    = e476c61626ccf1f2d8f3fd76727dbb144a3dd52e75a416de5d1e52bb5dd54bb1
```

One number — the corpus digest — is checked in five places: the file
itself, `data/quran-uthmani.sha256`, `quran.koplugin/data/quran.db`'s
`meta.checksum` row, `quran.koplugin/data/manifest.json`'s
`corpus_sha256`, and the literal constant duplicated (deliberately — see
D4 in `.pipeline/spec.md`) in `tools/build_pack.py`, `tools/verify_pack.py`
and `tools/check_m1.py`.

## Independent verification (the only thing that proves Tanzil provenance)

A hash proves the file has not drifted since it was committed. It cannot
prove the file originally came from Tanzil. **The only thing that proves
that is a human, at review time, downloading `quran-uthmani.txt` from
tanzil.net's own download form by hand and `diff`-ing it byte-for-byte
against `data/quran-uthmani.txt`.** `docs/BUILD.md` gives the exact steps.
Nobody should treat a green `tools/check_m1.py` run as proof of Tanzil
provenance on its own — it proves internal consistency and structural
sanity, not origin.

## What was NOT enumerated by hand (and why)

Per D0, this pipeline carries **no hand-copied sajdah list, no hand-copied
juz table, and no per-surah ayah-count spot-checks**:

- **Sajdah** is derived by scanning every ayah for U+06E9 ARABIC PLACE OF
  SAJDAH — never read from a typed list. `surah_meta.json`'s `sajdah` array
  is used only as a cross-check, and the two must agree exactly (15 ayat,
  both directions). If a future edition disagrees, the build/verify fails —
  that is correct behaviour, and the response is to investigate the
  edition, never to edit the text.
- **Juz** is validated as an exact partition of the corpus (6236 covered, 0
  missing, 0 overlapping, all 30 non-empty, non-decreasing in `(surah,
  ayah)` order) — never trusted as a list. A shifted boundary breaks the
  partition and the check fires.
- **Obligatory-vs-recommended sajdah is deliberately not encoded.**
  Madhahib differ on which sajdah ayat are obligatory (notably 22:77, and
  41:37-vs-41:38), and that claim cannot be derived from the text itself.
  M1 stores only a plain `0`/`1` presence flag, derived from the U+06E9
  scan — nothing about obligation.

## A metadata assertion that was wrong, not the data (the M0 rule, applied to metadata)

Two of the 114 staged `name_en_translation` values are genuinely
comma-separated alternate meanings: surah 97 is `"The Power, Fate"`, surah
103 is `"The Declining Day, Epoch"`. `tools/verify_pack.py`'s P26 check
(Latin-column charset) originally whitelisted only ASCII letters, `-`, `'`
and space, per the spec text. Both of those staged values failed that check
on first build. Per the M0 rule — a failing presence/absence assertion
against genuinely verbatim, trusted text means the assertion is wrong, never
the text — the whitelist was widened to also allow `,`. No metadata value
was edited to make a check pass.

## `order_rev` (revelation order) — deferred, not forgotten

`surah_meta.json` does not carry revelation-order numbers, so the `surah`
table does not either. This lands in a later milestone, from a source
staged and cross-validated the same way this one was — see `docs/BUILD.md`.

## Limitation of the SHA-256 guard

Same limitation as `quran.koplugin/data/SOURCE.md` already states for
2:255, now at corpus scale: if `data/quran-uthmani.txt`,
`data/quran-uthmani.sha256`, the in-source digest constants, and the pack
were all regenerated together from corrupted text, every check in this
pipeline passes — the digest only proves internal self-consistency between
the copies committed here, not that the text still matches Tanzil. The only
real mitigation is a human `diff` against a hand-downloaded Tanzil file at
review time (see "Independent verification" above). Nobody should mistake a
passing `tools/check_m1.py` run for proof of provenance on its own.
