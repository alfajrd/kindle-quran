# Report to Tanzil — E1

Ready to send. Post to the Tanzil text mailing list:
**<https://groups.google.com/g/tanzil-text>**

There is no contact form or email address anywhere on tanzil.net — the
`/updates/` page documents corrections but offers no route to submit one, and
`/docs/` gives no contact either. The mailing list is the only channel the
project provides, and it is specifically about the text.

Sending this is worthwhile beyond politeness: if Tanzil corrects it upstream,
our `data/errata.tsv` `before` hash stops matching, our build fails loudly,
and we delete two lines. Everyone else using the Uthmani edition benefits at
the same time.

---

## Subject

    Uthmani text: spurious shadda on the basmala of 95:1 and 97:1

## Body

> Assalamu alaikum,
>
> I believe I have found a small defect in the Uthmani text, affecting two
> ayat. I am reporting it because Tanzil's own editions disagree with each
> other about it, which suggests a processing step rather than a variant
> reading.
>
> **What**
>
> The basmala is embedded as a prefix of ayah 1 in 113 surahs. In 111 of them
> it is one identical 38-codepoint string. In 95:1 and 97:1 it carries an
> extra U+0651 ARABIC SHADDA on the initial bāʾ:
>
> ```
> 111 surahs :  0628 0650 0633 0652 ...       بِسْمِ    bāʾ + kasra
> 95:1, 97:1 :  0628 0651 0650 0633 ...       بِّسْمِ   bāʾ + SHADDA + kasra
> ```
>
> Deleting that single codepoint makes both byte-identical to the other 111.
>
> **Why I think it is a defect and not a variant**
>
> Checked across every Arabic text edition Tanzil publishes:
>
> | Edition | 95:1 / 97:1 |
> |---|---|
> | quran-uthmani | affected |
> | quran-simple-enhanced | affected |
> | quran-uthmani-quran-academy | affected |
> | quran-uthmani-min | clean |
> | quran-simple | clean |
> | quran-simple-clean | clean |
> | quran-simple-min | clean |
>
> The anomaly appears in exactly the three enhanced/full-mark editions and in
> none of the simple or minimal ones. Shadda is a base consonant-doubling
> mark rather than an optional annotation, and the simple editions do carry
> shadda elsewhere — they simply do not place one on this bāʾ. A genuine
> variant reading would appear in all of them. That the three affected
> editions are affected identically points at a shared mark-application step
> rather than at one file.
>
> I also note tanzil.net/docs/ describes the Uthmani text as "completely
> matching the Medina Mushaf", which is what led me to treat the
> inconsistency as unintended rather than deliberate.
>
> **How it was found**
>
> Building an offline Qur'an reader. Every structural check we had passed —
> U+0651 is a legitimate codepoint, so a character whitelist admits it, and a
> corpus checksum only proves a database faithfully reproduces its input. It
> surfaced only on comparing the basmala prefix across all 113 surahs.
>
> We are not modifying the text we redistribute: the downloaded file is kept
> byte-exact, and the correction is applied at build time from a declared,
> hash-verified erratum, disclosed to the reader. If a corrected edition is
> published we will drop that erratum immediately.
>
> Happy to supply the exact byte offsets, the extraction script, or the
> per-edition comparison if useful.
>
> Jazakum Allahu khayran for the work — the text and its documentation are
> excellent, which is why the inconsistency stood out.
>
> — <your name>
