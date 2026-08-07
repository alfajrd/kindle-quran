# Building and verifying the Qur'an pack

This covers Milestone 1: how `quran.koplugin/data/quran.db` is built from
the vendored corpus, how to verify it, and — the part that actually matters
for trusting the Arabic text — how to check the vendored corpus against
Tanzil yourself, by hand, independently of anything this repository claims.

## D0 — the principle behind every check below

> Prefer assertions derived from the text itself, or that structurally
> validate against it, over assertions that trust a transcribed constant.
> Where a constant is unavoidable, say plainly that it is a trusted input
> and name what verified it.

Nothing in this pipeline carries a hand-typed sajdah list, a hand-typed juz
table, or per-surah ayah-count spot-checks. Sajdah positions are scanned out
of the text (U+06E9); juz is validated as an exact partition of all 6236
ayat; per-surah ayah counts are cross-checked against `surah_meta.json`, not
assumed from it. See `data/SOURCE.md` for exactly what verified each of the
three trusted inputs this milestone relies on.

## Rebuilding the pack

From a clean checkout, with no network access required at all:

```
python tools/build_pack.py
```

This reads `data/quran-uthmani.txt` and `data/surah_meta.json` — both
already committed — re-derives and re-asserts every structural fact about
the corpus (surah/ayah counts, contiguous numbering, the codepoint
whitelist, the sajdah scan, the juz partition, the metadata cross-check),
applies the declared, hash-verified corrections in `data/errata.tsv` (see
"The errata mechanism" below), and writes a fresh
`quran.koplugin/data/quran.db`, `quran.koplugin/data/quran.db.sha256`, and
`quran.koplugin/data/manifest.json`.

## The errata mechanism

`data/quran-uthmani.txt` is Tanzil's own download, vendored **byte-exact**
and never edited — that is what makes the independent-verification `diff`
below meaningful, and what Tanzil's redistribution terms require. A
confirmed defect in that text (`docs/ERRATA.md` E1: a spurious `U+0651`
SHADDA on the basmala of 95:1 and 97:1) is therefore corrected **only at
build time**, from `data/errata.tsv`:

```
# surah<TAB>ayah<TAB>sha256(before)<TAB>sha256(after)<TAB>note
```

For each declared row, `tools/build_pack.py` locates the ayah, verifies
`sha256(current text) == before`, applies the one declared structural edit
(deletes one specific, already-present, hash-verified codepoint — never a
textual search-and-replace, and the corrected text is never typed or
constructed), then verifies `sha256(result) == after`. Any mismatch is a
hard build failure — including the case where Tanzil quietly fixes this
upstream, which would make `before` stop matching; the correct response
then is to delete the now-stale erratum row, not to force it through. The
pack's `meta` table records `errata_count` and `errata_ids` so a future
About screen can disclose what was corrected. `tools/verify_pack.py`
independently re-checks all of this against the vendored file and against
`data/errata.tsv` (P28–P30).

Because of this, two different digests matter and are not interchangeable:
the **vendored digest** (`data/quran-uthmani.txt` as downloaded,
byte-exact) and the **post-errata canonical digest** (what the pack's
`ayah` table actually contains). `meta.checksum` and
`manifest.json`'s `corpus_sha256` carry the latter.

`build_date` is a **pinned constant** (`2026-08-07`, overridable with
`--build-date`), never `datetime.now()` — a build that changes its own
metadata on every run would make "rebuild and compare" meaningless.

**What "reproducible" means here, precisely.** Re-running
`tools/build_pack.py` reproduces the same corpus digest and the same row
*content*, every time — that is the property `tools/verify_pack.py` checks
(P16: the canonical serialisation re-derived from the db's own rows hashes
to the pinned digest). The `.db` file's raw *bytes* can still differ across
SQLite versions (different page layout, different vacuum behaviour) — that
is expected, is not a bug, and is why this project never compares `.db`
files byte-for-byte, only by re-deriving and re-hashing their content.

## Verifying the pack

```
python tools/verify_pack.py
```

Standalone, stdlib-only, opens the db read-only, never imports anything
from `build_pack.py` — deliberately (see D4 in `.pipeline/spec.md`): a
shared serialisation/hashing helper would corrupt the build and the
verification identically, and the checks would pass on wrong data anyway.

## The whole gate, in one command

```
python tools/check_m1.py
```

Runs its own repo-structure/provenance-consistency checks (C1–C11), then
shells out to `tools/check_m0.py` and `tools/verify_pack.py` and folds their
results in. Exit 0 only if all three are clean.

**Milestone 2 (the reader) adds `tools/check_m2.py`, which is now the whole
gate**: `python tools/check_m2.py` runs its own R1–R12 static checks over
`quran.koplugin/reader.lua` and `quran.koplugin/settings.lua` (file
existence, Lua parseability, the two fenced blocks, the MUST-VERIFY
registry cross-check against `docs/VERIFY-M2.md`, typography constants,
`_meta.lua`'s version, the STEP-marker sync with `tools/paging_model.py`,
the on-device checklist in `README.md`, and the `io.*`/`os.*` ban), then
shells out to `tools/check_m1.py` (which itself nests `check_m0.py` and
`verify_pack.py`) and folds its result in. Exit 0 only if both parts are
clean. Nothing it does replaces the on-device checklist -- see `README.md`'s
"Milestone 2 — on-device checklist" for what only a real device can prove.

