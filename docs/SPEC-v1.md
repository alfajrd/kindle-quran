# Qur'an — v1 Specification

**Target:** Kindle Paperwhite 11th gen (jailbroken)
**Runtime:** KOReader plugin, launched from KUAL
**Content:** Uthmani Arabic + a side-loaded English translation
**Distribution:** personal use — see §1
**Status:** draft for review · 6 August 2026, amended 11 August 2026

---

## 1. Decisions taken

| | |
|---|---|
| Name | **Qur'an** |
| Scope | Qur'an only. Bible deferred to v2. |
| Languages | Arabic (Uthmani) + English translation |
| Device | Kindle Paperwhite 11 — **and only that**, for v1 |
| Runtime | KOReader plugin (`.koplugin`), Lua |
| Distribution | **Personal use.** The repo is public; the build on the owner's device is not a release. |
| Interleaved layout | **Side-by-side ayah rows** — translation left, Arabic right, a rule between ayat |

Narrowing to one device and one scripture removes most of the risk in the
previous draft. What remains is concentrated in one place: §3.

### On "personal use" — decided 11 August 2026

It settles what may go **on the device**, and nothing about what may go **in
this repository**. The two are separate questions, and conflating them is how a
public repo acquires a copyright problem.

- **Device:** a translation the owner holds a copy of may be built into a pack
  and side-loaded. That is format-shifting a book they bought.
- **Repository:** ships **no** translation, now or under this decision.
  `.gitignore` blocks `translations/*.db` and `packs/personal/`; overriding it
  needs a cleared licence and a `THIRD-PARTY.md` entry.

This unblocks §3's translation question **for the engine work only**. If a
KindleForge release is ever wanted, the licensing survey in `docs/BACKLOG.md`
§B1 applies again, unchanged — which is why that survey stays in the tree
rather than being deleted as resolved.

Note the consequence for §4 and §10: the reader now renders two scripts at
once, so every performance target is measured with a translation pack loaded.

---

## 2. Why a KOReader plugin and not a KUAL app

A raw KUAL extension drawing with FBInk or eips **cannot render Quranic
Arabic**. FBInk's TrueType mode uses `stb_truetype`, which has no HarfBuzz and
therefore no complex-script shaping: letters would render isolated and unjoined,
in visual order. Unshippable.

KOReader already carries HarfBuzz + FriBiDi (correct shaping and RTL), a UI
toolkit, e-ink refresh management tuned per device, and SQLite bindings. We
write Lua against a documented plugin API and inherit all of it.

**Accepted dependency:** the app requires KOReader. Normal for this audience,
and KindleForge distributes both.

---

## 3. Text sources and licensing

The English decision solves what was the project's biggest legal risk. Both
candidate translations are **unambiguously public domain**:

