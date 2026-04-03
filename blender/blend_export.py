import argparse
import json
import os
import sys
from pathlib import Path


def find_png(textures_dir, material_name):
    tex_dir = Path(textures_dir)

    direct = tex_dir / "materials" / (material_name.lower() + ".png")
    if direct.exists():
        return str(direct)

    flat_name = material_name.lower().replace("/", "_") + ".png"
    flat = tex_dir / flat_name
    if flat.exists():
        return str(flat)

    stem = Path(material_name).name.lower() + ".png"
    for root, _, files in os.walk(str(tex_dir)):
        for fname in files:
            if fname.lower() == stem:
                return str(Path(root) / fname)

    return None


def find_png_for_material(textures_dir, material_name, mat_props, underscore_to_slash=None):
    key = material_name.lower().replace("\\", "/")
    props = mat_props.get(key)
    slash_key = None
    if props is None and underscore_to_slash is not None:
        slash_key = underscore_to_slash.get(key)
        if slash_key:
            props = mat_props.get(slash_key)
    if props:
        bt = props.get("basetexture") or slash_key or key.replace("_", "/")
        candidate = find_png(textures_dir, bt)
        if candidate:
            return candidate
    return find_png(textures_dir, material_name)


def apply_alpha_mode(mat, alpha_mode):
    rdp = mat.f3d_mat.rdp_settings
    if alpha_mode == "clip":
        rdp.set_rendermode = True
        rdp.rendermode_preset_cycle_1 = "G_RM_AA_ZB_TEX_EDGE"
        rdp.rendermode_preset_cycle_2 = "G_RM_AA_ZB_TEX_EDGE2"
        mat.f3d_mat.draw_layer.sm64 = "4"
    elif alpha_mode == "blend":
        rdp.set_rendermode = True
        rdp.rendermode_preset_cycle_1 = "G_RM_AA_ZB_XLU_SURF"
        rdp.rendermode_preset_cycle_2 = "G_RM_AA_ZB_XLU_SURF2"
        mat.f3d_mat.draw_layer.sm64 = "5"


