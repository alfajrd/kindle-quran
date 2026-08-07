# Backlog

Things worth building that are **not** in v1. `docs/SPEC-v1.md` §13 keeps the
one-line list; this file holds the items that have enough shape to need
thinking about before they are picked up.

Nothing here is scheduled. An item earns a milestone when its blockers clear.

---

## B1 — Startup mode: Arabic only, or Arabic with translation

**Status:** blocked on translation licensing
**Size:** large — changes pagination, not just presentation

### What

On opening the app, the reader chooses between two modes:

1. **Arabic only** — continuous reading, the v1 behaviour.
2. **With translation** — **one ayah and its translation per page.**

The choice persists, and is changeable later from settings rather than being
asked on every launch.

### Why it is bigger than it looks

Option 2 is not a display toggle over the v1 reader. It is a **different
pagination model**:

| | Arabic only | With translation |
|---|---|---|
| Unit of a page | whatever fits the screen | exactly one ayah |
| Page breaks | wherever the text wraps | at ayah boundaries, always |
| Position memory | offset within a surah | an ayah reference |

The v1 reader flows text and breaks pages where the screen runs out. Mode 2
breaks pages where the *content* says to. Both models have to coexist, and the
saved reading position has to survive a mode switch — a reader who stops at
2:255 in one mode should resume at 2:255 in the other, not at a byte offset
that means nothing there.

### Design notes

- **Ayah length varies enormously.** 2:282 is by far the longest ayah; many in
  the short surahs are a few words. One-ayah-per-page therefore produces very
  uneven pages: mostly near-empty, occasionally overflowing a screen. Decide
  deliberately what happens when a single ayah does not fit — scroll within the
  page, or allow that one ayah to spill across pages while still not sharing a
  page with its neighbour. Do not discover this at 2:282.
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

### Blocker

**No English translation has cleared licensing yet.** This is the gate, and it
is not a formality — see `docs/SPEC-v1.md` §3 and `THIRD-PARTY.md`. Sahih
International's terms are unclear; a translation cannot be bundled until its
licence is established in writing. Mode 2 cannot ship without one.

The mode *selector* could be built ahead of that, but it would offer a choice
with nothing behind it, so there is no point until the text exists.
