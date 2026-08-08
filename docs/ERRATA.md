# Errata — known anomalies in the source text

Defects found in upstream sources, recorded here rather than silently
corrected.

**The vendored file `data/quran-uthmani.txt` is never edited** — it stays
byte-exact as Tanzil distributes it, so anyone can diff it against the source
and get zero differences. Tanzil's licence requires verbatim redistribution
of that file, and hand-editing scripture to tidy a checksum is precisely the
failure this project's checking exists to prevent.

**The shipped pack, however, is not byte-identical to the vendored file.**
Corrections listed below with status *applied* are applied at build time from
`data/errata.tsv`, each one hash-verified before and after. The pack is
therefore Tanzil's text **plus the declared corrections on this page** — see
each entry's Decision section for exactly what changed and why.

---

## E1 — Spurious SHADDA on the basmala of 95:1 and 97:1

**Status:** confirmed upstream defect · **APPLIED** at build from `data/errata.tsv` (vendored file left verbatim) · **not yet reported to Tanzil**
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

**Taken.** Ship the vendored text exactly as Tanzil distributes it —
`data/quran-uthmani.txt` stays byte-exact, forever, and is never edited to
fix this — while applying the correction **at build time**, from a
declared, hash-verified erratum (`data/errata.tsv`, row format `surah<TAB>
ayah<TAB>sha256(before)<TAB>sha256(after)<TAB>note`). `tools/build_pack.py`
locates the ayah, verifies `sha256(current) == before`, applies the one
declared structural edit — deleting the single already-present, hash-
verified `U+0651` codepoint, never a textual search-and-replace and never a
constructed replacement string — and verifies `sha256(result) == after`.
Any mismatch (including Tanzil quietly fixing this upstream, which would
make `before` stop matching) is a hard build failure; the correct response
to that is to delete the now-stale row from `data/errata.tsv`, never to
force the build through. `tools/verify_pack.py` independently re-derives
and re-checks all of this against the vendored file. The pack's `meta`
table records `errata_count` and `errata_ids` so an About screen can
disclose exactly what was corrected and why.

This was chosen over the alternative of holding the pack back until Tanzil
issues an upstream correction: the defect is well-evidenced (see "Why this
is a defect" above), affects only two ayat by one codepoint each, and a
declared, hash-verified, build-time correction is auditable and reversible
in a way hand-editing the vendored bytes never could be. Hand-editing the
vendored bytes was never among the options considered — it would violate
Tanzil's "not modified" redistribution term for the one file that term
actually governs.

### Reporting upstream

**Status: not yet sent.** A ready-to-post report is written out in
`docs/tanzil-report.md`.

Route: the Tanzil text mailing list, <https://groups.google.com/g/tanzil-text>.

Note the earlier draft of this section pointed at <http://tanzil.net/updates/>,
which was wrong. That page lists corrections Tanzil has *made*; it offers no
way to submit one. There is no contact form or email address on tanzil.net at
all — `/updates/` and `/docs/` were both checked, and `/contact` and `/wiki/`
do not exist. The mailing list is the only channel the project publishes, and
it is specifically about the text.

Worth sending rather than merely noting: if Tanzil corrects this upstream, the
`before` hash in `data/errata.tsv` stops matching, our build fails loudly, and
we delete the erratum. Everyone else using the Uthmani edition benefits at the
same time.