| Component | Source | Licence |
|---|---|---|
| Arabic, Uthmani script | [Tanzil.net](https://tanzil.net) | Free to use with attribution; **text must not be modified** |
| English translation | **Pickthall (1930)** | Public domain — Pickthall d. 1936, life+70 expired 2006 |
| English alternative | Yusuf Ali (1934) | Public domain — d. 1953, life+70 expired 2023 |

**Ship Pickthall as the default.** Its public-domain status is the least
arguable of any English translation, and its register suits the Uthmani text.
Yusuf Ali can ship as a second selectable translation at near-zero cost since
the schema already supports multiple.

**Deliberately avoided:** Sahih International. Widely used, but rights are held
by Dar Abul Qasim and its redistribution terms are not clearly stated. Not
worth the exposure for v1.

**Non-negotiable rule:** the Arabic text is never altered. Normalisation happens
only in the desktop build pipeline, only to strip source markup, never to change
characters. Tanzil's terms require this and it is correct regardless.

---

## 4. Device profile — Paperwhite 11

| | |
|---|---|
| Screen | 6.8", 1236 × 1648 px, **300 ppi** |
| Greyscale | 16 levels |
| Input | Touch only — no page-turn buttons |

Two consequences:

**300 ppi removes the diacritic risk.** Full Uthmani harakat is comfortably
legible at this density — it was the main hazard when older 167 ppi devices were
in scope. It is not one now.

**Touch-only input** means every action needs a touch affordance. No key
handling to fall back on. Tap zones must be defined explicitly, not inherited.

---

## 5. Scope

### v1 does

1. **Read** — continuous, by surah, with position memory
2. **Navigate** — by surah (1–114) and by **juz** (1–30)
3. **Jump to reference** — type `2:255`, land there
4. **Display modes** — Arabic only · English only · **both interleaved** (§9.1),
   chosen at startup and changeable later, never re-asked on every launch
5. **Typography** — independent font size for Arabic and English; line spacing; margins
6. **Bookmarks** — a saved reference with an optional note
7. **About** — translation, source, licence, attribution

### v1 does not

Search · tafsir · audio (PW11 has no speaker) · highlights · notes on verses ·
word-by-word · transliteration · Indonesian · Bible · sync · **mushaf page
fidelity**.

### On mushaf fidelity

Reproducing the Madani mushaf — 15 lines per page, page-specific QCF fonts — is
a separate project with its own font pipeline. v1 renders **flowing text by
ayah**. State this in the README so nobody arrives expecting a mushaf and leaves
disappointed.

---

## 6. Qur'an-specific rules

These are the details that separate a scripture reader from a text viewer.
Getting them wrong is immediately visible to anyone who knows the text.

- **Bismillah.** Every surah opens with it *except* At-Tawbah (9). In
  Al-Fātiḥah (1) it is **ayah 1**, not a heading. Everywhere else it is a
  heading and must not be numbered. Hard-code this; do not infer it.

  **The data does not arrive in that shape.** Established 12 August 2026: the
  Tanzil corpus stores the basmala as a **prefix inside ayah 1** for all 113
  surahs that have one, while the translation pack stores it as a **separate
  ayah 0**. So the reader must split the prefix off for surahs 2–114 (except 9)
  and render it as the heading this rule requires.

  That split is a **deletion at a verified offset**, never a search-and-replace:
  the prefix is asserted byte-identical to Al-Fātiḥah's ayah 1, which is read
  from the pack rather than written down anywhere. `tools/check_alignment.py`
  proves the precondition holds across all 114 surahs before any of it runs —
  same discipline `docs/ERRATA.md` imposes, and for the same reason.
- **Ayah markers.** Use U+06DD with the Arabic-Indic ayah number — never a
  Latin numeral inside Arabic text.
- **Sajdah.** 15 verses carry a prostration mark. Flag them in the data and
  render the mark; do not synthesise one.

  **Already satisfied by verbatim rendering**, established 12 August 2026:
  U+06E9 is present in the Tanzil text at exactly those 15 verses, so the mark
  appears because the reader does not interfere with the text. The `sajdah`
  column is therefore *not* what draws it — it exists for what the inline mark
  cannot do, which is say so at a glance: the mark sits at the END of an ayah,
  and on a long one that may be several sub-pages from where the reader is
  looking. The position readout names it.
- **Waqf marks** are part of the Uthmani text. Render as-is.
- **Surah metadata** — Meccan/Medinan, ayah count, revelation order — shown on
  the surah header and in the navigator.
- **Juz boundaries** are static data. Precompute them; do not derive at runtime.

---

## 7. Data

One SQLite file. Chosen over JSON because jump-to-ayah and later search need
indexed access, and KOReader already links SQLite.

```sql
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
-- pack_id, name, licence, source_url, attribution, build_date, checksum

CREATE TABLE surah (
  id           INTEGER PRIMARY KEY,   -- 1..114
  name_ar      TEXT NOT NULL,
  name_en      TEXT NOT NULL,         -- "The Cow"
  name_tr      TEXT NOT NULL,         -- "Al-Baqarah"
  ayah_count   INTEGER NOT NULL,
  revelation   TEXT NOT NULL,         -- 'meccan' | 'medinan'
  order_rev    INTEGER NOT NULL,
  has_bismillah INTEGER NOT NULL      -- 0 for surah 9 only
);

CREATE TABLE ayah (
  surah   INTEGER NOT NULL REFERENCES surah(id),
  ayah    INTEGER NOT NULL,
  text    TEXT NOT NULL,              -- Uthmani, unmodified
  sajdah  INTEGER NOT NULL DEFAULT 0,
  juz     INTEGER NOT NULL,
  PRIMARY KEY (surah, ayah)
);

-- Separate table, not a column: adding Yusuf Ali must not need a migration.
CREATE TABLE translation (
  trans_id TEXT NOT NULL,             -- 'pickthall'
  surah    INTEGER NOT NULL,
  ayah     INTEGER NOT NULL,
  text     TEXT NOT NULL,
  PRIMARY KEY (trans_id, surah, ayah)
);
```

### Build pipeline (desktop only, never on device)

```
Tanzil XML → normalise → validate → build .db → checksum → package
```

**Validation must assert and fail loudly:**

- exactly **114** surahs
- exactly **6236** ayat
- per-surah ayah counts match the canonical table
- exactly **15** sajdah markers
- **30** juz, contiguous, covering every ayah
- translation row count equals Arabic row count
- no ayah text is empty

A silently truncated scripture is the worst bug this project can ship. These
assertions are the defence.

---

## 8. Architecture

```
quran.koplugin/
  _meta.lua           -- name, description, version
  main.lua            -- plugin entry, menu registration
  reader.lua          -- render loop, pagination, position memory
  navigator.lua       -- surah / juz pickers
  reference.lua       -- "2:255" parser
  display.lua         -- Arabic / English / both
  settings.lua        -- typography

(Shipped as `quranreader.lua` / `quransettings.lua`: KOReader's own
repo root has a `reader.lua` — the application launcher — and a plugin
doing `require("reader")` can load that instead. Namespacing removes the
dependency on package.path ordering.)
  db.lua              -- SQLite layer
  data/
    quran.db
    manifest.json
    fonts/
      UthmanicHafs.ttf
```

Plus a KUAL entry:

```
extensions/quran/
  menu.json    -- "Qur'an" → launch KOReader into the plugin
  config.xml
```

**Keep the engine scripture-agnostic** even though only one pack ships. Surah
names, direction, script and fonts come from data, not from code. That is what
makes the Bible a v2 data task rather than a rewrite.

---

## 9. Typography

Starting values, to be tuned on the device — do not treat as final.

| | Default | Floor |
|---|---|---|
| Arabic | 34 px | 26 px |
| English | 22 px | 16 px |
| Arabic line height | 1.9 × | 1.7 × |
| English line height | 1.5 × | 1.35 × |
| Side margins | 40 px | 24 px |

Arabic needs markedly more leading than Latin: harakat sit above and below the
baseline, and tight lines collide. The two sizes are **independently
adjustable** because a reader wanting large Arabic rarely wants equally large
English.

**Font: settled.** Scheherazade New (SIL, OFL 1.1), vendored in `fonts/` and
chosen by eye on a Paperwhite 11. Verified to cover every codepoint in the
corpus, with GSUB and GPOS present. KFGQPC Uthmanic Script HAFS is the most
authentic face but is **proprietary and may not be redistributed**, so it is
ruled out for a KindleForge release — see `THIRD-PARTY.md`.

**Arabic size: settled at 34 px**, chosen on device against Scheherazade New
after comparing 26/30/34/38/44. Harakat clear the line above at that size.
This is a Paperwhite 11 number; a 167 ppi device will want its own.

**Re-confirmed at 34 px in the interleaved column**, 12 August 2026 — the
open question in §9.1 ("chosen at full width, re-judge it in 562 px") is
answered: it did not need to change.

**Interleaved leading: settled at 0.9** (`rows_line_height`), tuned live on
device the same day. Measured geometry at 34 px on a PW11: the face scales to
~71 px, so

| leading | line pitch | Arabic lines per page |
|---|---|---|
| 0.3 | 92 px | 17 |
| **0.9** | **135 px** | **11** |
| 1.5 | 178 px | 8 |

It shipped at 0.3 on the argument that the leading existed only to clear the
per-line rules, which interleaved mode does not have. That argument was right
about the rules and wrong about legibility: **Arabic with stacked harakat needs
the room whether or not anything is drawn in it.** Six lines a page is the
price.

Note where it landed — 0.9 is exactly what this section's "1.9 × line height"
maps to, and the value the project shipped before 1.5 was reached for to cure
the rule clipping. That cure failed and was replaced by measuring the gap. The
eye came back to the spec's original number.

Consequence for Arabic-only mode: its `arabic_line_height` is still 1.5, and on
this evidence is too large. It is deliberately unchanged — that mode has not
been read on device since, and still carries the `top_line_num` defect, so its
typography cannot be judged until its paging works.

### 9.1 Interleaved layout — side-by-side ayah rows (Milestone 3)

Decided 11 August 2026 from a reference screenshot, and confirmed side-by-side
over the stacked alternative.

**The ayah is the layout unit.** One row per ayah:

```
+----------------------------+----------------------------+
| 39. Comprising many from   |  <Arabic, RTL>        (٣٩) |
|     the first generations, |                            |
+============================+============================+
| 40. And many from the      |  <Arabic, RTL>        (٤٠) |
|     later ones.            |                            |
+============================+============================+
```

- **Left column:** translation, LTR, English face and leading.
- **Right column:** Arabic, RTL, Arabic face and leading, ayah marker trailing.
- **Row height:** the taller of the two cells. Neither column is padded to a
  fixed height.
- **Rule:** one horizontal rule per row, in the **gutter below** it.

#### Why this supersedes the §9 ruled lines, and does not extend them

The M2 rules are drawn every `line_height_px` and can land on any glyph — which
is exactly what has been clipping harakat, and why `RULE_GAP_FRACTION` exists as
a device-tuned knob. **A row rule has no such problem**: it sits in a gutter
whose height the reader computes, between two rows it also computed. No glyph
occupies that band, so none can be cut. The knob is not needed here.

Per-line rules therefore remain for **Arabic-only mode**, where lines are the
unit and there is nothing else to rule against. Interleaved mode does not use
them. Two modes, two rule models — do not try to unify them.

#### Geometry on the PW11

1236 px wide. After 40 px side margins and a 32 px gutter, each column is
**562 px**. That is a narrow measure for Arabic: 2:255 wraps to roughly 13 lines
at 562 px against 7 at full width. Accepted deliberately in exchange for the
reference layout's density.

Two consequences the implementation must handle rather than assume away:

- **The Arabic default of 34 px was chosen at full width.** Re-judge it on
  device in a 562 px column; it may want to come down, and §9's independent
  Arabic/English sizing is what makes that possible without shrinking English.
- **A single ayah can exceed a page.** 2:282 will, at any supported size. See
  the overflow rule below.

#### Pagination

Fill each page with **as many complete rows as fit**. Never cut a row to squeeze
it in — if the next does not fit whole, it starts the next page.

**Exception:** a row taller than a page splits across as many pages as it needs.
Measure this against the **rendered** height at the reader's current font size,
not a character count — Arabic wraps by shaped width, so a count predicts
nothing. Verify against **2:282 at the largest supported size**, where it is
worst.

#### Direction

The two columns have opposite paragraph direction. Set each cell's direction
explicitly rather than relying on `auto_para_direction` to infer it — an ayah
whose translation opens with a digit ("39.") is exactly the case where
detection is least reliable.

#### The basmala row

Not a row. It is a **heading spanning both columns**, above the first row of
every surah but 1 and 9 — see §6, which also records why the two packs disagree
about where it lives and how the split is made safe.

Getting this wrong is not subtle: the Arabic cell of the first row would carry
the basmala while the English cell did not, in 112 surahs. `check_alignment.py`
is the guard, and it must pass before any pack pair is used.

#### Position memory

A position is an **ayah reference**, not a byte offset, so it survives a mode
switch: stopping at 2:255 in Arabic-only must resume at 2:255 interleaved. The
existing `positions = { ["2"] = { ayah = N, line = M } }` already carries the
ayah; `line` becomes meaningful only within a split row.

### Ruled lines (Milestone 2)

Long RTL lines are hard for the eye to track back along — ruled mushafs and
lined paper solve the same problem. The reader should draw a horizontal rule
between lines, with the extra leading above.

Verified against KOReader source, so M2 need not repeat the research:

- `TextBoxWidget` accepts `line_height` (em, **default 0.3**). That is the
  leading control.
- **`InfoMessage` does not forward `line_height`.** It passes only text, face,
  width, height, alignment, lang, and the two para-direction flags. So the
  Milestone 0 display widget cannot do leading *or* rules, and M2 must build
  on `TextBoxWidget` directly rather than going through `InfoMessage`.
- `TextBoxWidget` exposes `line_height_px`, `lines_per_page` and
  `vertical_string_list` after init. Draw rules at `line_height_px` intervals
  so they land on the text's own baselines; spacing them by guesswork drifts
  out of register as the block grows.
- Those fields are commented **"for internal use"** upstream. Treat as
  MUST-VERIFY against the pinned KOReader version, and re-check on upgrade.

On e-ink, rules want to be light — a thin grey, not full black — or they
compete with the text they are meant to support. That is a device judgement,
not a desktop one.

---

## 10. Performance

| Action | Target |
|---|---|
| Page turn | < 400 ms, partial refresh |
| Jump to reference | < 1 s |
| Cold start to last position | < 3 s |
| Full refresh | every ~6 turns, or on view change |

Render one screen at a time. The Qur'an is small enough to tempt you into
loading it whole — don't, because the Bible pack later will not be.

---

## 11. Milestones

| # | Deliverable | Proves |
|---|---|---|
| **0** | Hello-world `.koplugin` on the PW11 rendering one hard-coded Uthmani ayah with correct shaping, joining and harakat | **The premise.** |
| 1 | Pipeline → validated `quran.db` passing every §7 assertion | Data integrity |
| 2 | Reader: continuous scroll, position memory, typography, **ruled lines** | The core loop |
| **3** | **Translation pack format + interleaved ayah-row layout (§9.1), row pagination, mode switch** | **The reason to build this rather than read an EPUB** |
| 4 | Navigator (surah + juz) and reference parser | Fast movement |
| 5 | Bismillah/sajdah rules, bookmarks, About | Feature-complete |
| 6 | Packaging, README, screenshots | Done |

Milestone 3 was promoted from `docs/BACKLOG.md` §B1 on 11 August 2026, when the
personal-use decision (§1) cleared its licensing blocker. It moved ahead of the
navigator because it changes the pagination model — building navigation against
a model that is about to be replaced would mean building it twice.

**Milestone 0 is a gate.** Build nothing else until Arabic shapes correctly on
your actual device. If it fails, the architecture changes and everything built
after it is wasted.

---

## 12. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Arabic shaping fails on device | **Fatal** | Milestone 0, week 1, before anything else |
| Font licence blocks redistribution | Medium | Amiri (OFL) as the fallback; decided before M1 |
| Text corruption in pipeline | **High** | §7 assertions; checksum; spot-check famous verses by eye |
| KOReader API drift | Medium | Pin a minimum version in `_meta.lua` |
| Jailbreak/KOReader unavailable on your firmware | Medium | Verify before starting — this gates everything |

---

## 13. v2 candidates

Search (verify FTS5 in KOReader's SQLite build) · Bible pack on the same engine
· Indonesian translation, licensing permitting · tafsir · transliteration ·
bookmarks export · word-by-word.

Items with enough shape to need designing before they are picked up live in
`docs/BACKLOG.md`. **B1 is no longer among them** — it was promoted into v1 as
Milestone 3 on 11 August 2026. Its licensing survey stays in that file, because
it becomes live again the moment a public release is considered.
