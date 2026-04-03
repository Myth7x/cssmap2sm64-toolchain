import json
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from .cli import build_parser
from .stages import unpack_pak, blend_run, f64_to_native, parse_vmt

_BG_SEGMENT = {
    "OCEAN_SKY": "water",
    "FLAMING_SKY": "bitfs",
    "UNDERWATER_CITY": "wdw",
    "BELOW_CLOUDS": "cloud_floor",
    "SNOW_MOUNTAINS": "ccm",
    "DESERT": "ssl",
    "HAUNTED": "bbh",
    "GREEN_SKY": "bidw",
    "ABOVE_CLOUDS": "clouds",
    "PURPLE_SKY": "bits",
}

_SKY_HINTS = [
    ("dust", "DESERT"), ("sand", "DESERT"), ("desert", "DESERT"),
    ("snow", "SNOW_MOUNTAINS"), ("ice", "SNOW_MOUNTAINS"), ("ccm", "SNOW_MOUNTAINS"),
    ("night", "HAUNTED"), ("haunted", "HAUNTED"), ("bbh", "HAUNTED"),
    ("ocean", "OCEAN_SKY"), ("water", "OCEAN_SKY"), ("tides", "OCEAN_SKY"),
    ("underwater", "UNDERWATER_CITY"),
    ("fire", "FLAMING_SKY"), ("lava", "FLAMING_SKY"), ("bitfs", "FLAMING_SKY"),
    ("purple", "PURPLE_SKY"), ("lunacy", "PURPLE_SKY"),
    ("green", "GREEN_SKY"),
    ("cloud", "ABOVE_CLOUDS"), ("sky", "ABOVE_CLOUDS"),
]


def _read_skyname(bsp_path: str) -> str:
    with open(bsp_path, "rb") as f:
        f.read(8)
        lump_table = f.read(64 * 16)
    fileofs, filelen = struct.unpack_from("<ii", lump_table, 0 * 16)
    with open(bsp_path, "rb") as f:
        f.seek(fileofs)
        entities = f.read(filelen).decode("utf-8", errors="replace")
    for block in re.split(r'(?<=\})\s*(?=\{)', entities):
        if '"classname" "worldspawn"' in block:
            m = re.search(r'"skyname"\s+"([^"]+)"', block)
            if m:
                return m.group(1).lower()
    return ""


def _skyname_to_background(skyname: str, sky_map: dict, default: str) -> str:
    if skyname in sky_map:
        return sky_map[skyname]
    for hint, bg in _SKY_HINTS:
        if hint in skyname:
            return bg
    return default


_ROOT = Path(__file__).parent.parent
_VENDOR = _ROOT / "vendor"
_BUILD = _ROOT / "build"
_BIN_SUFFIX = ".exe" if sys.platform == "win32" else ""


def _require_binary(name):
    p = _BUILD / (name + _BIN_SUFFIX)
    if not p.exists():
        sys.exit(f"Binary not found: {p}\nRun: cmake -B build && cmake --build build")
    return p


