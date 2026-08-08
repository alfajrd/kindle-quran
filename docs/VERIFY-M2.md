# MUST-VERIFY registry — Milestone 2

Every item below is a KOReader API this machine could not confirm: there is
no KOReader checkout and no network access here. Numbering continues from
M0/M1's V1–V16 (see `quran.koplugin/db.lua`'s and `quran.koplugin/main.lua`'s
own header comments for those). This document covers exactly V20–V36, the
ids M2 introduces, in `quran.koplugin/quranreader.lua` (V20–V29, V33–V36) and
`quran.koplugin/quransettings.lua` (V30–V32).

For each id: the claim, the KOReader source file that would confirm or
refute it, what the code does about it (never guesses, never throws at
module load), and the on-device symptom if the claim turns out wrong.
`tools/check_m2.py`'s R6 parses the quick-reference table below and
requires it to list exactly the same ids that appear as `MUST-VERIFY V<n>`
comments (n >= 20) in `quranreader.lua`/`quransettings.lua`/`db.lua` — no undocumented
id, no stale doc entry.

## Quick reference

| id | Claim | Read this file (KOReader source) |
|---|---|---|
| V20 | `TextBoxWidget:new{}` accepts `text`, `face`, `width`, `height`, `line_height`, `alignment`, `auto_para_direction`, `top_line_num`. | `frontend/ui/widget/textboxwidget.lua` |
| V21 | `line_height` is *extra leading in em*, default 0.3 (so 1.9x maps to `line_height = 0.9`). | `frontend/ui/widget/textboxwidget.lua` |
| V22 | `line_height_px` exists on the instance after `init()`. | `frontend/ui/widget/textboxwidget.lua` |
| V23 | `vertical_string_list` exists after `init()` and its length is the total line count of the whole text, not of one page. | `frontend/ui/widget/textboxwidget.lua` |
| V24 | With `height` set to exactly `k * line_height_px`, the widget renders exactly `k` lines and occupies exactly that height (no internal padding). | `frontend/ui/widget/textboxwidget.lua` |
| V25 | `top_line_num` is 1-based. | `frontend/ui/widget/textboxwidget.lua` |
| V26 | `TextBoxWidget:free()` exists and releases the shaped-text resources. | `frontend/ui/widget/textboxwidget.lua` |
| V27 | `VerticalGroup` inserts no spacing between children by default. | `frontend/ui/widget/verticalgroup.lua` |
| V28 | A grey `Blitbuffer` colour constant exists; `bb:paintRect(x, y, w, h, colour)` is the signature. | `ffi/blitbuffer.lua` |
| V29 | `ui/widget/buttondialog` accepts a `buttons` table of rows of `{text=, callback=}`; a button with no `callback` renders inert rather than throwing. | `frontend/ui/widget/buttondialog.lua` |
| V30 | `require("luasettings")`; `LuaSettings:open(path)`, `:readSetting(k)`, `:saveSetting(k, v)`, `:flush()`, `:close()`. | `frontend/luasettings.lua` |
| V31 | `require("datastorage")`; `DataStorage:getSettingsDir()` returns a writable directory. | `frontend/datastorage.lua` |
| V32 | `LuaSettings` round-trips a nested table (`positions`) with string keys. | `frontend/luasettings.lua` |
| V33 | `InputContainer` + `ges_events` with a `GestureRange` over a `Geom` region delivers `onTap(_, ges)` with `ges.pos`. | `frontend/ui/widget/container/inputcontainer.lua`, `frontend/ui/gesturerange.lua` |
| V34 | `UIManager:setDirty(widget, "partial" \| "full")` is a valid call shape. | `frontend/ui/uimanager.lua` |
| V35 | `covers_fullscreen = true` on a shown widget suppresses the underlying view's repaint. | `frontend/ui/uimanager.lua` |
| V36 | `lines_per_page` exists — checked but deliberately not used; M2 computes its own `lines_per_screen`. | `frontend/ui/widget/textboxwidget.lua` |

## Detail — what the code does, and the on-device symptom if wrong

Every one of V20–V35 is accessed through `pcall` or a presence test, and
every failure produces a specific, named InfoMessage. Nothing may throw at
module load — a plugin that throws while loading is skipped by KOReader in
silence, which is the one failure mode that gives the tester nothing to
work with. `main.lua` keeps its existing `pcall(require, ...)` idiom for
`reader`; `quranreader.lua` and `quransettings.lua` do the same for their own
requires (`db`, `settings`, `ffi/blitbuffer`, `logger`,
`ui/widget/buttondialog`, `datastorage`, `luasettings`).

- **V20** — `quranreader.lua` constructs every `TextBoxWidget` inside a `pcall`.
  A wrong key name surfaces as a caught Lua error (treated the same as
  "line metrics unavailable" for measuring probes; a mid-layout failure
  triggers the same DB-error-style close for real page widgets). Symptom
  if wrong: reader refuses to open, or closes itself with an error
  InfoMessage, rather than a blank/garbled screen.
- **V21** — mapped once, at `quransettings.lua`'s `Settings.LIMITS`/`DEFAULTS`
  declaration, with a comment pinning the 1.9x -> 0.9 / 1.7x -> 0.7
  mapping so a future edit doesn't "correct" it back to the raw
  multiplier. Symptom if wrong: line spacing looks roughly double what the
  slider claims; on-device check D7 would show far more or far less
  leading than the number on the dialog implies.
