# `quran.koplugin` — Milestone 1: the pack is the scripture, provably

Milestone 0 was a go/no-go gate: one hard-coded, byte-exact Tanzil Uthmani
ayah (2:255, Ayat al-Kursi), full-screen, to prove Arabic shaping, joining
and harakat work on this device at all. That checklist is kept below because
it is still the reproducible on-device rendering check.

**Milestone 1 adds the whole Qur'an, as a checksummed SQLite pack**
(`quran.koplugin/data/quran.db`, all 114 surahs / 6236 ayat), built and
verified by a reproducible desktop pipeline (`docs/BUILD.md`), and changes
the plugin so the ayah it displays is **read out of that pack** at runtime —
the M0 literal (`PIN_2_255`) is kept only as a tripwire the pack's own text
is compared against, never displayed itself. If the pack is missing,
unreadable, or disagrees with the pin, the plugin shows a loud, specific
error and displays nothing else; it never silently falls back to the pin.

If you are looking for the wider project plan, see
`docs/SPEC-v1.md`. For how the pack is built, rebuilt and
independently verified against Tanzil, see `docs/BUILD.md`.

## What this is not

- Not a font project, but it does now ship one. Milestone 0 originally
  relied on KOReader's fallback (Noto Sans Arabic). That rendered correctly
  but is a *sans-serif*, which reads wrong for scripture. Scheherazade New
  (SIL, OFL 1.1) is now vendored in `fonts/` and set as `ARABIC_FONT`.
  Verified against this ayah: full coverage of all 48 codepoints used, with
  GSUB and GPOS tables present (joining and mark positioning).
- Not a Qur'an reader. One verse, no navigation, no second verse, no surah
  list, no bookmarks.
- Not a deep link. The KUAL "Qur'an" entry starts KOReader; you then open the
  plugin from **KOReader's own menu**. That is intentional (see "KUAL entry"
  below), not a bug.

## Install (jailbroken Kindle Paperwhite 11)

1. Confirm the Kindle is jailbroken and KOReader is already installed and
   launches. If it doesn't, stop here — this gates everything else in the
   project.
2. USB-mount the Kindle.
3. Copy `quran.koplugin/` to `/mnt/us/koreader/plugins/quran.koplugin/`.
3b. **Confirm `quran.db` actually copied.** `quran.koplugin/data/quran.db`
   is a ~1.5 MB binary file inside the folder you just copied — some sync
   tools and some previous manual copies skip large/binary files silently.
   Check that `/mnt/us/koreader/plugins/quran.koplugin/data/quran.db` exists
   and is a similar size to the one in this repo. Without it, the plugin
   opens but every ayah lookup fails loudly (see "Pack missing on device"
   below) — this is deliberate (D5: never fall back to the pin), not a bug.
3c. **Milestone 2 adds two more Lua files inside the same folder:**
   `quran.koplugin/quranreader.lua` and `quran.koplugin/quransettings.lua`. Copying
   `quran.koplugin/` wholesale (step 3) already carries them — this is
   just confirming: check that
   `/mnt/us/koreader/plugins/quran.koplugin/quranreader.lua` and
   `.../settings.lua` both exist after the copy. Without either one, the
   plugin still loads (M0/M1's two items still work) but the five
   "Qur'an — read ..." reader items report the failure instead of opening
   (see edge case 16 in `.pipeline/spec.md`) rather than being silently
   absent.
4. Copy `extensions/quran/` to `/mnt/us/extensions/quran/`.
4b. Copy `fonts/ScheherazadeNew-Regular.ttf` to `/mnt/us/koreader/fonts/`.
   Without it the plugin falls back to KOReader's default sans — legible,
   but not what you want to look at.
5. Eject the Kindle.
6. Open KUAL → **"Qur'an"**. This starts KOReader (it does not open the
   plugin directly — see "KUAL entry" below).
7. In KOReader's File Manager: top menu → **Tools** (some KOReader versions
   call it **"More tools"** — check both) → **"Qur'an — pack self-test"**
   first (confirms the pack opened, its counts and checksum, and whether
   2:255 matches the pin), then **"Qur'an — test ayah (2:255)"** (renders the
   ayah read from the pack).