def main():
    args = build_parser().parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        sys.exit(
            f"Config not found: {config_path}\n"
            "Run: node src/config-gen/index.js"
        )

    with open(config_path) as f:
        cfg = json.load(f)

    cfg.setdefault("scale_factor", 1.0)
    cfg.setdefault("blender_to_sm64_scale", 300)
    cfg.setdefault("collision_divisor", 150)
    cfg.setdefault("area_id", 1)
    cfg.setdefault("is_custom_level", True)
    cfg.setdefault("texture_resolution_limit", 512)
    cfg.setdefault("default_background", "ABOVE_CLOUDS")
    cfg.setdefault("sky_map", {})
    cfg.setdefault("decimate_ratio", 1.0)

    bsp = Path(args.bsp).resolve()
    if not bsp.exists():
        sys.exit(f"BSP file not found: {bsp}")

    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)

    bsp2obj_bin = _require_binary("bsp2obj")
    vtf2png_bin = _require_binary("vtf2png")

    if not args.no_blend:
        blender_path = Path(cfg.get("blender_path", ""))
        if not blender_path.exists():
            sys.exit(
                f"Blender not found: {blender_path}\n"
                "Set blender_path in pipeline.json or use --no-blend to skip this stage."
            )
    else:
        blender_path = None

    obj_path    = out / (bsp.stem + ".obj")
    spawn_file  = out / (bsp.stem + ".spawn")
    tex_dir     = out / "textures"
    if tex_dir.exists():
        shutil.rmtree(tex_dir)
    tex_dir.mkdir()

    print("[1/4] Converting BSP to OBJ...")
    bsp2obj_cmd = [
        str(bsp2obj_bin), str(bsp), str(obj_path),
        "--scale", str(cfg["scale_factor"]),
        "--spawn-out", str(spawn_file),
    ]
    if args.keep_tools:
        bsp2obj_cmd.append("--keep-tools")
    subprocess.run(bsp2obj_cmd, check=True)

    skyname = _read_skyname(str(bsp))
    background = _skyname_to_background(skyname, cfg["sky_map"], cfg["default_background"])
    skybox_bin = _BG_SEGMENT.get(background, "water")
    print(f"  Sky: {skyname!r} -> background={background} skybox-bin={skybox_bin}")

    spawn_bl  = (0.0, 0.0, 0.0)
    sm64_spawn = (0, 0, 0)
    if spawn_file.exists():
        raw = spawn_file.read_text().strip()
        if raw and raw != "none":
            parts = raw.split()
            if len(parts) == 3:
                sx, sy, sz = float(parts[0]), float(parts[1]), float(parts[2])
                scale = cfg["scale_factor"]
                spawn_bl = (sx * scale, sy * scale, sz * scale)
                net = cfg["blender_to_sm64_scale"] / cfg["collision_divisor"]
                sm64_spawn = (
                    round(sx * scale * net),
                    round(sz * scale * net),
                    round(-sy * scale * net),
                )
                print(f"  Spawn source=({sx},{sy},{sz}) -> blender={spawn_bl} -> sm64={sm64_spawn}")
        else:
            print("  [warn] No spawn entity found, using origin (0, 0, 0)")

    print("[2/4] Extracting PAK textures...")
    vtf_files, vmt_files = unpack_pak.extract_pak(str(bsp), str(tex_dir))
    _res = cfg["texture_resolution_limit"]
    max_size = "0" if _res == "auto" else str(int(_res))
    if vtf_files:
        list_file = out / "vtf_list.txt"
        with open(list_file, "w") as lf:
            lf.write(max_size + "\n")
            for vtf in vtf_files:
                lf.write(vtf + "\n")
                lf.write(str(Path(vtf).with_suffix(".png")) + "\n")
        subprocess.run([str(vtf2png_bin), "@", str(list_file)], check=True)
    materials_json = None
    if vmt_files:
        print(f"  Parsing {len(vmt_files)} VMT material files...")
        parse_vmt.parse_vmts(vmt_files, tex_dir)
        materials_json = tex_dir / "materials.json"

    if args.no_blend:
        print(f"[3/5] Skipped (--no-blend). OBJ: {obj_path}")
        print(f"Done. Output in {out}/")
        return

    print("[3/4] Exporting to SM64 via Blender/Fast64...")
    sm64_out = out / "sm64_level"
    blend_run.run(
        blender=str(blender_path),
        obj_path=str(obj_path),
        textures_dir=str(tex_dir),
        output_dir=str(sm64_out),
        level_name=cfg["level_name"],
        area_id=cfg["area_id"],
        scale=cfg["blender_to_sm64_scale"],
        spawn=spawn_bl,
        materials_json=materials_json,
        background=background,
        decimate_ratio=cfg["decimate_ratio"],
    )
    level_name = cfg["level_name"]
    print("[4/5] Converting Fast64 output to native sm64-port format...")
    native_out = out / "native_level" / level_name
    f64_to_native.convert(
        sm64_out / level_name,
        native_out,
        level_name,
        collision_divisor=cfg["collision_divisor"],
        sm64_spawn=sm64_spawn,
        skybox_bin=skybox_bin,
    )

    sm64_port_path = cfg.get("sm64_port_path", "")
    if sm64_port_path:
        sm64_port = Path(sm64_port_path)
        dest = sm64_port / "levels" / level_name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(native_out, dest)
        print(f"  -> deployed to {dest}")
    else:
        print(f"Done. Native level in {native_out}/")
    print(f"  -> copy to sm64-port/levels/{level_name}/")


if __name__ == "__main__":
    main()
