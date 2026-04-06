import json
import lzma
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from .cli import build_parser
from .stages import unpack_pak, blend_run, f64_to_native, parse_vmt, extract_vpk, read_bsp_env, sky_cubemap

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


def _decompress_valve_lzma(lump_bytes: bytes) -> bytes:
    actual_size = struct.unpack_from("<I", lump_bytes, 4)[0]
    lzma_size   = struct.unpack_from("<I", lump_bytes, 8)[0]
    props       = lump_bytes[12:17]
    payload     = lump_bytes[17 : 17 + lzma_size]
    lzma_alone  = props + struct.pack("<q", actual_size) + payload
    return lzma.decompress(lzma_alone, format=lzma.FORMAT_ALONE)


_LZMA_DECOMPRESS_LUMPS = {0, 1, 2, 3, 5, 6, 7, 12, 13, 14, 18, 19, 26, 33, 35, 40, 43, 44}


def _normalize_bsp(src: Path, dst: Path) -> bool:
    data = src.read_bytes()
    HDR = 8 + 64 * 16 + 4
    if len(data) < HDR:
        return False
    lumps = []
    for i in range(64):
        o = 8 + i * 16
        fileofs, filelen, lver = struct.unpack_from("<iii", data, o)
        fourcc = data[o + 12 : o + 16]
        lumps.append((fileofs, filelen, lver, fourcc))
    map_rev = struct.unpack_from("<i", data, 8 + 64 * 16)[0]
    has_lzma = any(
        i in _LZMA_DECOMPRESS_LUMPS
        and 0 < fileofs and 0 < filelen and fileofs + filelen <= len(data)
        and data[fileofs : fileofs + 4] == b"LZMA"
        for i, (fileofs, filelen, _, _) in enumerate(lumps)
    )
    if not has_lzma:
        return False

    new_data: list[bytes] = []
    new_lumps: list[tuple] = []
    pos = HDR
    for i, (fileofs, filelen, lver, fourcc) in enumerate(lumps):
        if fileofs <= 0 or filelen <= 0 or fileofs + filelen > len(data):
            new_lumps.append((0, 0, lver, fourcc))
            new_data.append(b"")
            continue
        chunk = data[fileofs : fileofs + filelen]
        if i in _LZMA_DECOMPRESS_LUMPS and chunk[:4] == b"LZMA" and len(chunk) >= 17:
            try:
                chunk = _decompress_valve_lzma(chunk)
            except Exception:
                pass
        if i == 35 and len(chunk) >= 4:
            delta = pos - fileofs
            chunk = bytearray(chunk)
            gl_lump_count = struct.unpack_from("<i", chunk, 0)[0]
            if 0 < gl_lump_count <= 64:
                for li in range(gl_lump_count):
                    entry_off = 4 + li * 16
                    if entry_off + 16 <= len(chunk):
                        gl_ofs = struct.unpack_from("<i", chunk, entry_off + 8)[0]
                        struct.pack_into("<i", chunk, entry_off + 8, gl_ofs + delta)
            chunk = bytes(chunk)
        pad = (-len(chunk)) & 3
        new_lumps.append((pos, len(chunk), lver, fourcc))
        new_data.append(chunk + bytes(pad))
        pos += len(chunk) + pad

    hdr = bytearray(HDR)
    struct.pack_into("<ii", hdr, 0, *struct.unpack_from("<ii", data, 0))
    for i, (fileofs, filelen, lver, fourcc) in enumerate(new_lumps):
        o = 8 + i * 16
        struct.pack_into("<iii", hdr, o, fileofs, filelen, lver)
        hdr[o + 12 : o + 16] = fourcc
    struct.pack_into("<i", hdr, 8 + 64 * 16, map_rev)
    dst.write_bytes(bytes(hdr) + b"".join(new_data))
    return True


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
    cfg.setdefault("point_light_radius_mult", 5.0)
    cfg.setdefault("point_light_intensity_mult", 1.0)
    cfg.setdefault("area_id", 1)
    cfg.setdefault("is_custom_level", True)
    cfg.setdefault("texture_resolution_limit", 512)
    cfg.setdefault("default_background", "ABOVE_CLOUDS")
    cfg.setdefault("sky_map", {})
    cfg.setdefault("decimate_ratio", 1.0)
    cfg.setdefault("sky_radius", 0.0)
    cfg.setdefault("max_visual_polys", 0)

    bsp = Path(args.bsp).resolve()
    if not bsp.exists():
        sys.exit(f"BSP file not found: {bsp}")

    derived_level_name = re.sub(r'[^a-z0-9_]', '_', bsp.stem.lower())
    if cfg.get("level_name") != derived_level_name:
        cfg["level_name"] = derived_level_name
        with open(config_path, "w") as _cfg_f:
            json.dump(cfg, _cfg_f, indent=2)
        print(f"  pipeline.json: level_name updated to {derived_level_name!r}")

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

    obj_path       = out / (bsp.stem + ".obj")
    spawn_file     = out / (bsp.stem + ".spawn")
    props_file     = out / (bsp.stem + ".props.json")
    triggers_file  = out / (bsp.stem + ".triggers.json")
    sky_obj_path   = out / (bsp.stem + ".sky.obj")
    sky_cam_path   = out / (bsp.stem + ".sky_camera.json")
    moving_brushes_dir = out / "moving_brushes"
    tex_dir     = out / "textures"
    if tex_dir.exists():
        shutil.rmtree(tex_dir)
    tex_dir.mkdir()

    norm_bsp = out / (bsp.stem + "_normalized.bsp")
    bsp_for_tool = norm_bsp if _normalize_bsp(bsp, norm_bsp) else bsp
    if bsp_for_tool == norm_bsp:
        print(f"  Decompressed LZMA lumps -> {norm_bsp.name}")

    print("[1/4] Converting BSP to OBJ...")
    bsp2obj_cmd = [
        str(bsp2obj_bin), str(bsp_for_tool), str(obj_path),
        "--scale", str(cfg["scale_factor"]),
        "--spawn-out", str(spawn_file),
        "--props-out", str(props_file),
        "--skybox-out", str(sky_obj_path),
        "--sky-camera-out", str(sky_cam_path),
        "--sky-radius", str(cfg["sky_radius"]),
        "--triggers-out", str(triggers_file),
        "--moving-brushes-dir", str(moving_brushes_dir),
    ]
    if args.keep_tools:
        bsp2obj_cmd.append("--keep-tools")
    subprocess.run(bsp2obj_cmd, check=True)

    skyname = _read_skyname(str(bsp_for_tool))
    background = _skyname_to_background(skyname, cfg["sky_map"], cfg["default_background"])
    skybox_bin = _BG_SEGMENT.get(background, "water")
    print(f"  Sky: {skyname!r} -> background={background} skybox-bin={skybox_bin}")

    env_data = read_bsp_env.read_env(str(bsp_for_tool))
    env_json_path = None
    if env_data:
        import json as _env_json_mod
        env_json_path = out / (bsp.stem + ".env.json")
        env_json_path.write_text(_env_json_mod.dumps(env_data, indent=2), encoding="utf-8")
        sc, ac = env_data["sun_color"], env_data["ambient_color"]
        print(
            f"  Env: sun=({sc[0]:.2f},{sc[1]:.2f},{sc[2]:.2f})"
            f" amb=({ac[0]:.2f},{ac[1]:.2f},{ac[2]:.2f})"
            f" pitch={env_data['sun_pitch']:.0f}° yaw={env_data['sun_yaw']:.0f}°"
        )
    else:
        print("  Env: no light_environment found, using default lighting")

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
    vtf_files, vmt_files = unpack_pak.extract_pak(str(bsp_for_tool), str(tex_dir))

    if bsp_for_tool != bsp:
        norm_bsp.unlink(missing_ok=True)

    game_path = cfg.get("game_path", "")
    if game_path and Path(game_path).is_dir():
        mat_slugs = set()
        for _slug_obj in [obj_path, sky_obj_path]:
            if _slug_obj.exists():
                for line in _slug_obj.read_text(errors="replace").splitlines():
                    if line.startswith("usemtl "):
                        mat_slugs.add(line[7:].strip().lower())
        mat_dir = str(tex_dir / "materials")
        already = set()
        for p in vtf_files:
            try:
                rel = os.path.relpath(p, mat_dir).replace("\\", "/")
                already.add(rel.rsplit(".", 1)[0].lower().replace("/", "_"))
            except ValueError:
                pass
        needed = {s for s in mat_slugs if s not in already}
        needed.update(parse_vmt.collect_base_slugs(str(tex_dir)) - already)
        if needed:
            extra_vtfs = extract_vpk.extract_materials_from_vpk(game_path, needed, str(tex_dir))
            vtf_files = vtf_files + extra_vtfs

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
    mat_dir_path = tex_dir / "materials"
    all_vmts = list(mat_dir_path.rglob("*.vmt")) if mat_dir_path.is_dir() else []
    if all_vmts:
        print(f"  Parsing {len(all_vmts)} VMT material files...")
        parse_vmt.parse_vmts([str(p) for p in all_vmts], tex_dir)
        materials_json = tex_dir / "materials.json"

    # Compute SM64 sky origin for cubemap centering
    sm64_sky_origin = (0, 0, 0)
    if sky_cam_path.exists():
        import json as _scj
        _sc = _scj.loads(sky_cam_path.read_text())
        _ox, _oy, _oz = _sc["origin"]
        _sky_scale = _sc["scale"]
        _net = cfg["blender_to_sm64_scale"] / cfg["collision_divisor"]
        sm64_sky_origin = (
            round(_ox * cfg["scale_factor"] * _net * _sky_scale),
            round(_oz * cfg["scale_factor"] * _net * _sky_scale),
            round(-_oy * cfg["scale_factor"] * _net * _sky_scale),
        )
        print(f"  Sky SM64 origin: {sm64_sky_origin}")

    # Extract sky cubemap faces and generate a cubemap box OBJ
    sky_cube_obj_path = out / (bsp.stem + ".sky_cube.obj")
    if game_path and Path(game_path).is_dir() and skyname:
        print("[2b/4] Extracting skybox cubemap faces...")
        cube_pngs = sky_cubemap.extract_sky_faces(
            game_path, skyname, str(tex_dir), str(vtf2png_bin)
        )
        if cube_pngs:
            sky_cubemap.generate_cubemap_obj(
                str(sky_cube_obj_path), skyname,
                tex_dir=str(tex_dir), sm64_origin=sm64_sky_origin
            )
            print(f"  Cubemap box: {len(cube_pngs)} faces -> {sky_cube_obj_path.name}")
        else:
            sky_cube_obj_path = None
            print(f"  Cubemap: no faces found for skyname={skyname!r}, skipping")
    else:
        sky_cube_obj_path = None

    # --- Collision: generate directly from OBJ (bypasses Fast64 for collision) ---
    print("[2c/4] Generating collision from OBJ (direct bypass)...")
    import time as _col_time
    _col_t0 = _col_time.monotonic()
    _net = cfg["blender_to_sm64_scale"] / cfg["collision_divisor"]
    _pre_collision = out / (bsp.stem + ".collision.inc.c")
    f64_to_native.generate_collision_from_obj(obj_path, _pre_collision, cfg["level_name"], _net)
    print(f"  Collision generated in {_col_time.monotonic() - _col_t0:.1f}s")

    if args.no_blend or args.collision_only:
        level_name = cfg["level_name"]
        sm64_port_path = cfg.get("sm64_port_path", "")
        if sm64_port_path:
            sm64_port = Path(sm64_port_path)
            dest = sm64_port / "levels" / level_name
            col_dest = dest / "areas" / "1" / "collision.inc.c"
            if col_dest.exists() and _pre_collision.exists():
                shutil.copy2(_pre_collision, col_dest)
                print(f"  -> collision.inc.c deployed to {col_dest}")
                if triggers_file.exists():
                    entities_dest = dest / "entities.inc.c"
                    if entities_dest.exists():
                        import json as _ejson
                        _triggers_data = _ejson.loads(triggers_file.read_text(encoding="utf-8"))
                        _net = cfg["blender_to_sm64_scale"] / cfg["collision_divisor"]
                        f64_to_native._write_entities_inc(
                            entities_dest,
                            level_name,
                            _triggers_data,
                            cfg["scale_factor"],
                            _net,
                            sm64_spawn,
                        )
                        print(f"  -> entities.inc.c deployed to {entities_dest}")
            if moving_brushes_dir.exists() and dest.exists():
                import json as _mjson
                _triggers_data = _mjson.loads(triggers_file.read_text(encoding="utf-8")) if triggers_file.exists() else []
                _net2 = cfg["blender_to_sm64_scale"] / cfg["collision_divisor"]
                f64_to_native.convert_moving_platforms(
                    _triggers_data,
                    moving_brushes_dir,
                    dest,
                    level_name,
                    cfg["scale_factor"],
                    _net2,
                    dest / "script.c",
                    dest / "leveldata.c",
                    dest / "header.h",
                )
                print("  -> moving platforms generated")
            elif not col_dest.exists():
                print(f"  [warn] {dest} not yet deployed — run full pipeline first, then use --collision-only")
        print(f"[3/5] Skipped ({'--collision-only' if args.collision_only else '--no-blend'}). OBJ: {obj_path}")
        print(f"Done. Output in {out}/")
        return

    # --- Auto-decimate: count OBJ faces, limit visual polys sent to Fast64 ---
    #_max_vis = cfg["max_visual_polys"]
    #_decimate_ratio = cfg["decimate_ratio"]
    #if _max_vis > 0 and obj_path.exists():
    #    _face_count = sum(1 for _ln in open(obj_path, encoding="utf-8", errors="replace") if _ln.startswith("f "))
    #    print(f"  OBJ faces: {_face_count}")
    #    if _face_count > _max_vis:
    #        _decimate_ratio = min(_decimate_ratio, _max_vis / _face_count)
    #        print(f"  Auto-decimate: ratio={_decimate_ratio:.3f} (max_visual_polys={_max_vis})")

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
        decimate_ratio=1.0,#_decimate_ratio,
        props_json=props_file if props_file.exists() else None,
        bsp_scale=cfg["scale_factor"],
        env_json=env_json_path,
        sky_obj=str(sky_obj_path) if sky_obj_path.exists() else None,
        sky_camera_json=str(sky_cam_path) if sky_cam_path.exists() else None,
        sky_cube_obj=str(sky_cube_obj_path) if sky_cube_obj_path and sky_cube_obj_path.exists() else None,
        triggers_json=triggers_file if triggers_file.exists() else None,
    )
    level_name = cfg["level_name"]
    print("[4/5] Converting Fast64 output to native sm64-port format...")
    native_out = out / "native_level" / level_name
    sky_camera_data = None
    if sky_cam_path.exists():
        with open(sky_cam_path) as _scf:
            sky_camera_data = json.load(_scf)
    f64_to_native.convert(
        sm64_out / level_name,
        native_out,
        level_name,
        collision_divisor=cfg["collision_divisor"],
        sm64_spawn=sm64_spawn,
        skybox_bin=skybox_bin,
        env_json=env_json_path,
        triggers_json=triggers_file if triggers_file.exists() else None,
        scale_factor=cfg["scale_factor"],
        blender_to_sm64_scale=cfg["blender_to_sm64_scale"],
        point_light_radius_mult=cfg["point_light_radius_mult"],
        point_light_intensity_mult=cfg["point_light_intensity_mult"],
    )
    if _pre_collision.exists():
        import shutil as _colshutil
        _colshutil.copy2(_pre_collision, native_out / "areas" / "1" / "collision.inc.c")
        print("  -> collision.inc.c replaced with direct-generated version")
    if triggers_file.exists() and moving_brushes_dir.exists():
        _net2 = cfg["blender_to_sm64_scale"] / cfg["collision_divisor"]
        _triggers_data = json.loads(triggers_file.read_text(encoding="utf-8"))
        f64_to_native.convert_moving_platforms(
            _triggers_data,
            moving_brushes_dir,
            native_out,
            level_name,
            cfg["scale_factor"],
            _net2,
            native_out / "script.c",
            native_out / "leveldata.c",
            native_out / "header.h",
        )
        print("  -> moving platforms generated")
    if sky_obj_path.exists() and sky_camera_data is not None:
        print("[4b/5] Converting sky Fast64 output to native format...")
        sky_level_name = level_name + "_sky"
        f64_to_native.convert_sky(
            sm64_out / sky_level_name,
            native_out / "sky",
            level_name,
            sky_camera_data["origin"],
            sky_camera_data["scale"],
            scale_factor=cfg["scale_factor"],
            blender_to_sm64_scale=cfg["blender_to_sm64_scale"],
            collision_divisor=cfg["collision_divisor"],
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