8. If neither menu item is there, check KOReader's crash log at
   `/mnt/us/koreader/crash.log`. That is where a Lua error thrown while
   loading the plugin surfaces — KOReader silently skips a plugin that
   throws at load time, so "the menu item isn't there" is the most likely
   first-run symptom, and the crash log is the only way to debug it.

### Pack missing on device

If `quran.db` was not copied (or was copied to the wrong path), **"Qur'an —
test ayah (2:255)"** and **"Qur'an — pack self-test"** both show a loud,
specific `Qur'an: pack error` message naming the exact path the plugin tried
to open. There is no silent fallback to the old hard-coded pin — a pack
error must look like an error, not like Milestone 0 quietly reappearing.

### Milestone 1 device checklist

Beyond the M0 rendering checklist below (still the correct way to judge
Arabic shaping), Milestone 1 adds one more question: **does the displayed
text genuinely come from `quran.db`, and does it match what was verified on
desktop?**

1. Open **"Qur'an — pack self-test"**. Record: `pack_id`, `build_date`,
   `surah_count` / `ayah_count` (should read `114` / `6236`, counted from the
   tables, not trusted from `meta`), `checksum` (should read
   `9ce47bd964c51283a4d31a36f0a8529723a82feb3900551de31e323e09a611aa` — the
   pack's own post-errata content digest, not the vendored file's digest;
   see `data/SOURCE.md`), `errata_count` (should read `2`), and the `2:255
   pin` line (should read `MATCH`).
2. Open **"Qur'an — test ayah (2:255)"**. The Arabic shown must render
   identically to the Milestone 0 photo (same shaping, same joining, same
   harakat, no tofu) — it is now sourced from the pack, not from the
   `PIN_2_255` literal, so this also re-proves M0's rendering result still
   holds end-to-end through the database.
3. On KOReader's Lua console or via `ls`, confirm **no `quran.db-wal` or
   `quran.db-journal` file** appears next to `quran.db` after use — the pack
   is opened read-only and must never write to `/mnt/us`.
4. Record `SELECT sqlite_version();` and whether
   `sqlite_compileoption_used('ENABLE_FTS5')` if you can reach KOReader's Lua
   console (see `.pipeline/spec.md`'s MUST-VERIFY V15/V16 — unresolved on
   the desktop machine that built this pack; only the device can answer).
5. Time from menu tap to rendered ayah, roughly, by counting — should feel
   under a second.
6. Free space on `/mnt/us` before and after copying (`quran.db` adds
   roughly 1.5 MB).

See `docs/BUILD.md` for how the pack itself was built and how to
independently verify it against a hand-downloaded Tanzil file.

## Milestone 2 — on-device checklist

Milestone 2 turns the plugin into a reader: open a surah, page forward and
back through it continuously, come back later to exactly where you
stopped, with Arabic size and line height adjustable at runtime and a grey
ruled line under every line of text. It ships **no navigator** — the five
"Qur'an — read ..." menu items (last position, plus the four hard-coded
test surahs 1/2/9/114) are scaffolding for Milestone 3, not a finished
feature; see `.pipeline/spec.md` §5.1.

**Touch zones**, full screen, no chrome: `W`/`H` are screen width/height.

| Zone | Region | Action |
|---|---|---|
| MENU | `x` in `[0.25W, 0.75W)` and `y` in `[0, 0.10H)` | Open the settings dialog |
| PREV | everything else with `x < 0.5W` | Previous page |
| NEXT | everything else with `x >= 0.5W` | Next page |

`NEXT` is on the **right** — LTR-style, even though the text is RTL — to
match KOReader's own reader on this device. D5 below asks you to judge
whether that still feels right in Arabic; it is one constant
(`FORWARD_ON_RIGHT` in `quranreader.lua`) to flip if not.

Ten minutes on a Paperwhite 11, in this order. Each item is pass/fail with
no judgement call except D5's direction question, which is marked as such.

D13 is the exception to "ten minutes": it needs a file edit over USB.
It earns that because 2:282 is the only ayah long enough to force the
multi-page overflow path, and paging to it by hand takes 60-100 taps —
which is why the earlier steps never reach it. Seeding the saved position
also exercises the position-read path with a value this build did not
write itself.
`docs/VERIFY-M2.md` has the full MUST-VERIFY registry (V20–V36) that most
FAIL columns below point back to.

