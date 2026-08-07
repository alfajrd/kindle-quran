# Translation packs

This directory is where side-loaded translation packs go. **It ships empty.**

## Why empty

No widely-used English translation of the Qur'an has an unambiguous open
licence — see `docs/BACKLOG.md` §B1 for the survey. The Arabic is settled
(Tanzil, CC BY 3.0, verbatim with attribution); translations are not.

So the app supports translation packs but bundles none. You supply your own.

## Personal use vs redistribution

These are different things, and the distinction is the whole reason this
directory exists:

- **Putting a translation you own on your own device** is format-shifting a
  book you bought. Fine.
- **Committing it here, or shipping it in a KindleForge release**, is
  redistribution. Not fine for anything under copyright — and this repo is
  public, with permanent history, so "I'll delete it later" does not undo it.

`.gitignore` blocks the obvious paths so a personal pack cannot be committed
by accident. Do not override it without checking the licence and recording it
in `THIRD-PARTY.md`.
