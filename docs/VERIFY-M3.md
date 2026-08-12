# Verifying Milestone 3 on the device

The interleaved side-by-side layout (SPEC-v1 §9.1). Nothing in M3 has run: this
machine has no Lua interpreter, so `tools/check_m3.py` proves the wiring is
connected and proves nothing about what it draws.

Read §"If it fails" before starting. Knowing which file to blame beats
re-copying everything.

---

## 1. What to copy

Five plugin files, one of them new:

```
quran.koplugin/main.lua
quran.koplugin/db.lua
quran.koplugin/quranreader.lua
quran.koplugin/quransettings.lua
quran.koplugin/quranrows.lua        <-- NEW
```

to `<KindleDrive>\koreader\plugins\quran.koplugin\`.

**`quranrows.lua` is new.** Forgetting it is the most likely mistake and it
fails softly: the reader opens, the mode toggle says "quranrows.lua failed to
load", and you read Arabic-only wondering why nothing changed.

## 2. The translation pack

Build it if you have not:

```
python tools/build_translation.py --src <the verse-by-verse archive>.zip
```

That writes `translations/itani.db`. Copy it to **either** location — the
plugin checks both, in this order:

| Destination | Survives a plugin upgrade? |
|---|---|
| `<KindleDrive>\koreader\plugins\quran.koplugin\data\translation.db` | No — the directory is replaced |
| `<KindleDrive>\koreader\settings\quran-translation.db` | **Yes** |

Prefer the second. The first is for a quick test.

Rename it to match: the plugin looks for those exact filenames, not `itani.db`.

**Do not commit the pack.** `check_m0.py` S4 asserts git tracks none, and it
fails the build if one is.

## 3. Settings

The mode defaults to **Arabic only**, so after copying you will see no change
until you switch. Tap the top centre → **Mode: Arabic only** → it flips to
"with translation".

If your saved `quran.lua` is old it simply lacks the new keys, and each falls
back to its default — no reset needed. Delete
`<KindleDrive>\koreader\settings\quran.lua` only if you want to start clean.

---

## 4. Checklist

Work down. Stop at the first failure and record what you saw — a photograph of
a wrong page is worth more than a description.

### The layout

- [ ] **D1** Mode toggle switches to "with translation" without an error message.
- [ ] **D2** Each row shows **English on the left, Arabic on the right**.
- [ ] **D3** English reads left-to-right. Arabic reads right-to-left and is
      **right-aligned in its column**. *(Verifies V40 — if either column is
      aligned the wrong way, `para_direction_rtl` is being ignored.)*
- [ ] **D4** The two columns **do not overlap or clip each other**. Each
      TextBoxWidget blits opaquely, so an overlap erases text rather than
      layering it. *(V42)*
- [ ] **D5** A **rule runs below each ayah**, and **cuts no glyph anywhere** —
      not a descender, not a low kasra. This is the whole point of the row
      model; unlike the per-line rules there is nothing to tune, so any
      clipping here is a real bug, not a setting.
- [ ] **D6** Row heights differ — a short ayah's row is short. Nothing is
      padded to a fixed height.

### The basmala

- [ ] **D7** Open **surah 112**. The basmala appears **once**, as a heading
      spanning both columns above ayah 1 — **not** inside the Arabic of ayah 1,
      and not on the Arabic side only.
- [ ] **D8** Open **surah 1 (Al-Fātiḥah)**. The basmala is **ayah 1, numbered**,
      with its translation beside it. No separate heading.
- [ ] **D9** Open **surah 9 (At-Tawbah)**. **No basmala at all**, either side.

*D7–D9 are the three cases `tools/check_alignment.py` proved the data supports.
If D7 shows the basmala twice, the prefix strip did not fire; if it shows on
the Arabic side only, the translation's ayah 0 was not found.*

### Pagination

- [ ] **D10** Page forward through a whole short surah (114) and back again.
      The same rows appear in the same order both directions.
- [ ] **D11** **No ayah is ever cut across a page break** — a row that does not
      fit starts the next page whole.
- [ ] **D12** **Go to 2:282.** It is the longest ayah in the Qur'an and cannot
      fit one page at any supported size. It must **split across pages** and be
      fully readable — both columns advancing, nothing lost at the seam.
      *(This is the case the overflow path exists for. Test it at the LARGEST
      Arabic size too, where it is worst.)*
- [ ] **D13** Paging backward out of a split ayah returns to its earlier
      sub-page, not to the previous ayah.

### Typography

- [ ] **D14** "English +/-" appears in the dialog **only** in interleaved mode.
- [ ] **D15** Changing English size re-lays the page and does not disturb the
      Arabic size.
- [ ] **D16** **Judge the Arabic at 34 px in a ~562 px column.** It was chosen
      at full width and may now be too large. If it is, note the size that
      works — that number is the deliverable from this checklist.

### Mode switching and memory

- [ ] **D17** Read to a known ayah in interleaved mode, switch to Arabic-only:
      you land on **the same ayah**. (Not necessarily the same screenful —
      §9.1 promises the ayah, not the offset.)
- [ ] **D18** Switch back. Still the same ayah.
- [ ] **D19** Close the reader, reopen it: the mode **and** the position
      persist.
- [ ] **D20** **Remove the translation pack** and open the reader. It opens in
      Arabic-only, the toggle explains "no translation pack is installed", and
      **nothing crashes**. Losing the translation must never cost you the
      Qur'an.

---

## 5. If it fails

| Symptom | Almost certainly |
|---|---|
| Nothing under "More tools" | The plugin failed to load — `crash.log` names the file and line |
| Mode toggle says "quranrows.lua failed to load" | `quranrows.lua` was not copied |
| Mode toggle says "no translation pack is installed" | Pack absent, or misnamed — see §2 |
| Mode toggle says "pack has no trans_id" | Built by an older builder; rebuild it |
| Columns overlap | `Rows.COLUMN_GUTTER_PX` (V42) |
| Arabic laid out left-to-right | `para_direction_rtl` ignored (V40); fall back to `auto_para_direction = true` |
| Basmala shown twice in surah 112 | `Rows.stripBasmala` — run `tools/check_alignment.py` first |
| Reader hangs on a long ayah | The overflow path in `Rows.buildPage`; 2:282 |

`crash.log` lives at `/mnt/us/koreader/crash.log`. Every failure path in M3 is
either an `InfoMessage` naming the cause or a line in that file — none of them
is silent, which is a deliberate change from M0, where a load failure was.
