# Known False Positives and Blind Spots

Every item below was observed on a real file, not hypothesised. If you are about to defend a
tier-2 number, read this first.

---

## 1. "High ratio of vivid pixels" fires on any saturated subject

Observed on a photo of an industrial HMI screen (blue mimic diagram, red alarms):

```
Strong indicators (forensic anomalies):
  - Color: high ratio of vivid pixels
Verdict: POSSIBLY AI-GENERATED
```

The image was a genuine photo of a real monitor. The heuristic assumes natural scenes are
muted; screens, signs, night cityscapes, product shots on coloured backgrounds and
chromatic lighting all violate it.

**Correct read:** a saturated subject is a subject, not a symptom.

## 2. Noise uniformity mis-scores smooth AI images as "natural"

On a confirmed AI-generated image (C2PA: `trainedAlgorithmicMedia`):

```
Uniformity Score: 1.6623   (<2.0 → "suspiciously uniform")
Verdict: POSSIBLY AI-GENERATED
```

The score that was supposed to catch it produced only a hedge. Meanwhile a genuine
document photo scored `9.14` ("natural variation") while also triggering
`[FLAG:ELA_UNIFORM]` in the same report. Two metrics, opposite conclusions, same file.

**Correct read:** noise statistics have no stable decision boundary across sensors,
denoisers and resamplers. They separate populations in aggregate, not files.

## 3. ELA is meaningless after resampling

Any messenger, any "export from Word", any `max-width: 100%` on a web page resamples the
image and homogenises the 8×8 DCT grid. ELA then reports "very uniform error levels" for
everything — real photos and composites alike.

If `dimensions < sensor size` or `DPI = 96` with a JFIF header, **do not quote ELA at all**.

## 4. Stripped EXIF is normal, not suspicious

`Exif tags: 0` appears on:

- every WeChat / WhatsApp / Telegram image
- every screenshot
- every export from a document or a ticketing system
- every image that went through an image CDN

It closes an evidence path. It does not point toward forgery, and the tier-2 report's line
"No camera data (common for AI AND social media)" is true but useless — it is listed under
"weak" for a reason.

## 5. Vector annotations look like "editing" but usually are not

A uniform-colour rectangle (e.g. 489 pixels of exactly `(187,24,7)`) proves a human drew on
the file in software. In 处置报告 / 工单 / 投诉材料 this is the normal way to point at the
relevant reading.

**Correct read:** "the file is not the camera original" — then continue; do not call it
forgery.

## 6. Tiny images crash individual analysers

On a 1×1 PNG:

```
Spectral Decay: FAILED — expected non-empty vector for x
Color Analysis: FAILED — Shape of array too small to calculate a numerical gradient
```

The pipeline survives, but the report is full of FAILED sections that look like findings.
Below ~64 px, go straight to grade D.

## 7. Screenshot-of-a-screen is not the same as photo-of-a-screen

Photo-of-a-screen has moiré, chromatic fringing and perspective. A screenshot has none.
If a document claims "photo of the on-site screen" but shows no moiré or CA, it may be a
screenshot — a different provenance claim, and worth flagging as such (not as forgery).

## 8. C2PA's absence is not evidence of anything

Most cameras do not sign. Content Credentials ship on some Leica / Nikon / Sony bodies,
Adobe tools, and OpenAI / Google generators. A phone photo of a paper document almost never
has one.

`NO_C2PA` means: tier 1 is unavailable. Nothing more.

## 9. C2PA's presence does not mean the scene is true

A signed photo of a staged scene is a genuine file of a fake situation. Grade A speaks about
the file. Say "签名声明 X", never "照片里的人真的做了 Y".

## 10. Don't trust the filename

`WeChat图片_2026…jpg` is a strong hint of re-encoding, but the reverse is equally common:
someone renames a WeChat file to look like a camera original. Decide from bytes
(`JFIF`, EXIF, dimensions, quantisation tables), not from the name.
