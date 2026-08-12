# Verifying Milestone 4 on the device

The navigator: surah list, juz list, reference jump. Nothing here has run —
same as M3, there is no Lua interpreter on the build machine.

What *has* been checked without a device:

- `tools/check_m3.py` X14–X20 — the M4 wiring, mutation-tested against five
  planted defects.
- The reference **grammar**, traced against 24 documented cases. That found and
  fixed one real bug (`"2 255"` parsed as surah 2255). It proves the grammar,
  **not** the Lua that implements it.

---

## 1. What to copy

```
quran.koplugin/main.lua
quran.koplugin/db.lua
quran.koplugin/quranreader.lua
quran.koplugin/qurannavigator.lua      <-- NEW
```

`quranrows.lua` and `quransettings.lua` are unchanged since M3.

## 2. The menu changed

The four hard-coded surah entries are **gone**. In their place:

| Entry | Does |
|---|---|
| Qur'an — read (last position) | unchanged |
| **Qur'an — surahs** | all 114, then opens the reader there |
| **Qur'an — juz** | all 30, showing where each begins |
| **Qur'an — go to reference** | type `2:255` |

The same three exist **inside** the reader — top-centre tap, the row under the
position readout — so a jump from an open reader stays in it rather than
closing and reopening.

---

## 3. Checklist

### The lists

- [ ] **N1** "Qur'an — surahs" shows **114** entries, 1 to 114, in order.
- [ ] **N2** Each reads like `2. Al-Baqara - The Cow  (286 ayat, Medinan)`.
      Check a few against what you know: **9** is At-Tawba/The Repentance,
      Medinan, 129 ayat; **114** is An-Naas/Mankind, Meccan, 6 ayat.
      *(`name_tr` is the transliteration and `name_en` the meaning — they are
      easy to swap, and a swap is obvious here and nowhere else.)*
- [ ] **N3** Picking a surah opens the reader **at ayah 1 of it**.
- [ ] **N4** "Qur'an — juz" shows **30** entries. Juz 1 begins at **1:1**;
      juz 2 at **2:142**; juz 30 at **78:1**.
- [ ] **N5** Picking a juz lands on **exactly** that ayah, not the start of
      its surah.

### Reference jump

- [ ] **N6** `2:255` lands on Ayat al-Kursi.
- [ ] **N7** These all work: `2 255`, `2.255`, `2-255`, and `  2 : 255  `.
- [ ] **N8** `2` alone opens surah 2 at ayah 1.
- [ ] **N9** `2:300` is **refused**, and the message says surah 2 has 286 ayat.
- [ ] **N10** `115:1` is refused (surah out of range).
- [ ] **N11** `2:255x` is **refused** — not silently accepted as 2:255. *(This
      is what anchoring the patterns buys; unanchored it would jump.)*
- [ ] **N12** Empty input and `abc` are refused without crashing.

### From inside the reader

- [ ] **N13** Top-centre tap → the row under the readout has **Surahs / Juz /
      Go to...**.
- [ ] **N14** The readout now reads `Surah 2:255  -  juz 3`. Check the juz
      against N4's boundaries.
- [ ] **N15** Jumping from inside the reader **stays in the reader** — no
      close-and-reopen flicker.
- [ ] **N16** "Go to..." opens **pre-filled with where you are**.

### The one that has teeth

- [ ] **N17** From surah 2 (286 ayat), jump to **surah 114** (6 ayat). Page
      forward past the end. It must stop at "End of surah 114" — **not** page
      into emptiness. *(If it does, `Reader:goTo` failed to re-read
      `ayah_count` and is using surah 2's length.)*
- [ ] **N18** Jump surah → surah → surah several times, then reopen the reader.
      Position memory holds for **each** surah separately, not just the last.
- [ ] **N19** Dismiss a surah list **without picking** (back button). Nothing
      leaks, nothing hangs, and the menu can be reopened.
- [ ] **N20** Jump while in **interleaved** mode: the layout stays interleaved
      and the basmala heading rules from M3 still apply in the new surah.

### Still outstanding from M3

- [ ] **D12** **2:282** — the overflow path, still untested. Now reachable in
      one step: "go to reference" → `2:282`.
- [ ] **D19** Does `koreader/settings/quran.lua` exist after a clean close?
      Before M3 was copied it did **not**, anywhere on the device, which would
      mean position and mode are not persisting at all.
- [ ] **D16** Is 34 px Arabic right in a ~562 px column?

---

## 4. If it fails

| Symptom | Almost certainly |
|---|---|
| Menu entries missing | `qurannavigator.lua` not copied; `crash.log` names the line |
| "qurannavigator.lua failed to load" | it copied but does not parse |
| Lists open empty | `DB.listSurahs` / `DB.listJuz` — check the pack self-test |
| Tapping a list item does nothing | V50: this version's `Menu` ignores our `onMenuSelect`; the per-item `callback` is the fallback path |
| No keyboard in "Go to..." | V52 — harmless, the field still accepts input |
| Juz boundaries wrong | `DB.listJuz`; compare against N4 |
| Pages past the end of a short surah | `Reader:goTo` did not re-read `ayah_count` (N17) |
