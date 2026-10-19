# image-provenance-mcp

**Read the signature before guessing from pixels.**

An MCP server for one question: *is this image AI-made, edited, or real?* It answers in two tiers,
in the only order that makes sense:

1. **C2PA Content Credentials** — signed, machine-verifiable provenance. When the file carries a
   manifest, that is the answer and we stop.
2. **Pixel heuristics** — noise, ELA, spectral decay, colour, EXIF. Used *only* when tier 1 has
   nothing to say, and always labelled as a guess.

No API keys, no cloud calls, no telemetry. Tier 1 needs nothing but the Python standard library
plus the `openssl` binary you already have.

## Why the order matters

Running this on a ChatGPT (gpt-image) PNG:

| signal | says |
|---|---|
| noise uniformity score `8.27` | "natural-looking" |
| no camera EXIF, square-ish crop | "suspicious" |
| **C2PA manifest** | **`trainedAlgorithmicMedia`, created by ChatGPT** |

The heuristics hedged both ways and would have produced a confident-sounding `POSSIBLY
AI-GENERATED`. The manifest produced a fact. Same pipeline, opposite direction on a WeChat
re-upload: the messenger strips EXIF, the heuristics fire `META_NO_CAMERA` plus uniform ELA, and
you get an AI accusation built entirely from metadata that was removed in transit.

Heuristics describe *artifacts*; C2PA describes *authorship*. Do not let the first impersonate
the second.

## Tools

| tool | tier | what it returns |
|---|---|---|
| `image_provenance` | 1 → 2 | the whole pipeline, tier 1 first; stubs out tier 2 if a manifest exists |
| `c2pa_inspect` | 1 | signed provenance only — faster, and works with zero pixel deps |
| `full_forensic_report` | 2 | all heuristic analysers plus a combined verdict |
| `noise_map`, `error_level_analysis`, `frequency_analysis`, `spectral_decay_analysis`, `color_analysis`, `metadata_check` | 2 | the individual analysers |

Tier-2 tools are vendored from [`surewht/image-forensics-mcp`](https://github.com/surewht/image-forensics-mcp)
(MIT — see [NOTICE.md](NOTICE.md)). They need the `[pixel]` extra; without it they simply are not
registered and the C2PA tools keep working.

## Verdicts (tier 1)

| verdict | meaning |
|---|---|
| `AI_GENERATED` | the signer declares `digitalSourceType=trainedAlgorithmicMedia` — **a fact about the file** |
| `EDITED` | signed action history contains `edited` / `opened` / `filtered` / `repackaged` |
| `CAPTURED` | only capture-side actions were signed |
| `INVALID_HASH` | manifest present but pixels no longer match the signed hash — **modified after signing** |
| `NO_C2PA` | nothing signed in this file — says nothing about authenticity |

## Install

```bash
git clone https://github.com/DanZai233/image-provenance-mcp
cd image-provenance-mcp
pip install -e '.[pixel]'      # omit [pixel] for C2PA only
```

No network to a package index? Skip packaging entirely and run from the tree:

```bash
PYTHONPATH=src python -m provenance_mcp photo.jpg
PYTHONPATH=src python -m provenance_mcp --mcp        # stdio MCP server
```

Tier 1 needs only the standard library and `openssl`, so that works on a bare
interpreter.

## CLI

```bash
image-provenance photo.jpg              # tier 1, then tier 2 if needed
image-provenance photo.jpg --mode c2pa  # signature only
image-provenance photo.jpg --mode pixels
image-provenance photo.jpg --json       # parsed manifest as JSON
image-provenance --mcp                  # stdio MCP server
```

Exit codes: `0` a manifest was found, `1` no manifest, `2` usage error.

## Wire it into an MCP client

Generic stdio config:

```json
{
  "mcpServers": {
    "image-provenance": {
      "command": "image-provenance",
      "args": ["--mcp"]
    }
  }
}
```

DeepSeek Harness (`~/.dsh/profiles/web/cordis.patch.yml`):

```yaml
- insert:
    - id: mcp-image-provenance
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: image_provenance
        transport: stdio
        command: image-provenance
        args: ['--mcp']
        toolCallTimeoutMs: 180000
```

Check the wiring without any SDK — the probe speaks raw JSON-RPC over stdio:

```bash
python examples/probe_mcp.py image-provenance --mcp
```

## What is actually verified

| test | result |
|---|---|
| ChatGPT/gpt-image PNG | `AI_GENERATED`, generator `OpenAI Media Service API` (c2pa-rs 0.79.2), chain `CN=OpenAI Media Service` ← `Trufo C2PA Claim Signing CA` |
| hard binding recomputed | `sha256 cbd859ea…` matches the signed value |
| **tamper**: flip one byte inside IDAT, keep the manifest | `INVALID_HASH`; both hashing strategies independently produce `37bf1185…`, so the mismatch is the content's fault, not the verifier's |
| PNG without a manifest | `NO_C2PA`, no crash |
| truncated file | `NO_C2PA`, no crash |
| 20 unit tests | `python -m unittest discover -s tests` |

## Limitations (read these)

- **No cryptographic signature verification.** This tool checks the sha256 hard binding and prints
  the COSE `x5chain`; it does not verify the signature, check revocation, or validate against a
  trust anchor. So `INVALID_HASH` is trustworthy (pure hashing), while "this chain is genuine" is
  currently only "this chain looks right". For the full check use `c2patool` or `c2pa-python`.
- **C2PA presence is not C2PA ubiquity.** Most cameras, every messenger, every screenshot pipeline
  and every CDN re-encode strips manifests. `NO_C2PA` is the common case, not a red flag.
- JPEG APP11 multi-segment reassembly follows the spec but has no end-to-end test with a real
  signed JPEG; only PNG manifests were validated here.
- Old XMP-embedded `c2pa` fields (early Adobe style) are not parsed; only JUMBF.
- Tier-2 thresholds are upstream's and were tuned on a small sample. Treat every tier-2 verdict as
  a hint.
- Tier 2 needs `numpy`, `scipy`, `pillow`.

## License

MIT for this project. Vendored tier-2 code is MIT, © 2026 surewht — see
[NOTICE.md](NOTICE.md) and [LICENSES-image-forensics-mcp.txt](LICENSES-image-forensics-mcp.txt).
