"""C2PA / Content Credentials reader.

JUMBF carriers (PNG caBX/jumb, JPEG APP11, WebP C2PA), CBOR claim decoding,
sha256 hard-binding verification and COSE x5chain pretty-printing.
Standard library only, except the system ``openssl`` binary used for certs.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys

# --------------------------------------------------------------------------
# CBOR (RFC 8949) — definite & indefinite lengths, tags, all majors we need.
# --------------------------------------------------------------------------


class CBORError(ValueError):
    pass


def _cbor_len(data: bytes, pos: int, info: int):
    if info < 24:
        return info, pos
    if info == 24:
        return data[pos], pos + 1
    if info == 25:
        return struct.unpack(">H", data[pos : pos + 2])[0], pos + 2
    if info == 26:
        return struct.unpack(">I", data[pos : pos + 4])[0], pos + 4
    if info == 27:
        return struct.unpack(">Q", data[pos : pos + 8])[0], pos + 8
    raise CBORError(f"reserved additional-info {info}")


def cbor_decode(data: bytes, pos: int = 0):
    """Decode one CBOR item; returns (value, next_pos)."""
    if pos >= len(data):
        raise CBORError("unexpected end of CBOR")
    ib = data[pos]
    major, info = ib >> 5, ib & 0x1F
    pos += 1

    if major == 0:
        return _cbor_len(data, pos, info)
    if major == 1:
        n, pos = _cbor_len(data, pos, info)
        return -1 - n, pos
    if major == 2:  # byte string
        if info == 31:
            out = b""
            while data[pos] != 0xFF:
                chunk, pos = cbor_decode(data, pos)
                out += chunk
            return out, pos + 1
        n, pos = _cbor_len(data, pos, info)
        return data[pos : pos + n], pos + n
    if major == 3:  # text string
        if info == 31:
            out = ""
            while data[pos] != 0xFF:
                chunk, pos = cbor_decode(data, pos)
                out += chunk
            return out, pos + 1
        n, pos = _cbor_len(data, pos, info)
        return data[pos : pos + n].decode("utf-8", "replace"), pos + n
    if major == 4:  # array
        if info == 31:
            out = []
            while data[pos] != 0xFF:
                v, pos = cbor_decode(data, pos)
                out.append(v)
            return out, pos + 1
        n, pos = _cbor_len(data, pos, info)
        out = []
        for _ in range(n):
            v, pos = cbor_decode(data, pos)
            out.append(v)
        return out, pos
    if major == 5:  # map
        if info == 31:
            out = {}
            while data[pos] != 0xFF:
                k, pos = cbor_decode(data, pos)
                v, pos = cbor_decode(data, pos)
                out[k] = v
            return out, pos + 1
        n, pos = _cbor_len(data, pos, info)
        out = {}
        for _ in range(n):
            k, pos = cbor_decode(data, pos)
            v, pos = cbor_decode(data, pos)
            out[k] = v
        return out, pos
    if major == 6:  # tag — decode and unwrap
        _, pos = _cbor_len(data, pos, info)
        return cbor_decode(data, pos)
    if major == 7:
        if info == 20:
            return False, pos
        if info == 21:
            return True, pos
        if info in (22, 23):
            return None, pos
        if info == 25:
            return struct.unpack(">e", data[pos : pos + 2])[0], pos + 2
        if info == 26:
            return struct.unpack(">f", data[pos : pos + 4])[0], pos + 4
        if info == 27:
            return struct.unpack(">d", data[pos : pos + 8])[0], pos + 8
        if info == 31:
            return None, pos + 1  # break
        raise CBORError(f"simple value {info}")
    raise CBORError(f"bad major {major}")


# --------------------------------------------------------------------------
# JUMBF (ISO/IEC 19566-5) box walker
# --------------------------------------------------------------------------

JUMD_LABEL = 0x02
JUMP_MARKERS = (b"jumb", b"jumd", b"cbor", b"json", b"uuid", b"bidb", b"jumb")


class Box:
    __slots__ = ("type", "payload", "start", "total")

    def __init__(self, type_: str, payload: bytes, start: int = 0, total: int = 0):
        self.type = type_
        self.payload = payload
        self.start = start
        self.total = total

    def __repr__(self):
        return f"<Box {self.type} {len(self.payload)}b>"


def parse_boxes(data: bytes) -> list[Box]:
    """Parse a flat sequence of ISO boxes (JUMBF / JPEG-XL superset)."""
    boxes, pos = [], 0
    while pos + 8 <= len(data):
        size = struct.unpack(">I", data[pos : pos + 4])[0]
        type_ = data[pos + 4 : pos + 8].decode("latin1")
        hdr = 8
        if size == 1:  # 64-bit size
            if pos + 16 > len(data):
                break
            size = struct.unpack(">Q", data[pos + 8 : pos + 16])[0]
            hdr = 16
        elif size == 0:  # extends to EOF
            size = len(data) - pos
        if size < hdr or pos + size > len(data):
            break
        boxes.append(Box(type_, data[pos + hdr : pos + size], pos, size))
        pos += size
    return boxes


def jumd_label(payload: bytes) -> str:
    """Label lives after a 16-byte UUID + 1 toggle byte."""
    if len(payload) < 17:
        return ""
    toggles = payload[16]
    if not (toggles & JUMD_LABEL):
        return ""
    rest = payload[17:]
    end = rest.find(b"\x00")
    raw = rest if end < 0 else rest[:end]
    return raw.decode("utf-8", "replace")


def walk_jumbf(data: bytes, path: str = "") -> list[dict]:
    """Recursively collect {label, json, cbor, boxes} for every JUBMF node."""
    nodes = []
    for box in parse_boxes(data):
        if box.type == "jumb":
            label, inner = "", box.payload
            children = parse_boxes(inner)
            if children and children[0].type == "jumd":
                label = jumd_label(children[0].payload)
            node = {"label": label, "cbor": None, "json": None, "boxes": [c.type for c in children]}
            for c in children:
                if c.type == "cbor":
                    try:
                        node["cbor"] = cbor_decode(c.payload)[0]
                    except Exception:
                        node["cbor"] = None
                elif c.type == "json":
                    try:
                        node["json"] = json.loads(c.payload.decode("utf-8", "replace"))
                    except Exception:
                        node["json"] = None
            node["path"] = f"{path}/{label}" if label else path
            nodes.append(node)
            if any(b == "jumb" for b in node["boxes"]):
                nodes.extend(walk_jumbf(inner, node["path"]))
    return nodes


# --------------------------------------------------------------------------
# Carriers — pull the raw JUMBF store out of the file container
# --------------------------------------------------------------------------


def png_chunks(data: bytes):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return
    pos = 8
    while pos + 8 <= len(data):
        ln = struct.unpack(">I", data[pos : pos + 4])[0]
        typ = data[pos + 4 : pos + 8]
        yield typ, pos, ln
        if typ == b"IEND":
            break
        pos += 12 + ln


def extract_jumbf(path: str):
    """Return (carrier_description, jumbf_bytes, exclusions_as_chunks)."""
    with open(path, "rb") as fh:
        data = fh.read()
    chunks = {b"caBX", b"jumb"}
    found = []
    for typ, pos, ln in png_chunks(data) or []:
        if typ in chunks:
            found.append((pos, 12 + ln, data[pos + 8 : pos + 8 + ln]))
    if found:
        # PNG may split the store across several caBX chunks; concatenate payloads.
        blob = b"".join(p[2] for p in found)
        return "png:" + ",".join(sorted({data[p[0] + 4 : p[0] + 8].decode() for p in found})), blob, [p[:2] for p in found]

    if data[:2] == b"\xff\xd8":  # JPEG
        segs, pos = [], 2
        while pos + 4 <= len(data):
            if data[pos] != 0xFF:
                break
            marker = data[pos + 1]
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                pos += 2
                continue
            ln = struct.unpack(">H", data[pos + 2 : pos + 4])[0]
            payload = data[pos + 4 : pos + 2 + ln]
            if marker == 0xEB and payload[:2] == b"JP":
                inst = struct.unpack(">H", payload[2:4])[0]
                seq = struct.unpack(">I", payload[4:8])[0]
                segs.append((seq, inst, payload[8:], pos, 2 + ln))
            if marker == 0xDA:  # start of scan — no metadata after here
                break
            pos += 2 + ln
        if segs:
            segs.sort()
            return "jpeg:APP11", b"".join(s[2] for s in segs), [(s[3], s[4]) for s in segs]

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        pos, out = 12, []
        while pos + 8 <= len(data):
            ctyp = data[pos : pos + 4]
            ln = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
            if ctyp in (b"C2PA", b"C2P2"):
                out.append((pos, 8 + ln, data[pos + 8 : pos + 8 + ln]))
            pos += 8 + ln + (ln & 1)
        if out:
            return "webp:C2PA", b"".join(o[2] for o in out), [o[:2] for o in out]

    return "none", b"", []


# --------------------------------------------------------------------------
# Certificates
# --------------------------------------------------------------------------


def cert_summary(der: bytes) -> dict:
    info = {"subject": None, "issuer": None, "not_before": None, "not_after": None, "error": None}
    openssl = shutil.which("openssl")
    if not openssl:
        info["error"] = "openssl not available"
        return info
    try:
        out = subprocess.run(
            [openssl, "x509", "-inform", "DER", "-noout", "-subject", "-issuer", "-dates", "-nameopt", "RFC2253"],
            input=der, capture_output=True, timeout=10,
        )
        for line in out.stdout.decode("utf-8", "replace").splitlines():
            k, _, v = line.partition("=")
            k = k.strip().lower()
            if k == "subject":
                info["subject"] = v.strip()
            elif k == "issuer":
                info["issuer"] = v.strip()
            elif k.replace(" ", "").lower() == "notbefore":
                info["not_before"] = v.strip()
            elif k.replace(" ", "").lower() == "notafter":
                info["not_after"] = v.strip()
        if out.returncode != 0 and not info["subject"]:
            info["error"] = out.stderr.decode("utf-8", "replace").strip()[:200]
    except Exception as exc:  # pragma: no cover
        info["error"] = str(exc)
    return info


# --------------------------------------------------------------------------
# Interpretation
# --------------------------------------------------------------------------

AI_SOURCE_TYPES = (
    "trainedAlgorithmicMedia",
    "compositeWithTrainedAlgorithmicMedia",
    "algorithmicMedia",
)


def _actions_from(nodes: list[dict]):
    """Pull c2pa.actions / c2pa.actions.v2 assertion payloads."""
    acts = []
    for n in nodes:
        label = (n.get("label") or "").lower()
        blob = n.get("cbor") or n.get("json")
        if not isinstance(blob, dict):
            continue
        if label.startswith("c2pa.actions") or "actions" in blob and "action" in str(blob)[:400]:
            for a in blob.get("actions", []) or []:
                if isinstance(a, dict) and a.get("action"):
                    acts.append(a)
    return acts


def _hash_assertions(nodes: list[dict]):
    out = []
    for n in nodes:
        label = (n.get("label") or "").lower()
        blob = n.get("cbor")
        if isinstance(blob, dict) and ("exclusions" in blob or "hash" in blob) and (
            label.startswith("c2pa.hash") or "alg" in blob
        ):
            out.append((label or "c2pa.hash.data", blob))
    return out


def verify_hash(path: str, assertion: dict, carrier_exclusions) -> dict:
    algo = str(assertion.get("alg", "sha256")).lower().replace("-", "")
    if algo.startswith("sha384"):
        h = hashlib.sha384
    elif algo.startswith("sha512"):
        h = hashlib.sha512
    else:
        h = hashlib.sha256
    stored = assertion.get("hash")
    if not isinstance(stored, (bytes, bytearray)):
        return {"ok": None, "reason": "no stored hash", "alg": algo}
    stored = bytes(stored)

    with open(path, "rb") as fh:
        data = fh.read()
    results = []

    # 1) Honour the declared exclusions verbatim (offsets into the asset stream).
    excl = assertion.get("exclusions") or []
    if excl:
        keep, cur = [], 0
        for e in sorted((int(x.get("start", 0)), int(x.get("length", 0))) for x in excl):
            keep.append(data[cur : e[0]])
            cur = e[0] + e[1]
        keep.append(data[cur:])
        results.append(("declared-exclusions", h(b"".join(keep)).digest()))

    # 2) Fall back to dropping the carrier chunk/segments outright.
    if carrier_exclusions:
        keep, cur = [], 0
        for start, length in sorted(carrier_exclusions):
            keep.append(data[cur:start])
            cur = start + length
        keep.append(data[cur:])
        results.append(("carrier-removed", h(b"".join(keep)).digest()))

    for name, digest in results:
        if digest == stored:
            return {"ok": True, "method": name, "alg": algo, "stored": stored.hex()}

    return {
        "ok": False if results else None,
        "method": None,
        "alg": algo,
        "stored": stored.hex(),
        "tried": [{"method": n, "computed": d.hex()} for n, d in results],
        "reason": "no candidate hash matched" if results else "no exclusions resolved",
    }


def analyse(path: str) -> dict:
    carrier, blob, carrier_excl = extract_jumbf(path)
    report = {
        "file": os.path.abspath(path),
        "size": os.path.getsize(path),
        "carrier": carrier,
        "has_manifest": False,
        "claim_generator": None,
        "title": None,
        "actions": [],
        "assertions": [],
        "certificates": [],
        "hash": None,
        "verdict": "NO_C2PA",
        "verdict_reason": "no Content Credentials found in this file",
    }
    if not blob:
        return report

    nodes = walk_jumbf(blob)
    report["has_manifest"] = bool(nodes)
    if not nodes:
        report["carrier"] = "none (carrier chunk present but unparsable)"
        return report

    report["assertions"] = [n["label"] for n in nodes if n.get("label")]

    for n in nodes:
        label = (n.get("label") or "").lower()
        data = n.get("cbor") or n.get("json")
        if not isinstance(data, dict):
            continue
        if label.startswith("c2pa.claim"):
            report["claim_generator"] = data.get("claim_generator") or data.get("claim-generator")
            info = data.get("claim_generator_info")
            if isinstance(info, dict):  # spec 2.x allows a single struct
                info = [info]
            if isinstance(info, list) and info:
                gi = info[0] if isinstance(info[0], dict) else {}
                report["claim_generator_info"] = {k: v for k, v in gi.items() if isinstance(v, (str, int, float))}
                report["claim_generator"] = report["claim_generator"] or gi.get("name")
            report["instance_id"] = data.get("instanceID") or data.get("instance_id")
            if data.get("dc:title"):
                report["title"] = data["dc:title"]
    for n in nodes:
        d = n.get("cbor") or n.get("json")
        if isinstance(d, dict) and d.get("dc:title"):
            report["title"] = d["dc:title"]

    report["actions"] = [
        {
            "action": a.get("action"),
            "when": a.get("when"),
            "agent": (a.get("softwareAgent") or {}).get("name") if isinstance(a.get("softwareAgent"), dict) else a.get("softwareAgent"),
            "agent_version": (a.get("softwareAgent") or {}).get("version") if isinstance(a.get("softwareAgent"), dict) else None,
            "digitalSourceType": a.get("digitalSourceType"),
        }
        for a in _actions_from(nodes)
    ]

    hashes = _hash_assertions(nodes)
    if hashes:
        label, assertion = hashes[0]
        report["hash"] = {"label": label, **verify_hash(path, assertion, carrier_excl)}

    # Signature: COSE_Sign1 = [protected(bstr), unprotected(map), payload, signature].
    # The x5chain sits in the protected header under label 33 (int) or "x5chain".
    for n in nodes:
        label = (n.get("label") or "").lower()
        if not label.endswith("signature"):
            continue
        d = n.get("cbor")
        headers = []
        if isinstance(d, list) and len(d) >= 2:
            if isinstance(d[0], (bytes, bytearray)):
                try:
                    headers.append(cbor_decode(bytes(d[0]))[0])
                except Exception:
                    pass
            headers.append(d[1])
        elif isinstance(d, dict):
            headers.append(d)
        for hdr in headers:
            if not isinstance(hdr, dict):
                continue
            chain = hdr.get(33) if 33 in hdr else hdr.get("x5chain")
            if isinstance(chain, (bytes, list)):
                ders = [chain] if isinstance(chain, bytes) else [c for c in chain if isinstance(c, bytes)]
                if ders:
                    report["certificates"] = [cert_summary(x) for x in ders]
                    break
        if report["certificates"]:
            break

    # --- verdict -----------------------------------------------------------
    src_types = [a.get("digitalSourceType") or "" for a in report["actions"]]
    names = [str(a.get("action") or "").split("/")[-1].split(".")[-1] for a in report["actions"]]
    ai_hit = [s for s in src_types if any(t.lower() in s.lower() for t in AI_SOURCE_TYPES)]
    edited = [n for n in names if n in ("edited", "opened", "filtered", "repackaged")]

    if ai_hit:
        report["verdict"] = "AI_GENERATED"
        report["verdict_reason"] = f"signer declares digitalSourceType={ai_hit[0]}"
    elif edited:
        report["verdict"] = "EDITED"
        report["verdict_reason"] = f"signed edit history includes: {', '.join(sorted(set(edited)))}"
    elif names:
        report["verdict"] = "CAPTURED"
        report["verdict_reason"] = f"signed action history only: {', '.join(sorted(set(names)))}"

    if report["hash"] and report["hash"].get("ok") is False:
        report["verdict"] = "INVALID_HASH"
        report["verdict_reason"] = "content changed after signing — pixels do not match the signed hash"

    return report


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def render(rep: dict) -> str:
    L = []
    L.append(f"# C2PA Content Credentials — {os.path.basename(rep['file'])}")
    L.append(f"**File:** {rep['file']}  ({rep['size']:,} bytes)")
    L.append(f"**Manifest carrier:** {rep['carrier']}")

    v = rep["verdict"]
    if v == "NO_C2PA":
        L.append("")
        L.append("**No C2PA manifest.** Provenance is unverified — this says nothing about")
        L.append("whether the image is real or synthetic, only that it carries no signed claim.")
        return "\n".join(L)

    L.append(f"**Verdict:** `{v}` — {rep['verdict_reason']}")
    if rep.get("claim_generator") or rep.get("claim_generator_info"):
        L.append(f"**Claim generator:** {rep.get('claim_generator')}")
        info = rep.get("claim_generator_info") or {}
        if info:
            L.append(f"**Generator detail:** {json.dumps(info, ensure_ascii=False)}")
    if rep.get("title"):
        L.append(f"**Title:** {rep['title']}")

    if rep["actions"]:
        L.append("")
        L.append("## Action history")
        L.append("| # | action | when | agent | digitalSourceType |")
        L.append("|---|---|---|---|---|")
        for i, a in enumerate(rep["actions"], 1):
            st = (a.get("digitalSourceType") or "").rsplit("/", 1)[-1] or "—"
            L.append(f"| {i} | {a.get('action')} | {a.get('when') or '—'} | {a.get('agent') or '—'} | {st} |")

    if rep.get("hash"):
        h = rep["hash"]
        L.append("")
        L.append("## Hard binding")
        L.append(f"- assertion: `{h.get('label')}`  alg: `{h.get('alg')}`")
        L.append(f"- stored sha: `{h.get('stored')}`")
        if h.get("ok") is True:
            L.append(f"- **pixel hash VERIFIED** (method: {h.get('method')}) — bytes match what the signer signed")
        elif h.get("ok") is False:
            L.append("- **pixel hash MISMATCH** — the image was modified after signing")
            for t in h.get("tried", []):
                L.append(f"  - {t['method']}: `{t['computed']}`")
        else:
            L.append(f"- not verified ({h.get('reason')})")

    if rep["certificates"]:
        L.append("")
        L.append("## Signing chain")
        for i, c in enumerate(rep["certificates"]):
            if i == 0:
                role = "leaf"
            else:
                self_signed = c.get("subject") and c.get("subject") == c.get("issuer")
                role = "root" if self_signed else "intermediate"
            L.append(f"- **{role}** {c.get('subject') or c.get('error')}")
            L.append(f"  - issuer: {c.get('issuer')}")
            L.append(f"  - valid: {c.get('not_before')} → {c.get('not_after')}")

    if rep["assertions"]:
        L.append("")
        L.append("## Assertions")
        L.append(", ".join(f"`{a}`" for a in rep["assertions"]))
    return "\n".join(L)


# --------------------------------------------------------------------------
# MCP server mode
