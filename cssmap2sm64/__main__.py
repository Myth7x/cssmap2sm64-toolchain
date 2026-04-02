import json
import subprocess
import sys
from pathlib import Path

from .cli import build_parser
from .stages import decompile, unpack_pak, blend_run, find_spawn, f64_to_native

_ROOT = Path(__file__).parent.parent
_VENDOR = _ROOT / "vendor"
_BUILD = _ROOT / "build"
_BIN_SUFFIX = ".exe" if sys.platform == "win32" else ""


def _require_binary(name):
    p = _BUILD / (name + _BIN_SUFFIX)
    if not p.exists():
        sys.exit(f"Binary not found: {p}\nRun: cmake -B build && cmake --build build")
    return p


def _check_java(java_path):
    try:
        subprocess.run([java_path, "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        sys.exit(f"java not found or not executable: {java_path}")


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
    cfg.setdefault("area_id", 1)
    cfg.setdefault("is_custom_level", True)
    cfg.setdefault("texture_resolution_limit", 512)
    cfg.setdefault("java_path", "java")

    bsp = Path(args.bsp).resolve()
    if not bsp.exists():
        sys.exit(f"BSP file not found: {bsp}")

    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)

    vmf2obj_bin = _require_binary("vmf2obj")
    vtf2png_bin = _require_binary("vtf2png")

    _check_java(cfg["java_path"])

    if not args.no_blend:
        blender_path = Path(cfg.get("blender_path", ""))
        if not blender_path.exists():
            sys.exit(
                f"Blender not found: {blender_path}\n"
                "Set blender_path in pipeline.json or use --no-blend to skip this stage."
            )
    else:
        blender_path = None

    bspsource_jar = _VENDOR / "bspsource.jar"
    if not bspsource_jar.exists():
        sys.exit(f"bspsource.jar not found in {_VENDOR}")

    vmf_path = out / (bsp.stem + ".vmf")
    obj_path = out / (bsp.stem + ".obj")
    tex_dir  = out / "textures"
    tex_dir.mkdir(exist_ok=True)

    print("[1/4] Decompiling BSP...")
    decompile.run(cfg["java_path"], str(bspsource_jar), str(bsp), str(vmf_path))

    print("  Extracting spawn point...")
    spawn_raw = find_spawn.find_spawn(str(vmf_path))
    if spawn_raw is None:
        print("  [warn] No spawn entity found, using origin (0, 0, 0)")
        spawn_bl = (0.0, 0.0, 0.0)
    else:
        sx, sy, sz = spawn_raw
        scale = cfg["scale_factor"]
        spawn_bl = (sx * scale, sz * scale, sy * scale)
        print(f"  Spawn source={spawn_raw} -> blender={spawn_bl}")

    print("[2/4] Extracting PAK textures...")
    vtf_files = unpack_pak.extract_pak(str(bsp), str(tex_dir))
    for vtf in vtf_files:
        png = str(Path(vtf).with_suffix(".png"))
        subprocess.run([str(vtf2png_bin), vtf, png], check=True)

    print("[3/4] Converting VMF to OBJ...")
    vmf2obj_cmd = [
        str(vmf2obj_bin), str(vmf_path), str(obj_path),
        "--scale", str(cfg["scale_factor"]),
    ]
    if args.keep_tools:
        vmf2obj_cmd.append("--keep-tools")
    subprocess.run(vmf2obj_cmd, check=True)

    if args.no_blend:
        print(f"[4/5] Skipped (--no-blend). OBJ: {obj_path}")
        print(f"Done. Output in {out}/")
    else:
        print("[4/5] Exporting to SM64 via Blender/Fast64...")
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
        )
        level_name = cfg["level_name"]
        print("[5/5] Converting Fast64 output to native sm64-port format...")
        native_out = out / "native_level" / level_name
        f64_to_native.convert(sm64_out / level_name, native_out, level_name)
        print(f"Done. Native level in {native_out}/")
        print(f"  -> copy to sm64-port/levels/{level_name}/")


if __name__ == "__main__":
    main()