def main():
    import bpy

    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser()
    parser.add_argument("--obj", required=True)
    parser.add_argument("--textures", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--level-name", required=True)
    parser.add_argument("--area-id", type=int, default=1)
    parser.add_argument("--scale", type=float, default=300.0)
    parser.add_argument("--spawn", default="0,0,0")
    parser.add_argument("--materials-json", default=None)
    parser.add_argument("--background-sky", default="ABOVE_CLOUDS")
    args = parser.parse_args(argv)

    mat_props = {}
    underscore_to_slash = {}
    if args.materials_json and Path(args.materials_json).exists():
        with open(args.materials_json, encoding="utf-8") as f:
            mat_props = json.load(f)
        for k in mat_props:
            underscore_to_slash[k.replace("/", "_")] = k

    print("== blend_export: start", flush=True)

    from fast64.fast64_internal.f3d.f3d_material import createF3DMat

    scene = bpy.context.scene
    scene.f3d_type = "F3DEX2/LX2"

    scene.display_settings.display_device = "sRGB"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0

    print("== blend_export: color management set", flush=True)

    bpy.ops.object.select_all(action="DESELECT")
    print("== blend_export: importing OBJ", flush=True)

    blender_ver = bpy.app.version
    if blender_ver >= (3, 3, 0):
        bpy.ops.wm.obj_import(filepath=args.obj)
    else:
        bpy.ops.import_scene.obj(filepath=args.obj)

    imported = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    print(f"== blend_export: imported {len(imported)} mesh objects", flush=True)

    import time as _time

    _all_mat_names = []
    _seen_names = set()
    for obj in imported:
        for slot in obj.material_slots:
            if slot.material and slot.material.name not in _seen_names:
                _seen_names.add(slot.material.name)
                _all_mat_names.append(slot.material.name)
    _mat_total = len(_all_mat_names)
    print(f"== blend_export: {_mat_total} unique materials to create", flush=True)
    _mat_t0 = _time.monotonic()
    _mat_done = 0

    mat_cache = {}
    for obj in imported:
        for slot in obj.material_slots:
            old_mat = slot.material
            if old_mat is None:
                continue
            mat_name = old_mat.name
            if mat_name in mat_cache:
                slot.material = mat_cache[mat_name]
                continue

            png_path = find_png_for_material(args.textures, mat_name, mat_props, underscore_to_slash)
            preset = "Shaded Texture" if png_path else "Shaded Solid"
            _mat_done += 1
            _elapsed = _time.monotonic() - _mat_t0
            _pct = _mat_done / _mat_total * 100 if _mat_total else 100
            _eta = (_elapsed / _mat_done * (_mat_total - _mat_done)) if _mat_done else 0
            print(
                f"== blend_export: mat [{_mat_done}/{_mat_total} {_pct:.0f}%"
                f" +{_elapsed:.1f}s eta {_eta:.0f}s] {mat_name!r} preset={preset}",
                flush=True,
            )

            new_mat = createF3DMat(None, preset)
            new_mat.name = mat_name

            if png_path:
                img = bpy.data.images.load(png_path, check_existing=True)
                new_mat.f3d_mat.tex0.tex_set = True
                new_mat.f3d_mat.tex0.tex = img
                new_mat.f3d_mat.tex0.tex_format = "RGBA16"
            else:
                print(f"== blend_export: [warn] no texture found for {mat_name!r}", flush=True)

            props = mat_props.get(mat_name.lower()) or mat_props.get(mat_name.lower().replace("\\", "/"))
            if props and props.get("alpha_mode", "opaque") != "opaque":
                apply_alpha_mode(new_mat, props["alpha_mode"])

            slot.material = new_mat
            mat_cache[mat_name] = new_mat

    print(f"== blend_export: {len(mat_cache)} F3D materials created", flush=True)

    for mat in mat_cache.values():
        mat.collision_type_simple = "SURFACE_DEFAULT"

    bpy.ops.object.select_all(action="DESELECT")
    split_objects = []
    for obj in imported:
        if len(obj.material_slots) <= 1:
            split_objects.append(obj)
            continue
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.separate(type="MATERIAL")
        bpy.ops.object.mode_set(mode="OBJECT")
        splits = [o for o in bpy.context.selected_objects if o.type == "MESH"]
        split_objects.extend(splits)
        bpy.ops.object.select_all(action="DESELECT")
    imported = split_objects
    print(f"== blend_export: split into {len(imported)} per-material objects", flush=True)

    level_root = bpy.data.objects.new("Level Root", None)
    bpy.context.scene.collection.objects.link(level_root)
    level_root.sm64_obj_type = "Level Root"
    level_root.useBackgroundColor = False
    level_root.background = args.background_sky
    print(f"== blend_export: background={args.background_sky}", flush=True)

    area_root = bpy.data.objects.new("Area Root", None)
    bpy.context.scene.collection.objects.link(area_root)
    area_root.sm64_obj_type = "Area Root"
    area_root.areaIndex = args.area_id
    area_root.parent = level_root

    for obj in imported:
        obj.parent = area_root

    import mathutils

    min_pt = [float("inf")] * 3
    max_pt = [float("-inf")] * 3
    for obj in imported:
        for corner in obj.bound_box:
            wc = obj.matrix_world @ mathutils.Vector(corner)
            for i in range(3):
                if wc[i] < min_pt[i]:
                    min_pt[i] = wc[i]
                if wc[i] > max_pt[i]:
                    max_pt[i] = wc[i]

    margin = 1000.0
    water_y = min_pt[1] - margin
    cx = (min_pt[0] + max_pt[0]) * 0.5
    cz = (min_pt[2] + max_pt[2]) * 0.5
    sx = (max_pt[0] - min_pt[0]) * 0.5 + margin
    sz = (max_pt[2] - min_pt[2]) * 0.5 + margin

    water_box = bpy.data.objects.new("Water Box", None)
    bpy.context.scene.collection.objects.link(water_box)
    water_box.sm64_obj_type = "Water Box"
    water_box.waterBoxType = "Water"
    water_box.location = (cx, water_y, cz)
    water_box.scale = (sx, 1.0, sz)
    water_box.empty_display_size = 1.0
    water_box.parent = area_root
    print(f"== blend_export: Water Box at y={water_y:.1f} (floor min={min_pt[1]:.1f}), scale=({sx:.1f}, {sz:.1f})", flush=True)

    spawn_parts = [float(v) for v in args.spawn.split(",")]
    mario_start = bpy.data.objects.new("Mario Start", None)
    bpy.context.scene.collection.objects.link(mario_start)
    mario_start.sm64_obj_type = "Mario Start"
    mario_start.sm64_obj_mario_start_area = "0x01"
    mario_start.location = (spawn_parts[0], spawn_parts[1], spawn_parts[2])
    mario_start.parent = area_root
    print(f"== blend_export: Mario Start at {mario_start.location[:]}", flush=True)

    out_dir = Path(args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    sm64 = scene.fast64.sm64
    sm64.export_type = "C"
    sm64.blender_to_sm64_scale = args.scale

    ce = sm64.combined_export
    ce.non_decomp_level = True
    ce.custom_level_name = args.level_name
    ce.custom_level_path = str(out_dir)

    import fast64.fast64_internal.f3d.f3d_writer as _f3d_writer
    _orig_getInfoDict = _f3d_writer.getInfoDict
    _orig_saveOrGetF3DMaterial = _f3d_writer.saveOrGetF3DMaterial
    _export_total = [0]
    _export_done = [0]
    _export_t0 = [0.0]
    _export_total[0] = sum(
        1 for o in bpy.data.objects if o.type == "MESH" and o.visible_get()
    )
    _export_t0[0] = _time.monotonic()
    _mat_write_done = [0]
    _mat_write_t0 = [0.0]
    def _getInfoDict_logged(obj):
        _export_done[0] += 1
        obj.data.calc_loop_triangles()
        nf = len(obj.data.loop_triangles)
        _el = _time.monotonic() - _export_t0[0]
        _tot = _export_total[0]
        _dn = _export_done[0]
        _pct = _dn / _tot * 100 if _tot else 100
        _eta = (_el / _dn * (_tot - _dn)) if _dn else 0
        print(
            f"== f3d export [{_dn}/{_tot} {_pct:.0f}% +{_el:.1f}s eta {_eta:.0f}s]"
            f" {obj.name} ({nf} tris)",
            flush=True,
        )
        _mat_write_done[0] = 0
        _mat_write_t0[0] = _time.monotonic()
        return _orig_getInfoDict(obj)
    def _saveOrGetF3DMaterial_logged(material, fModel, obj, drawLayer, convertTextureData):
        _mat_write_done[0] += 1
        _dn = _mat_write_done[0]
        _el = _time.monotonic() - _mat_write_t0[0]
        _rate = _dn / _el if _el > 0 else 0
        print(
            f"  Writing material [{_dn} +{_el:.1f}s {_rate:.1f}/s] {material.name}",
            flush=True,
        )
        return _orig_saveOrGetF3DMaterial(material, fModel, obj, drawLayer, convertTextureData)
    _f3d_writer.getInfoDict = _getInfoDict_logged
    _f3d_writer.saveOrGetF3DMaterial = _saveOrGetF3DMaterial_logged

    bpy.context.view_layer.objects.active = level_root
    level_root.select_set(True)
    print("== blend_export: calling sm64_export_level", flush=True)
    bpy.ops.object.sm64_export_level()
    _f3d_writer.getInfoDict = _orig_getInfoDict
    _f3d_writer.saveOrGetF3DMaterial = _orig_saveOrGetF3DMaterial
    print("== blend_export: done", flush=True)


if __name__ == "__main__":
    main()