| id | Do this | PASS | FAIL means |
|---|---|---|---|
| D1 | Open KOReader's main menu → More tools. | All seven `Qur'an —` items are present. | Plugin threw at load; read `/mnt/us/koreader/crash.log`. |
| D2 | Tap "read An-Nas (114)". | The whole surah renders, Arabic shaped and joined, with an ayah marker (`۝` + Arabic-Indic digits) after each ayah. | If markers show as boxes/nothing: set `AYAH_MARKER_STYLE = "ornate"` in `quranreader.lua` and retest. Never a Latin numeral. |
| D3 | Look at the rules on that page. | One rule per line of text, none under blank space, text sits **on** the rules and no rule cuts through the glyphs, and the spacing of the last rule equals the spacing of the first (register holds). | Rules through the text or drifting: adjust `RULE_Y_OFFSET_PX` only. Drift specifically means the line pitch is not what V22 claims; stop and re-read the source. |
| D4 | Look at the rules against the text. | Grey, clearly lighter than the glyphs. | Black rules ⇒ the colour fallback chain fell through; V28 is wrong. |
| D5 | Open "read Al-Baqara (2)". Tap right five times. | Five distinct pages, each turn feels instant (well under half a second), no text repeated or skipped at any seam. **Also judge:** does right-for-forward feel right in Arabic? If not, flip `FORWARD_ON_RIGHT`. | Repeated/skipped lines at a seam ⇒ V25 (`top_line_num` off-by-one). |
| D6 | Tap left five times. | You land on exactly the five pages you just saw, in reverse order, ending on the page you started from. | The paging inverse is broken; compare against `tools/paging_model.py`. |
| D7 | Tap the top centre. Raise Arabic size twice, close the dialog. | The dialog opens, the readout names the current surah/ayah, the page re-renders larger, and the rules are still in register at the new line height. | Dialog absent ⇒ V29. Rules out of register after a size change ⇒ the line pitch was cached and not recomputed. |
| D8 | Note the ayah number at the top of the page. Close the reader. Exit KOReader completely and restart it. Open "read (last position)". | The identical page appears, same ayah at the top. | Position lost ⇒ V30/V31; check the settings file exists at `DataStorage:getSettingsDir()`. |
| D9 | Open surah 114, page to its end, close. Open surah 2 — check position — close. Open 114 again. | Each surah returns to its own saved position, independently. | Positions are sharing a key. |
| D10 | In surah 114, tap right on the last page. | Nothing moves; a brief "End of surah 114" toast. | Cross-surah paging leaked in, or the last page is unreachable. |
| D11 | Open surah 2, look at ayah 1. Then open surah 9, look at ayah 1. | Surah 2 shows the basmala **exactly once**, as the opening of ayah 1. Surah 9 shows **no** basmala. Surah 1 (check it too) shows the basmala as its numbered ayah 1. | A second basmala anywhere means a heading was rendered — it must not be. |
| D12 | Page forward eight times in a row and look at the screen. | A full refresh clears any ghosting at least once in those eight; no accumulated smearing. | The `turns_since_full` counter is not firing. |
| D13 | **The 2:282 overflow case.** Eject, then on a computer open `<KindleDrive>/koreader/settings/quran.lua` and set the Al-Baqara entry to `["2"] = { ayah = 281, line = 0 }` (create `positions = {}` if absent). Re-insert, open "read Al-Baqara (2)", then page forward until the marker reads `۝٢٨٢`. | 2:282 is the longest ayah in the Qur'an and **must** span several pages. Every one of those pages is full except the last, no line is repeated or lost at any seam, the rules stay in register throughout, and paging back through it returns you to exactly where you started. | Text lost or repeated across the split ⇒ the multi-page overflow path is wrong (V25/V26). A single clipped page ⇒ overflow is not implemented at all. Settings file rejected ⇒ position validation is too strict (V32). |

**Telling a paging bug from a rendering bug from a position-memory bug** —
these look similar on screen, so:

- **Paging bug**: the wrong *ayah/line* ends up at the top of a page (a
  seam repeats or skips a line, D5/D6). Diagnose against
  `tools/paging_model.py`, which mirrors the same arithmetic on real ayah
  lengths — if the model's forward/back walk over the same surah also
  disagrees, it is the arithmetic; if the model agrees but the device
  doesn't, it is `TextBoxWidget` metrics (V22–V25).
- **Rendering bug**: the *right* ayah/line is at the top, but something
  about how it is drawn is wrong (rules drift or wrong colour, D3/D4;
  clipped/overflowing text within one ayah's own slice). These never
  change *which* ayah is showing, only how it looks.
- **Position-memory bug**: the reader opens to the wrong page after a
  close/reopen (D8/D9), even though paging *within* a session was correct.
  Diagnose by checking whether the settings file
  (`DataStorage:getSettingsDir() .. "/quran.lua"`) exists and its
  `positions` table has the surah's key — if the file is missing or empty,
  it's V30/V31 (persistence); if the file has a value but the wrong one,
  it's a `Settings.setPosition`/`getPosition` bug, not a paging bug.

Record with the result: which of D3's/D5's tunable constants (if any) were
changed and to what value, and which MUST-VERIFY items (V20–V36) were
confirmed or refuted by this pass.

## What you should see

A full-screen view showing, in order: a short Latin title line
("Qur'an 2:255"), a blank line, then the Arabic text of Ayat al-Kursi,
right-to-left, wrapped over multiple lines, set in Scheherazade New at 34px.

**Milestone 0 has already passed on a Paperwhite 11** — direction, joining,
the lam-alef ligature, stacked harakat and the Uthmani marks all rendered
correctly with zero tofu. The checklist below is kept so the result can be
reproduced on other devices, and so a regression is easy to spot. If the text is taller than the
screen, it scrolls — scroll to the end before judging line-spacing (check 7
below).

**Dismissing depends on whether the text overflows.** If it fits, a tap
anywhere closes it. If it scrolls, KOReader's ScrollTextWidget claims taps
inside the text as scroll gestures — left half pages up, right half pages
down. To dismiss in that case, tap **outside** the text block (the dimmed
margin), or press Back. Do not mark check 8 FAILED because a tap scrolled
instead of closing: that is correct behaviour, not a defect.

Note: the primary widget used is `ui/widget/infomessage.InfoMessage`, not
`ui/widget/textviewer.TextViewer` as an earlier draft of this milestone's
implementation plan assumed. On inspection of the actual KOReader source,
`TextViewer` does not expose a way to set a custom font face or have it
honour a custom font size (its internal font choice and size are hardcoded /
overwritten from unrelated presets), so it could not host `ARABIC_FONT` /
`ARABIC_FONT_SIZE` as the spec required. `InfoMessage` does support a
`face` key directly and was used instead — this is the "documented fallback"
the spec's implementation plan anticipated for exactly this situation. It is
dismissed by tapping anywhere on the screen (no separate "Close" button),
which still satisfies the touch-only requirement.

## The five-minute verdict

Compare what is on screen against a known-good rendering of 2:255 (any
phone Qur'an app, or the Tanzil website: https://tanzil.net) held next to
the Kindle.

| # | Check | Pass looks like |
|---|---|---|
| 1 | Reading direction | The **first** word of the verse is at the **right** edge of the first line; the verse ends at the left of the last line |
| 2 | Joining | Words are single connected strokes. `ٱلسَّمَٰوَٰتِ` is one continuous run, not eight separate standing letters |
| 3 | Lam-alef ligature | `إِلَّا` ends in **one** V-shaped lam-alef glyph — not a lam followed by a separate vertical alef |
| 4 | Stacked harakat | `ٱللَّهُ` shows the shadda **and** the vowel above the lam, both distinct and legible at arm's length |
| 5 | Uthmani specials | The superscript alef in `إِلَٰهَ`, the alef wasla head on `ٱ`, and the small waw in `تَأْخُذُهُۥ` are all drawn |
| 6 | No tofu | Zero dotted/empty boxes anywhere in the text |
| 7 | Vertical spacing | No mark from one line touches or overlaps the line above |
| 8 | Touch | Tapping the screen dismisses the view and returns to the File Manager with no stuck ghost image |

### Verdicts — this is the gate

- **PASS** — checks 1–4 all pass. The architecture is proven. Proceed to
  Milestone 1.
- **FAIL MODE A — architecture failure.** Check 1 or 2 fails: letters
  isolated, unjoined, or in left-to-right order. This is the outcome that
  the wider spec's §12 calls fatal.

  **Rule out one false positive before declaring this.** Open
  `quran.koplugin/main.lua` and confirm the InfoMessage is constructed with
  `auto_para_direction = true`. KOReader's TextBoxWidget defaults that flag
  to `false`, and without it the ayah renders left-to-right *even when
  shaping is working perfectly* — which looks exactly like check 1 failing.
  Only if the flag is present and set is this a real architecture failure.

  If it is real: **stop, build nothing else.** The KOReader/HarfBuzz
  assumption is wrong for this build and the architecture must change.
- **FAIL MODE B — font coverage, not architecture.** Checks 1–4 pass but 5
  or 6 fails (tofu or missing Uthmani marks). The architecture is **fine**.
  Fix by font: copy `Amiri-Regular.ttf` (OFL-licensed; not included in this
  repo) into `/mnt/us/koreader/fonts/` and set `ARABIC_FONT` in
  `quran.koplugin/main.lua` to that **filename**. Amiri Quran (OFL 1.1) is
  the other good Naskh candidate. Note that KFGQPC Uthmanic HAFS — the
  official Madani mushaf face, and the most authentic-looking — is
  **proprietary** and may not be redistributed, so it cannot be bundled
  even though you may install it on your own device.
- **FAIL MODE C — typography, not architecture.** Checks 1–6 pass, 7 fails
  (marks colliding). Architecture is **fine**; this is a tuning task.

  **Settled.** On a Paperwhite 11 with Scheherazade New, 34px was chosen by
  eye after comparing 26/30/34/38/44 — at that size the harakat clear the
  line above. That is the current `ARABIC_FONT_SIZE`. The comparison submenu
  used to reach it has been removed.

### Record with the verdict

- KOReader version string (Menu → Help → About)
- Kindle firmware version
- Whether `InfoMessage` behaved as described above, or you had to fall back
  further
- Whether a font was swapped (fail mode B) and which one
- A photo or screenshot of the screen (kept outside this repository — do not
  check it in; put it in the milestone report). Without the photo the gate
  result is not reviewable later.

## Notes on what you'll see and why

- **Failure mode A vs. B, in one sentence**: mode A is a crash-adjacent
  layout bug (letters standing alone, wrong order) and means the whole
  approach is wrong; mode B is a missing-glyph problem (tofu boxes, or a
  mark simply absent) and just means the font on the device doesn't cover
  every Uthmani codepoint — both look "wrong" on screen, but only mode A is
  fatal.
- **Font size**: `ARABIC_FONT_SIZE` in `main.lua` is a point-like value
  passed to KOReader's `Font:getFace`, not a raw pixel count — it is scaled
  internally by screen DPI. If text looks absurdly small or huge, that is a
  units mismatch, not a shaping failure; adjust `ARABIC_FONT_SIZE` and
  retest.
- **KUAL entry launches KOReader, not the plugin directly.** Deep-linking
  KUAL straight into a specific KOReader plugin would require inventing
  launch API this milestone has no need for and no way to verify. The KUAL
  item is not on the critical path for the gate — you can also just launch
  KOReader any other way and open the plugin from its menu.
- **`quran.sh` launcher path**: the real KOReader-on-Kindle launcher, per
  KOReader's own published KUAL entry, lives at `/mnt/us/koreader/koreader.sh`.
  `extensions/quran/bin/quran.sh` tries that path first, falls back to
  `/mnt/us/extensions/koreader/bin/koreader.sh` (an alternate layout some
  installs use), and if neither exists it prints an error to stderr and
  exits non-zero rather than failing silently.

## What is deliberately absent from Milestone 0

No SQLite, no build pipeline, no second verse, no navigation, no
translation text, no bookmarks, no settings UI, and no font files. See
`.pipeline/spec.md`'s "Out of scope" section for the full list. This is
kept small on purpose — the gate is only useful if it stays cheap.

## What is deliberately absent from Milestone 1

No English translation (the `translation` table is created empty, on
purpose — see `data/SOURCE.md`), no navigation UI, no surah list, no juz
picker, no reference parser (typing `2:255` to jump), no `order_rev`
(revelation-order) data, no display modes or Bismillah/sajdah rendering, no
settings UI, no search/FTS5/inverted index. The surah names, juz and sajdah
*data* are in the pack because the schema requires them; nothing in the UI
touches them yet. Full list: `.pipeline/spec.md`'s M1 "Out of scope"
section.
