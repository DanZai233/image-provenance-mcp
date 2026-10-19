---
name: image-forensic-triage
description: Decide whether a photo, a photo of a document, or a screenshot is AI-generated, edited, or a genuine capture. Signed C2PA provenance first, file structure second, content plausibility third, and pixel heuristics last — as leads, never as proof. Use when someone asks "这张图是不是伪造的 / 是不是 AI 生成的", when auditing evidence attachments (工单、报告、投诉材料), or when any claim rests on a photograph.
license: MIT
---

# Image Forensic Triage

An image either carries a signed claim about its own origin, or it does not. Everything
else is inference. This skill keeps those two things strictly separated so the answer is
honest about its own strength.

**The one rule that matters:** never let a pixel score decide a question a signature could
have answered. And when there is no signature, say what the evidence *is*, not what you
wish it were.

## When to activate

- "这张图是不是 AI 生成的 / 是不是 P 的 / 是不是伪造的"
- "帮我看看这份材料能不能用" when the material includes photos
- Auditing a folder of attachments before they go into a report
- A dispute where either side relies on a photograph as proof

## Evidence grades

Every conclusion must land in exactly one grade. Do not blur them.

| Grade | Basis | What you may say |
|---|---|---|
| **A** | Valid C2PA manifest + pixel hash verified | "The signer declares X; pixels are the signed pixels." Decisive. |
| **B** | Metadata + structure + content all consistent | "No sign of tampering; consistent with a genuine capture of Y." |
| **C** | Visual inspection only | "Visually plausible / implausible because …" Explicitly a guess. |
| **D** | Nothing recoverable | "This file cannot answer the question. Get the original." |

Full definitions in `references/evidence-grading.md`.

## The pipeline

### Step 0 — establish what you are holding

Before any analysis, decide which of these it is, because it caps the achievable grade:

```bash
# size, format, EXIF, C2PA carrier in one shot
python -m provenance_mcp.cli FILE 2>/dev/null || image-provenance FILE
```

| What you see | What it means | Ceiling |
|---|---|---|
| 3000×4000+, full EXIF | camera original | A or B |
| ~1000 px, EXIF empty, JFIF 96dpi | passed through a messenger or a report export | C at best |
| 540×618, 100 KB | resized for a Word/PDF attachment | C, and edits are undetectable |
| `WeChat` / `微信图片_` in the name | messenger re-encode: manifest and EXIF both gone | C |

State the ceiling out loud before analysing. Half of all bad forensic reports skip this.

### Step 1 — C2PA (stop here if present)

```bash
image-provenance FILE --mode c2pa     # or MCP tool: c2pa_inspect
```

Read four fields, in this order:

1. `verdict` — `AI_GENERATED` / `INVALID_HASH` / valid-but-camera
2. `digitalSourceType` — `trainedAlgorithmicMedia` means the signer itself says "synthetic"
3. `claim_generator` + `actions` — who made it and when (`c2pa.created` by `ChatGPT`)
4. `hash` — `pixel hash VERIFIED` means nobody touched it after signing

`INVALID_HASH` is the strongest negative result available anywhere in this domain: someone
edited a signed file. Say so plainly.

If a manifest exists, **stop**. Run no pixel analysis. It has nothing to add.

### Step 2 — structure (no manifest)

```bash
python skills/image-forensic-triage/scripts/triage.py FILE...   # batch ledger
```

What it reports and why it matters:

- **Exif tags: 0** → stripped. Neither proof nor disproof; it removes a whole evidence path.
- **Dimensions well below the sensor** → resampled. Patch-based forensics (ELA, block noise)
  dies at resampling, so any "no anomaly" result afterwards is vacuous.
- **Exact-colour runs** → vector annotation. A red box with 489 pixels of exactly `(187,24,7)`
  was drawn in software. That establishes *the file was edited*, and you should say so —
  it is usually benign (someone circled the relevant reading) but it ends "pristine file".
- **8×8 block-noise outliers** → candidate paste boundary. max/mean above ~3 is worth a look;
  at these compression levels it is usually just text edges. Never call it forgery alone.

### Step 3 — content (the part that actually decides document cases)

Look at the image, at 4×–12× zoom, and check:

- **Physical plausibility** — a handheld probe reading 100.0 °C in a living room; a wall clock
  showing a different time than the watermark; shadows pointing two ways.
- **Text integrity** — dense correct Chinese in a HMI/表格/公文 is the single best AI detector
  available to the eye. Generators garble it; cameras never do.
- **Capture physics** — moiré, chromatic fringing (warm on one side, cyan on the other), screen
  bezel, glare, paper grain. Their absence on a "photo of a screen" is a red flag.
- **Watermark app** — 水印相机 style stamps (place + time) are added by software. Compare
  the stamp between two files: same place, minutes apart, but one is signed by an AI service →
  the stamp was reproduced on purpose.
- **Annotation layer** — see Step 2; note which elements are digital.

### Step 4 — external corroboration

For documents, the image is the least reliable part. Check the claim itself:

```python
# PRC ID checksum (GB 11643) — a lazy fake usually fails it
W = [7,9,10,5,8,4,2,1,6,3,7,9,10,5,8,4,2]
def id_ok(s):
    return "10X98765432"[sum(int(c)*w for c, w in zip(s[:17], W)) % 11] == s[-1].upper()
```

- Company exists? (工商信息: 天眼查 / 企查查 / 国家企业信用信息公示系统)
- Dates internally consistent? (入职 + 合同期 = 离职日; 落款 = 离职日)
- Issuer reachable for a callback? This is what actually verifies a 离职证明.

Record these as *content* findings, never as image findings.

### Step 5 — write it up

Use exactly this shape. It is designed so a reader cannot mistake a grade-C guess for a
grade-A result.

```markdown
## 结论
[one sentence + grade]

## 证据
| 层 | 发现 | 强度 |
|---|---|---|
| C2PA | … | 决定性/无 |
| 结构 | … | 中 |
| 内容 | … | 弱-中 |
| 外部 | … | 中 |

## 能证明什么
## 不能证明什么
## 下一步
```

## Red lines

- **No pixel score may produce "authentic".** Tier 2 output is a lead. If you write
  "LIKELY AUTHENTIC" without a manifest behind it, you have invented evidence.
- **"这张图没被改过" ≠ "这份文件是真的".** Separate the two sentences; only the first is
  ever about pixels.
- **Recompression destroys the question, not the answer.** A WeChat file cannot be cleared;
  it can only be declared inconclusive. Say which.
- **Do not give legal conclusions.** "可以作为证据" is a lawyer's call, not a forensic one.
- **Missing camera data is not suspicious.** Most pipelines strip it; treat `Exif tags: 0`
  as "path closed", not "path negative".

## Known false positives

Read `references/false-positives.md` before defending any tier-2 number. Highlights:
a blue industrial HMI screen trips "high ratio of vivid pixels"; AI images with smooth
gradients score "natural" noise uniformity; ELA on a resized JPEG always looks uniform.

## Worked examples

`references/worked-examples.md` has three real cases with the actual numbers — a signed AI
image, an unsignable document photo, and a photo of a screen — including where the tool was
wrong and the human read was right.