- **V22** — read only inside the fenced `TextMetrics.lineHeightPx`. If
  absent, falls back to a public-API-only probe (`getSize().h` on a
  freshly built one-line box). If *that* also fails: refuse to open the
  reader (edge case 19) with a specific InfoMessage; the reader never
  guesses a pitch. Symptom if wrong and unhandled: rules drift out of
  register over the page (D3), which is why D3's own text tells the
  tester to treat drift as a V22 finding, not a `RULE_Y_OFFSET_PX` tuning
  problem.
- **V23** — read only inside `TextMetrics.lineCount`. Falls back to a
  `getSize()`-based line count (edge case 20) if absent. Symptom if wrong:
  `linesOf()` over- or under-counts an ayah's lines, which would show up
  as a paging seam with a repeated or skipped line (D5/D6).
- **V24** — assumed by STEP P3's `height = slice.n_lines * <pitch>`.
  Symptom if wrong: a slice's rendered text doesn't fill (or overflows)
  its allotted height, which looks like extra blank space or clipped text
  at a slice boundary — distinguishable from a paging bug (D5/D6) because
  it would appear *within* a single ayah's own slice, not at a page seam.
- **V25** — STEP P3 passes `slice.first_line + 1`. Symptom if wrong (i.e.
  actually 0-based): every slice whose `first_line > 0` starts one line
  early, so it repeats the ayah's own last line already shown on the
  previous page — a repeated line exactly at a seam (D5's fail condition).
- **V26** — every `TextBoxWidget` this file builds, including throwaway
  measuring probes, is `:free()`d exactly once, wrapped in `pcall` in case
  `:free()` itself is the thing that's wrong. Symptom if wrong (method
  absent): a caught Lua error from the `pcall`, never a crash; leaked
  native resources across many page turns would show up as the device
  slowing down or eventually crashing over an extended session — not
  something this desktop machine can observe at all.
- **V27** — STEP P4's `VerticalGroup:new(slice_widgets)` is given no
  spacing option. Symptom if wrong (default spacing is non-zero): every
  line after the first sits slightly off the `text_top + i * pitch`
  grid the rules assume, which looks like a **constant** rule/text offset
  that gets worse page after page — different from V22's drift (which is
  present from the very first page) in that it would only appear once
  more than one slice widget is stacked.
- **V28** — resolved once at module load through the guarded
  `RULE_COLOUR_CANDIDATES` chain, ending at `Blitbuffer.gray(0.66)` then
  `COLOR_BLACK`, logged via `logger.warn` (itself `pcall`-guarded) whenever
  the fallback taken is not the first candidate. Symptom if wrong: rules
  render black instead of grey (D4's fail condition) — ugly but visible,
  never invisible.
- **V29** — the dialog is built with `buttons` only, no `title` key (see
  the note above). Buttons at a typography limit are given `callback =
  nil` rather than omitted, relying on this claim that a callback-less
  button renders inert instead of throwing (edge case 15). Both the
  `require` and the `ButtonDialog:new{}` construction (and the
  `UIManager:show`) are wrapped in their own `pcall`s, so a wrong claim
  here fails soft — a specific InfoMessage, the reader keeps reading —
  rather than throwing out of a touch-event handler. Symptom if wrong: the
  settings dialog fails to open (that InfoMessage appears) instead of
  opening with inert min/max buttons as intended; D7 is where this would
  first be seen.
- **V30** — every call into the returned `LuaSettings` instance is
  wrapped (`ls_read`/`ls_save` in `quransettings.lua`, plus `Settings.open`'s
  own `pcall`s). Symptom if wrong: persistence silently degrades to "off"
  for that session (defaults every time), never a crash (D8's fail mode).
- **V31** — `Settings.open` treats a failed `require` or a failed/empty
  `getSettingsDir()` result identically: persistence off, defaults used,
  the reader still opens, with one InfoMessage. Symptom if wrong: same as
  V30 — D8 fails softly, not loudly.
- **V32** — `positions` is read and written as a single nested Lua table
  via one `saveSetting`/`readSetting` call, keyed by surah number **as a
  string**. Every read is validated (type/range-checked) before being
  trusted, so if the round-trip is lossy or reorders keys, the observable
  failure is `Settings.getPosition` silently falling back to its own
  default `(1, 0)` — never a corrupted/garbage position. On-device check
  D9 (two surahs' positions kept independently) is what would surface this.
- **V33** — `quranreader.lua` sets `self.ges_events.Tap` to a single full-screen
  `GestureRange`, then classifies `ges.pos` into MENU/PREV/NEXT itself
  (D2). Symptom if wrong: `onTap` is never called at all, and the reader
  is inert to touch — indistinguishable on screen from a paging bug
  except that *nothing at all* responds, including the menu zone.
- **V34** — every `UIManager:setDirty` call site names an explicit
  `"full"` or `"partial"` string, nothing else. Symptom if wrong: either a
  Lua error (caught nowhere around these specific calls — an on-device
  crash-log-worthy finding) or, more likely if the shape is merely
  suboptimal rather than wrong, a refresh that doesn't visibly clear
  (D12's fail condition).
- **V35** — relied on implicitly by never drawing anything but the
  reader's own white background plus the ruled page in `Reader:paintTo`.
  Symptom if wrong: ghosting/bleed-through from whatever KOReader view was
  open before the reader (the File Manager, most likely) at the screen
  edges outside the text block.
- **V36** — not read anywhere in `quranreader.lua` outside this document (see
  R4's identifier-confinement check, which would fail if it were). Kept
  here only as a documented "checked the claim, chose not to depend on
  it" decision, per §8.3 of `.pipeline/spec.md`.

## What device check catches what MUST-VERIFY finding

See `README.md`'s "Milestone 2 — on-device checklist" (D1–D12) — each
entry there names which of V20–V36 its FAIL column points back to.
