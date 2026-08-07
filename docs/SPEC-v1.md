# Qur'an — v1 Specification

**Target:** Kindle Paperwhite 11th gen (jailbroken)
**Runtime:** KOReader plugin, launched from KUAL, distributed via KindleForge
**Content:** Uthmani Arabic + English translation
**Status:** draft for review · 6 August 2026

---

## 1. Decisions taken

| | |
|---|---|
| Name | **Qur'an** |
| Scope | Qur'an only. Bible deferred to v2. |
| Languages | Arabic (Uthmani) + English translation |
| Device | Kindle Paperwhite 11 — **and only that**, for v1 |
| Runtime | KOReader plugin (`.koplugin`), Lua |

Narrowing to one device and one scripture removes most of the risk in the
previous draft. What remains is concentrated in one place: §3.

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
4. **Display modes** — Arabic only · English only · both interleaved
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
- **Ayah markers.** Use U+06DD with the Arabic-Indic ayah number — never a
  Latin numeral inside Arabic text.
- **Sajdah.** 15 verses carry a prostration mark. Flag them in the data and
  render the mark; do not synthesise one.
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

**Font:** KFGQPC Uthmanic Script HAFS if its licence permits redistribution;
otherwise Amiri (OFL). Decide by diacritic coverage, checked on-device against
known-difficult verses.

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
| 2 | Reader: continuous scroll, position memory, typography | The core loop |
| 3 | Navigator (surah + juz) and reference parser | Why it beats an EPUB |
| 4 | Display modes, Bismillah/sajdah rules, bookmarks, About | Feature-complete |
| 5 | KindleForge packaging, README, screenshots | Ship |

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
