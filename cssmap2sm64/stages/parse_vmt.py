import json
import re
from pathlib import Path


def _parse_vmt(text):
    text = re.sub(r"//[^\n]*", "", text)
    m = re.search(r"\{(.*)\}", text, re.DOTALL)
    if not m:
        return {}
    body = m.group(1)
    pairs = re.findall(r'"([^"]+)"\s+"([^"]*)"', body, re.IGNORECASE)
    result = {}
    for k, v in pairs:
        result[k.lower()] = v
    return result


def _alpha_mode(kv):
    if kv.get("$alphatest", "0") not in ("0", ""):
        return "clip"
    if kv.get("$translucent", "0") not in ("0", ""):
        return "blend"
    if kv.get("$additive", "0") not in ("0", ""):
        return "blend"
    return "opaque"


def _material_key(vmt_path, textures_dir):
    rel = Path(vmt_path).relative_to(textures_dir)
    parts = rel.parts
    try:
        mat_idx = next(i for i, p in enumerate(parts) if p.lower() == "materials")
        sub = parts[mat_idx + 1:]
    except StopIteration:
        sub = parts
    key = "/".join(sub)
    if key.lower().endswith(".vmt"):
        key = key[:-4]
    return key.lower()


def parse_vmts(vmt_paths, textures_dir):
    textures_dir = Path(textures_dir)
    materials = {}
    for vmt_path in vmt_paths:
        try:
            text = Path(vmt_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        kv = _parse_vmt(text)
        key = _material_key(vmt_path, textures_dir)
        basetexture = kv.get("$basetexture") or None
        if basetexture:
            basetexture = basetexture.replace("\\", "/").lower()
        materials[key] = {
            "basetexture": basetexture,
            "alpha_mode": _alpha_mode(kv),
        }
    out = textures_dir / "materials.json"
    out.write_text(json.dumps(materials, indent=2), encoding="utf-8")
    return materials
