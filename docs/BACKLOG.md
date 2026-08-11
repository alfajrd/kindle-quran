# Backlog

Things worth building that are **not** in v1. `docs/SPEC-v1.md` §13 keeps the
one-line list; this file holds the items that have enough shape to need
thinking about before they are picked up.

Nothing here is scheduled. An item earns a milestone when its blockers clear.

---

## B1 — Startup mode: Arabic only, or Arabic with translation

> **PROMOTED TO v1 — Milestone 3, on 11 August 2026.**
>
> The blocker below was translation *licensing*. The personal-use decision
> (`docs/SPEC-v1.md` §1) resolved it for the owner's device: a translation they
> hold a copy of may be side-loaded, while the repository still ships none.
> That is Option 3 below, which was already the recommendation.
>
> The layout was settled at the same time — **side-by-side ayah rows**, from a
> reference screenshot. Spec: §9.1. It replaces "one ayah per page", which the
> pagination rule below had already superseded.
>
> **This section is not obsolete.** The licensing survey becomes live again the
> instant a public KindleForge release is considered, and nothing in it has
> changed. Keep it. The design notes below remain the working notes for M3 —
> in particular the surah-intro schema, which is not yet built.

**Status:** ~~blocked on translation licensing~~ → **in v1 as Milestone 3**
**Size:** large — changes pagination, not just presentation

### What

On opening the app, the reader chooses between two modes:

1. **Arabic only** — continuous reading, the v1 behaviour.
2. **With translation** — pages break on ayah boundaries.

The choice persists, and is changeable later from settings rather than being
asked on every launch.

### Why it is bigger than it looks

Option 2 is not a display toggle over the v1 reader. It is a **different
pagination model**:

| | Arabic only | With translation |
|---|---|---|
| Unit of a page | whatever fits the screen | whole ayat, greedily packed |
| Page breaks | wherever the text wraps | at ayah boundaries where possible |
| Position memory | offset within a surah | an ayah reference |

### Pagination rule (decided)

Fill each page with **as many complete ayah + translation pairs as fit**. Never
cut an ayah mid-way to squeeze it in — if the next pair does not fit whole, it
starts the next page.

The exception is an ayah that cannot fit a page on its own: split it across as
many pages as it needs. 2:282 is the case that forces this, and a handful of
others will too — the split must be measured against the rendered height at the
reader's current font size, not guessed from character count, because Arabic
wraps by shaped width.

This is strictly better than one-ayah-per-page: short surahs read normally
instead of wasting a screen per line, and the reader still never meets an ayah
chopped for want of a few pixels.

The v1 reader flows text and breaks pages where the screen runs out. Mode 2
breaks pages where the *content* says to. Both models have to coexist, and the
saved reading position has to survive a mode switch — a reader who stops at
2:255 in one mode should resume at 2:255 in the other, not at a byte offset
that means nothing there.

### Design notes

- **Ayah length varies enormously**, which is what the pagination rule above
  exists to absorb. The overflow path is not hypothetical: verify it against
  2:282 specifically, at the largest supported font size, where it is worst.
- **Two scripts, two typographic settings.** §9 already separates Arabic and
  English size and leading. Mode 2 is where that separation actually earns its
  keep, since both appear together.
- **Direction changes mid-page.** The Arabic block is RTL, the translation LTR.
  Each block needs its own paragraph direction — `auto_para_direction` handles
  detection, but the two must not be assumed to share alignment.
- **Ayah numbering.** With one ayah to a page, the reference should be visible
  on the page rather than inferred from a marker in a flow.
- A rule between the Arabic and the translation would help separate them —
  related to the ruled-lines work in §9, and probably the same widget.
- **Surah introductions.** Some translations (The Clear Quran among them) open
  each surah with a short introduction — when it was revealed, its themes, how
  it connects to the one before. Worth supporting: it is the part of a
  translation that a plain verse-by-verse rendering loses entirely.

  It belongs to the **translation pack**, not the Arabic pack — the intros are
  the translator's own writing, with their own copyright, and a reader who
  swaps translations should get that translation's intros. So the pack schema
  needs a place for it:

  ```sql
  CREATE TABLE trans_surah_intro (
    trans_id  TEXT NOT NULL,
    surah     INTEGER NOT NULL,
    text      TEXT NOT NULL,
    PRIMARY KEY (trans_id, surah)
  );
  ```

  Display: shown once when entering a surah, ahead of ayah 1, and skippable —
  a reader returning to a surah for the tenth time does not want to page past
  it every time. Position memory should treat it as before-ayah-1 rather than
  as its own page, so resuming never lands on an intro the reader has read.

  Note this makes the pack format richer than "verses in another language",
  which is an argument for defining the side-loaded pack format properly
  rather than treating it as a translation dump.

### Blocker — translation licensing

**No English translation has cleared licensing.** Researched, and the result is
worse than expected: there is no widely-used English translation with an
unambiguous open licence.

| Translation | Status | Usable? |
|---|---|---|
| **Sahih International** | Dar Abul Qasim; no public licence grant found | ❌ |
| **The Clear Quran** (Khattab) | © Al-Furqaan Foundation, all rights reserved | ❌ |
| **Yusuf Ali** | PD in Pakistan since 2002 (life+50), but a pro-forma **US copyright runs to 2033**, and the Islamic Computing Centre asserts rights | ⚠️ jurisdictional |
| **Pickthall** | d. 1936 → PD in life+50 and life+70 countries (UK/EU since 2006, Indonesia life+70). **Not clearly PD in the US** — published in India after 1922. ICC also asserts rights | ⚠️ jurisdictional |
| **quranenc.com** (King Fahd Complex) | Portal states its translations are free to distribute; terms not confirmed in writing | ❓ ask |

Note the asymmetry: **the Arabic is settled** — Tanzil is CC BY 3.0, verbatim
only, attribution plus a link to tanzil.net, which we already comply with. It
is only the translations that are unresolved.

### Three ways forward

1. **Ask.** Write to quranenc.com / the King Fahd Complex for explicit written
   permission. Slowest, and the only route that ends in a clean answer.
2. **Pickthall, documented.** Public domain where the publisher sits
   (Indonesia, life+70) and across the UK/EU. The US position is unclear and
   the repository is US-hosted. Viable with the reasoning written down; not
   risk-free.
3. **Ship none; support side-loading.** The app reads translation packs but
   bundles no translation. The reader supplies their own file. This sidesteps
   redistribution completely, and unblocks the *engine* work immediately —
   pagination, mode switching, the two-script typography — leaving only the
   content question open.

**Option 3 is the recommended first move.** It is the only one that lets B1's
hard part get built while the licensing conversation happens in parallel, and
it costs nothing if a licence later clears: a bundled pack is then just a
side-loaded pack that ships in the box.
