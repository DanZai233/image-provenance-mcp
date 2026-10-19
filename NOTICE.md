# Third-party code

## image-forensics-mcp (tier 2 pixel heuristics)

- Upstream: https://github.com/surewht/image-forensics-mcp
- Pinned commit: `c504667cdb1a3d9342b628275ef80721d83548a5` (v0.2.0)
- License: MIT, Copyright (c) 2026 surewht — full text in
  [`LICENSES-image-forensics-mcp.txt`](LICENSES-image-forensics-mcp.txt)

Vendored under `src/provenance_mcp/pixel/`:

| file | upstream file | changes |
|---|---|---|
| `helpers.py` | `image_forensics/helpers.py` | import paths only |
| `noise_map.py` | `image_forensics/noise_map.py` | import paths only |
| `ela.py` | `image_forensics/ela.py` | import paths only |
| `frequency.py` | `image_forensics/frequency.py` | import paths only |
| `spectral_decay.py` | `image_forensics/spectral_decay.py` | import paths only |
| `color.py` | `image_forensics/color.py` | import paths only |
| `metadata.py` | `image_forensics/metadata.py` | import paths only |
| `full_report.py` | `image_forensics/full_report.py` | import paths only |
| `_app.py` | `image_forensics/_app.py` | rewritten: re-exports this project's `mcp` app |

The algorithms, thresholds and flag strings are upstream's. They are kept
byte-for-byte so that tier-2 output stays comparable with the original project —
including its weaknesses (see "Limitations" in the README).

Why vendored rather than depended upon: at the time of writing the upstream
package was not on PyPI, and installing it from a git URL failed on a broken
`pyproject.toml`. Vendoring keeps this server installable offline and lets tier 1
run with no third-party dependencies at all.
