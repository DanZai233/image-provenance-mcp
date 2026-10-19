# Worked Examples

Three real cases. In each one the interesting part is the gap between what the tool said and
what the evidence could actually support.

---

## Case 1 — A photo that was never a photo

`thermometer.png` · 841×1870 PNG · 1,896,278 bytes

**Tier 1 (decisive):**

```
Manifest carrier: png:caBX
Verdict:          AI_GENERATED
digitalSourceType: trainedAlgorithmicMedia
Claim generator:  OpenAI Media Service API   (c2pa-rs 0.79.2, spec 2.2.0)
Action:           c2pa.created by ChatGPT at 2026-10-14T03:32:01Z
Hard binding:     sha256 VERIFIED
Chain:            OpenAI Media Service ← Trufo C2PA Claim Signing CA (2025)
                                   ← Trufo Root CA (2025, ECC P384)
```

Grade **A**. The signer itself declares the image synthetic, and the pixels are the signed
pixels — so there is no "but maybe it was edited" left to argue.

**What tier 2 said on the same file, before C2PA was wired in:** `POSSIBLY AI-GENERATED`,
driven by `Uniformity Score 1.6623 < 2.0`. A hedge, on a case that was fully decided by a
signature. This is the entire argument for tier ordering.

**Human-level tells, for when there is no signature:** 100.0 °C in a living room; the probe
held in mid-air, touching nothing; the reading is exactly the textbook boiling point with a
`.0` decimal — generators love round numbers; and the watermark reads the watermark place 13:42
2025-12-02, the same app, place and day as a genuine site photo taken 12 minutes earlier.

## Case 2 — A document that cannot be cleared by pixels

`resignation-letter.jpg` · 1773×2364 JPEG · 471,698 bytes

**Tier 1:** `NO_C2PA` — WeChat strips it. **Metadata:** `Exif tags: 0`.

That caps this file at grade **C** before any analysis. Everything after is content work.

**Tier 2 said:** `LIKELY AUTHENTIC`, `Uniformity 9.14`, `PSD beta -3.44`, but also
`[FLAG:ELA_UNIFORM]`. Opposite conclusions inside one report. None of it is quotable:
the file has been resampled by the messenger, which is exactly the condition under which
ELA and noise statistics stop carrying information.

**Content and external checks, which is where the actual work happened:**

| Check | Result |
|---|---|
| ID checksum (GB 11643) | `111111111111111111` → expected `8`, got `8` **PASS** |
| Region code | region code matched the home province |
| Timeline | 2023-07-01 → 2026-06-30, exactly three years, age 22 at hire |
| Signature date | 2026-06-30, same as the termination date |
| Company | the named employer exists (工商年报 2023 / 2025 available) |
| Seal | pale red, hand-written-looking glyph forms; HF energy inside strokes 32.6 vs 22.1 on blank paper — **inconclusive**, strokes are 3 px wide so edge contamination dominates |

Grade **B** for "no sign of tampering", grade **C** for anything stronger. The honest output
was: *the image is not the problem; the document's truth is verified by calling the issuer,
not by looking at pixels.*

## Case 3 — When the tool is simply wrong

`site-photo.jpg` · 540×618 JPEG · 102,726 bytes · 96 dpi JFIF

**Tier 1:** none. **EXIF:** none. **Dimensions:** 540×618 — resized for a report attachment.

**Tier 2 said:** `POSSIBLY AI-GENERATED — Color: high ratio of vivid pixels`.

False positive. The subject is a blue industrial HMI screen: saturated by construction.

**What actually decided it:**

- moiré from the screen's pixel grid, **chromatic fringing** (warm left, cyan right) around
  the white digits — both are camera-of-a-screen physics that no generator reproduces
- dense, correct Chinese HMI furniture: `频率 Hz 0.0Hz`, `运转 停止`, `故障 正常`,
  `方式 本地`, `阀门控制 / 变频控制 / 电磁阀控制`, `补水 0.00T`, `返回`
- readings form a coherent state: supply 43.1 °C / 0.25 MPa, return 36.0 °C / 0.16 MPa,
  ΔT 7.1 °C, ΔP 0.09 MPa, make-up water 0.00 T, both circulation pumps at 0.0 Hz
- the red highlight box is a **vector annotation**: 489 pixels of exactly `(187,24,7)`
  → the file was edited after capture (benign, but it ends "pristine file")
- 8×8 block-noise around the digits: 13.6 vs 16.3 on neighbouring background — no paste
  boundary, though at this compression level that proves little

Grade **C**. "Consistent with a genuine capture of a real screen; cannot rule out a
digit-level edit, because the file has been resized and annotated."

---

## What the three cases teach

| Case | Decision came from | Tool said | Gap |
|---|---|---|---|
| AI thermometer | signature | `POSSIBLY` | tier 2 was 90% confident where tier 1 was 100% |
| Document photo | content + external checks | `LIKELY AUTHENTIC` | tier 2 invented confidence the file could not support |
| HMI photo | human read of capture physics | `POSSIBLY AI` | tier 2 was outright wrong |

In all three, **the ranking of evidence mattered more than any single number**: signature
beats structure, structure beats content, content beats pixel statistics, and pixel
statistics never beat a phone call to the issuer.