## Independent verification against Tanzil (the only thing that proves provenance)

Every digest in this repository proves the committed bytes have not drifted
*since they were committed*. **None of them prove the text originally came
from Tanzil.** The vendored corpus (`data/quran-uthmani.txt`) is a direct
download from Tanzil's own download form, vendored byte-exact — see
`data/SOURCE.md` for that chain in full, including the earlier,
mirror-sourced corpus this one replaced (only 2561 of 6236 ayat matched
byte-for-byte against a genuine Tanzil download, which is why the mirror
was replaced rather than kept). Even a direct download is not
self-certifying — a corrupted or tampered download would carry the same
"direct" provenance claim. The only thing that actually proves Tanzil
provenance is a human doing this:

1. Go to <https://tanzil.net/download/> and download the Uthmani script
   text (Tanzil calls this the "Uthmani" edition, plain text,
   `quran-uthmani.txt`) through the site's own form. There is no direct
   file URL — Tanzil serves this through a download form on purpose, which
   is exactly why an automated build cannot do this step.
2. Compare it against the vendored file:
   ```
   diff <hand-downloaded quran-uthmani.txt> data/quran-uthmani.txt
   ```
   A byte-for-byte match (after accounting for Tanzil's own file header, if
   their download includes one, and line-ending conventions) is what
   actually establishes Tanzil provenance for this repository's Arabic
   text. A green `tools/check_m1.py` run does **not** establish this by
   itself — it only proves internal consistency.
3. Record the result (date, Tanzil file's own reported version/date if any,
   whether the diff was clean) wherever this milestone's acceptance report
   lives.

**Do not** treat a mirror as a substitute for this. The obvious one,
`fawazahmed0/quran-api`'s `ara-quranuthmanienc`, carries a *different*
orthographic variant — a byte-comparison against it would fail on text that
is actually correct and invite "fixing" the Qur'an to make a build green.
This is why D1 rejected fetching from a mirror outright; see
`.pipeline/spec.md`.

## What is and is not covered by the corpus-scale limitation

The M0 SHA-256 guard had a known limitation, now restated at corpus scale:
if `data/quran-uthmani.txt`, `data/quran-uthmani.sha256`, the in-source
digest constants (`build_pack.py`, `verify_pack.py`, `check_m1.py`), and the
pack were all regenerated together from corrupted text, every check in this
pipeline passes. The digest only proves the copies committed here agree
with each other — not that they still agree with Tanzil. The manual `diff`
above is the only real mitigation. This is documented, not hidden, in
`data/SOURCE.md` and here.

## `order_rev` (revelation order) — deferred, not forgotten

`surah_meta.json` (both the staged file and the vendored copy) does not
carry a revelation-order field, so the `surah` table has no `order_rev`
column in Milestone 1's schema. Nothing M1 builds needs it. It is planned
for Milestone 3 (the navigator), sourced and cross-validated the same way
this milestone's metadata was — not invented, not sourced ad hoc now.

## FTS5 — the V15 answer

`.pipeline/spec.md`'s MUST-VERIFY V15 asked whether KOReader's bundled
SQLite is compiled with `SQLITE_ENABLE_FTS5`. **Unresolved on this
machine**: there is no KOReader/koreader-base checkout available here, and
no network access to fetch one, so `thirdparty/sqlite/CMakeLists.txt` (or
`Makefile.third`) could not be inspected, and neither could
`thirdparty/lua-ljsqlite3/`. This is explicitly on the "what only the
device can settle" list in `.pipeline/spec.md` — the answer needs either a
real koreader-base checkout or, empirically, running
`SELECT sqlite_compileoption_used('ENABLE_FTS5');` on-device.

It does not block anything here: M1's schema creates no FTS5 table, and the
`ayah` table stores each ayah's text exactly once with no denormalised
copies, so whichever way V15 lands, v2 search stays unblocked — either an
external-content FTS5 table over `ayah` (if FTS5 is present) or a
desktop-built plain inverted index (if it is not). See `.pipeline/spec.md`
§"FTS5 and v2 search" for both paths.

## Other MUST-VERIFY items this environment could not settle

V11–V14 and V16 (the `lua-ljsqlite3` require path, its exact method
signatures, whether a read-only open flag exists, whether the plugin
loader sets `self.path`, and the on-device SQLite version) could not be
checked against real KOReader/koreader-base source either, for the same
reason as V15 — no checkout, no network, on this machine. `quran.koplugin/
db.lua`'s header comment records exactly what was implemented for each,
and why, and flags all of it as unverified pending an on-device pass. None
of it is guessed silently; every uncertain call is wrapped in `pcall` and
surfaced as an explicit, path-naming error rather than allowed to crash
plugin load or fail silently.
