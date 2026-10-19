# Evidence Grading

Four grades. Every finding you report belongs to exactly one. Mixing them is the single
most common way image "forensics" turns into confident noise.

---

## Grade A — signed and verified

Requirements, all of them:

1. A C2PA manifest is present and parses (`has_manifest: true`)
2. `c2pa.hash.data` recomputes to the stored value (`pixel hash VERIFIED`)
3. You read `digitalSourceType` and `claim_generator` from the claim itself

What it lets you say:

> 这张图的签名由 `<claim_generator>` 于 `<timestamp>` 产生，声明来源为
> `<digitalSourceType>`；签名后像素未被修改（哈希校验通过）。

What it still does not tell you:

- Whether the *scene* is real — a camera-signed photo of a staged scene is a real photo of
  a staged scene. C2PA signs capture, not truth.
- Whether the signer is trustworthy. The chain proves *which* key signed, not that the
  signer was honest. Report the chain; let the reader judge.
- Anything at all, if the manifest is `INVALID_HASH` — then the only claim you have is
  "this file was edited after signing".

## Grade B — no signature, but structure and content agree

You can reach B only when **all** of these hold:

| Check | Required result |
|---|---|
| Structure | one consistent compression history; no vector annotation layers |
| Content | physically plausible; text renders correctly; capture physics present |
| Metadata | either intact and consistent, or absent for a known-benign reason |
| External facts | names, IDs, dates, organizations all check out |

What you may say:

> 未发现篡改痕迹；图像、结构、内容三者与"一次真实拍摄"一致。

Never phrase it as authenticity. The honest form is "no evidence of tampering", which is
weaker than "authentic" by exactly the amount a good forgery costs.

## Grade C — visual inspection only

Everything downstream of a messenger re-encode, a resize, or a missing original. This is
where most real-world cases land, and where most confident answers are wrong.

What you may say:

> 视觉上自洽/不自洽，因为 …（具体到像素级观察）。这不足以证明真伪。

What you may **not** do:

- Cite tier-2 numbers as support. They are computed on resampled data; their "no anomaly"
  result is an artifact of the resampling, not a property of the scene.
- Say "没有发现伪造痕迹，所以是真的". At grade C the correct phrasing is
  "以现有文件无法判断".

## Grade D — nothing recoverable

Examples: 1×1 thumbnail, 40 px avatar, a heavily composited screenshot of a screenshot.
Correct answer:

> 这个文件无法回答该问题。需要原始文件。

Saying this is a good outcome. Guessing is not.

---

## Choosing the grade

```
有清单 → 哈希通过 ? A : (篡改已证实, 归入 A 级负面结论)
无清单 → 原始文件完好 ? → 结构+内容+外部全通过 ? B : C
        → 只有转发/压缩件 ? C
        → 尺寸/内容不足以分析 ? D
```

## Phrasing table

| Situation | Say | Do not say |
|---|---|---|
| manifest + verified hash, AI source | "签名声明为 AI 生成，像素未被改动" | "这张图是假的"（同义但丢掉了证据性质） |
| manifest + INVALID_HASH | "签名有效但像素与签名不符，签后被改" | "无法判断" |
| no manifest, clean structure | "未发现篡改痕迹（证据等级 B）" | "这张图是真的" |
| no manifest, re-encoded | "以现有文件无法判断真伪" | "LIKELY AUTHENTIC" |
| tier-2 flagged something | "某启发式指标异常，仅作线索" | "检测到 AI 痕迹" |
