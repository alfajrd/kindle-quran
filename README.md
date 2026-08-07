# `quran.koplugin` — Milestone 0: does Arabic render on the device

This is a **go/no-go gate**, not a real Qur'an app. It renders one hard-coded,
byte-exact Tanzil Uthmani ayah (2:255, Ayat al-Kursi) full-screen inside
KOReader on a jailbroken Kindle Paperwhite 11, so a human can decide in five
minutes whether Arabic shaping, joining and harakat work on this device —
and therefore whether the whole KOReader architecture (§2 of the wider
project spec) is viable at all.

If you are looking for the wider project plan, see
`d:\Nekoweb\dev\quran-spec-v1.md`. This README covers Milestone 0 only.

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
4. Copy `extensions/quran/` to `/mnt/us/extensions/quran/`.
4b. Copy `fonts/ScheherazadeNew-Regular.ttf` to `/mnt/us/koreader/fonts/`.
   Without it the plugin falls back to KOReader's default sans — legible,
   but not what you want to look at.
5. Eject the Kindle.
6. Open KUAL → **"Qur'an"**. This starts KOReader (it does not open the
   plugin directly — see "KUAL entry" below).
7. In KOReader's File Manager: top menu → **Tools** (some KOReader versions
   call it **"More tools"** — check both) → **"Qur'an — test ayah (2:255)"**.
8. If the menu item is not there, check KOReader's crash log at
   `/mnt/us/koreader/crash.log`. That is where a Lua error thrown while
   loading the plugin surfaces — KOReader silently skips a plugin that
   throws at load time, so "the menu item isn't there" is the most likely
   first-run symptom, and the crash log is the only way to debug it.

## What you should see

A full-screen view showing, in order: a short Latin title line
("Qur'an 2:255"), a blank line, then the Arabic text of Ayat al-Kursi,
right-to-left, wrapped over multiple lines. If the text is taller than the
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
  (marks colliding). Architecture is **fine**. It confirms Arabic needs
  roughly 1.9 line height at 34px, and is a later-milestone tuning task.
  Note it and move on.

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
