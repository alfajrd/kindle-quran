# Provenance — `quran-uthmani.txt` and `surah_meta.json`

## The governing principle (D0)

Prefer assertions derived from the text itself, or that structurally
validate against it, over assertions that trust a transcribed constant.
Where a constant is unavoidable, say plainly that it is a trusted input and
name what verified it. This document exists to discharge that obligation for
the two files in this directory.

| Trusted input | What verified it |
|---|---|
| `quran-uthmani.txt` — the corpus | 114 surahs / 6236 ayat / contiguous numbering, checked structurally on every `tools/build_pack.py` run (`tools/import_corpus.py` is retained for audit history but is no longer the path that produced this file — see "Retrieval chain" below); 2:255 hashes to `b036974542211b4c684147cc80b1943b932229e7d59d8e872035144f4aaaef9c`; vendored (byte-exact, as downloaded) digest `18c719bb3ba26d32ef457f40dad77cd28c4c5a34156833e26a8e5fcfdd246fb1`; post-errata canonical digest (what the pack actually contains, after `data/errata.tsv` is applied — see "The errata mechanism" below) `9ce47bd964c51283a4d31a36f0a8529723a82feb3900551de31e323e09a611aa` |
| `surah_meta.json` — 114 surah rows, sajdah refs, juz starts | Cross-validated against the corpus: all 114 `ayah_count` values match the per-surah counts in the corpus exactly. Two independent representations agreeing, not one source asserting. Its `sajdah` list matches a U+06E9 scan of the corpus (15 marks, both directions); its `juz_start` values form an exact partition of all 6236 ayat (0 missing, 0 overlapping) |
| `quran.koplugin/data/2_255.txt` | Reviewed by a human, byte by byte, at Milestone 0; re-pinned when the corpus was replaced with the direct Tanzil download (see below) |

Every one of those verifications is re-asserted by the pipeline, in the
pack, at build time and at verify time (`tools/build_pack.py`,
`tools/verify_pack.py`). None of it is taken on trust at runtime.

## Retrieval chain, as it actually happened

- **`quran-uthmani.txt`**: a **direct download from tanzil.net's own
  download form** (the Uthmani edition, `quran-uthmani.txt`), supplied for
  this milestone and vendored here **byte-exact**, including Tanzil's own
  trailing copyright/terms-of-use block (blank lines followed by lines
  starting with `#`). Earlier revisions of this repository sourced the
  corpus indirectly, via alquran.cloud's `quran-uthmani` mirror of the
  Tanzil text; that mirror differed from a genuine Tanzil download in
  material ways (different hamza encoding, different meem signs — only 2561
  of 6236 ayat matched byte-for-byte against this direct download). This
  file **replaces** that mirror-sourced corpus outright; nothing here is an
  edit of the old file, it is a new vendored file from a new, authoritative
  download. `tools/import_corpus.py` (the JSON-staged importer used for the
  old, mirror-sourced corpus) is kept for audit history but is **not** the
  path that produced the file now committed here — see the note at the top
  of that script.
- **`surah_meta.json`**: unaffected by the corpus replacement — still 114
  surah names (Arabic, transliteration, English meaning), ayah counts,
  revelation type, the sajdah cross-check list and the juz-start map,
  cross-validated against the new corpus exactly as it was against the old
  one (see the table above).

## The defect found and corrected (Milestone 1, mirror-sourced corpus)

The alquran.cloud response prepended a **U+FEFF byte-order mark to 1:1** —
the opening ayah of Al-Fatiha. Left alone it would have been stored as part
of the text and rendered as an invisible character at the very start of the
Qur'an. It was stripped (leading U+FEFF only; nothing else altered) before
that corpus was staged, in the milestone that has since been replaced by
the direct Tanzil download described above. `tools/import_corpus.py`,
`tools/build_pack.py` and `tools/verify_pack.py` each independently still
assert **zero U+FEFF anywhere, at every stage** — kept as a permanent guard
against this class of transport-layer artefact, not because the current
vendored file is known to carry one.

## The errata mechanism — corrections without editing the vendored file

`data/quran-uthmani.txt` stays byte-exact as Tanzil shipped it, forever —
that is what makes the "diff against a hand-downloaded Tanzil file" check in
`docs/BUILD.md` meaningful, and it is what Tanzil's redistribution terms
require. A confirmed defect in that vendored text (`docs/ERRATA.md` E1: a
spurious `U+0651` SHADDA on the basmala of 95:1 and 97:1, present in none of
the other 111 surahs and absent from Tanzil's own simple/minimal editions)
is therefore **not** corrected in the vendored file. It is corrected **at
build time**, from a declared, hash-verified erratum in `data/errata.tsv`:
`tools/build_pack.py` locates the ayah, verifies `sha256(current) ==
before`, applies the one declared structural edit (delete one specific,
already-present, hash-verified codepoint — never a textual
search-and-replace, never a constructed replacement string), and verifies
`sha256(result) == after`. Any mismatch — including Tanzil quietly fixing
this upstream, which would make `before` stop matching — is a hard build
failure, not a silent pass. The pack's `meta` table records how many errata
were applied and their ids (`errata_count`, `errata_ids`) so a future About
screen can disclose them. See `docs/ERRATA.md` for the full evidence and
decision record.

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
sha256(data/quran-uthmani.txt), as vendored (byte-exact) = 18c719bb3ba26d32ef457f40dad77cd28c4c5a34156833e26a8e5fcfdd246fb1
sha256 of the post-errata canonical serialisation          = 9ce47bd964c51283a4d31a36f0a8529723a82feb3900551de31e323e09a611aa
sha256(data/surah_meta.json)                                = e476c61626ccf1f2d8f3fd76727dbb144a3dd52e75a416de5d1e52bb5dd54bb1
```

These are two different numbers with two different jobs, and this
distinction is deliberate, not an inconsistency:

- The **vendored digest** is checked against the committed file itself and
  `data/quran-uthmani.sha256`, and proves the vendored file has not been
  touched since it was downloaded — it is the number a byte-exact
  redistribution obligation cares about.
- The **post-errata canonical digest** is what `quran.koplugin/data/quran.db`'s
  `meta.checksum` row and `quran.koplugin/data/manifest.json`'s
  `corpus_sha256` carry, because that is what the pack's `ayah` table
  actually contains (the two declared corrections in `data/errata.tsv`
  applied) — it is the number an on-device self-test cares about.

Both are duplicated as literal constants (deliberately — see D4 in
`.pipeline/spec.md`) in `tools/build_pack.py` and `tools/verify_pack.py`;
`tools/check_m1.py` and `tools/import_corpus.py` duplicate the vendored
digest only.

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
