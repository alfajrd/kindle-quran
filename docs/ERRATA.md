# Errata — known anomalies in the source text

Defects found in upstream sources, recorded here rather than silently
corrected. **Nothing in this file has been "fixed" in our data.** Tanzil's
licence requires verbatim redistribution, and editing scripture to make a
checksum tidy is precisely the failure this project's checking exists to
prevent.

---

## E1 — Spurious SHADDA on the basmala of 95:1 and 97:1

**Status:** confirmed upstream defect · not corrected here · **not yet reported to Tanzil**
**Affects:** surah 95 ayah 1, surah 97 ayah 1
**Severity:** two codepoints in ~330,000; orthographically wrong; visible to a reader who knows the text

### What

Tanzil's Uthmani edition embeds the basmala as a prefix of ayah 1 in 113
surahs (all but At-Tawbah). In 111 of them it is one identical 38-codepoint
string. In **95:1 and 97:1 it carries an extra `U+0651` ARABIC SHADDA on the
initial bāʾ**:

```
111 surahs :  0628 0650 0633 0652 ...     بِسْمِ    bāʾ + kasra
95:1, 97:1 :  0628 0651 0650 0633 ...     بِّسْمِ   bāʾ + SHADDA + kasra
```

Deleting that single codepoint makes both byte-identical to the other 111.

### Why this is a defect and not a variant reading

The decisive evidence is that **Tanzil's own editions disagree with each
other.** Checked across every Arabic text edition Tanzil publishes:

| Edition | 95:1 / 97:1 |
|---|---|
| `quran-uthmani` (ours) | **anomaly** |
| `quran-simple-enhanced` | **anomaly** |
| `quran-uthmani-quran-academy` | **anomaly** |
| `quran-uthmani-min` | clean |
| `quran-simple` | clean |
| `quran-simple-clean` | clean |
| `quran-simple-min` | clean |

The anomaly appears in exactly the three *enhanced/full-mark* editions and in
none of the simple or minimal ones. That pattern rules out a qirāʾāt variant:
shadda is a base consonant-doubling mark, not an optional annotation, and
Tanzil's simple editions do carry shadda elsewhere — they simply do not put
one on this bāʾ. A real variant would appear in all of them.

The most likely cause is a bug in whatever step applies full marks to the
enhanced editions.

### Why nothing in this repo caught it

Worth recording, because the same blind spot will recur:

- `U+0651` is a legitimate Arabic codepoint, so the character whitelist admits it.
- The corpus digest only proves the pack faithfully reproduces **what it was
  handed**. It cannot know the input was wrong.
- The single piece of human-verified ground truth is 2:255 — a mid-surah
  ayah, which structurally **cannot** expose a basmala defect however
  carefully it is checked.

Every automated check passed. It was found only by explicitly asking a
reviewer to look for what the checks could not see. **Structural verification
proves integrity of transmission, never correctness of source.**

### Decision

To be recorded here once taken. The options are: ship Tanzil verbatim with
this documented; or hold until Tanzil issues a correction. Hand-editing the
bytes is not among them.

### Reporting upstream

Tanzil maintains an errata process at <http://tanzil.net/updates/>. A report
should state: the two references, the exact codepoint sequences above, the
comparison table showing their own simple editions disagree, and that the
`quran-simple-enhanced` and `quran-uthmani-quran-academy` editions are
affected identically — which points at a shared mark-application step rather
than at one file.
