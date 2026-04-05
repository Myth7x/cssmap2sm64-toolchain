import argparse
import json
import os
import sys
from pathlib import Path


_png_slug_cache: dict = {}


def _png_index(textures_dir):
    td = str(Path(textures_dir).resolve())
    if td not in _png_slug_cache:
        idx = {}
        mat_dir = os.path.join(td, "materials")
        if os.path.isdir(mat_dir):
            for root, _, files in os.walk(mat_dir):
                for fname in files:
                    if fname.lower().endswith(".png"):
                        full = os.path.join(root, fname)
                        rel = os.path.relpath(full, mat_dir).replace("\\", "/")
                        slug = rel[:-4].lower().replace("/", "_")
                        idx[slug] = full
        _png_slug_cache[td] = idx
    return _png_slug_cache[td]


def find_png(textures_dir, material_name):
    tex_dir = Path(textures_dir).resolve()

    direct = tex_dir / "materials" / (material_name.lower() + ".png")
    if direct.exists():
        return str(direct)

    flat_name = material_name.lower().replace("/", "_") + ".png"
    flat = tex_dir / flat_name
    if flat.exists():
        return str(flat)

    slug = material_name.lower().replace("\\", "_").replace("/", "_")
    idx = _png_index(textures_dir)
    if slug in idx:
        return idx[slug]

    return None


def find_png_for_material(textures_dir, material_name, mat_props, underscore_to_slash=None):
    import re as _re
    # Strip Blender's automatic deduplication suffix (.001, .002, .003, …)
    material_name = _re.sub(r'\.\d{3}$', '', material_name)
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
    has_tex = mat.f3d_mat.tex0.tex_set and mat.f3d_mat.tex0.tex is not None
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
        # Use texture alpha channel in combiner only when a texture is actually loaded
        if has_tex:
            try:
                mat.f3d_mat.combiner1.D_alpha = "TEXEL0"
                mat.f3d_mat.combiner2.D_alpha = "TEXEL0"
            except Exception:
                pass


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
    parser.add_argument("--decimate-ratio", type=float, default=1.0)
    parser.add_argument("--props-json", default=None)
    parser.add_argument("--bsp-scale", type=float, default=1.0)
    parser.add_argument("--env-json", default=None)
    parser.add_argument("--sky-obj", default=None)
    parser.add_argument("--sky-camera-json", default=None)
    parser.add_argument("--sky-cube-obj", default=None)
    parser.add_argument("--triggers-json", default=None)
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

    _env = {}
    _sun_light_data = None
    _sun_light_obj = None
    if args.env_json and Path(args.env_json).exists():
        with open(args.env_json, encoding="utf-8") as _ef:
            _env = json.load(_ef)
        import math as _lmath
        import mathutils as _lmu

        _sr, _sg, _sb = _env["sun_color"]
        _sun_light_data = bpy.data.lights.new("_bsp_sun", "SUN")
        _sun_light_data.color = (_sr, _sg, _sb)
        _sun_light_obj = bpy.data.objects.new("_bsp_sun", _sun_light_data)
        bpy.context.scene.collection.objects.link(_sun_light_obj)

        _elev = _lmath.radians(-_env["sun_pitch"])
        _yaw_r = _lmath.radians(_env["sun_yaw"])
        _tx = _lmath.cos(_elev) * _lmath.cos(_yaw_r)
        _ty = _lmath.cos(_elev) * _lmath.sin(_yaw_r)
        _tz = _lmath.sin(_elev)
        _mag = _lmath.sqrt(_tx * _tx + _ty * _ty + _tz * _tz)
        if _mag > 1e-6:
            _tx, _ty, _tz = _tx / _mag, _ty / _mag, _tz / _mag
        else:
            _tx, _ty, _tz = 0.0, 1.0, 0.0
        _from = _lmu.Vector((0.0, 0.0, 1.0))
        _to = _lmu.Vector((_tx, -_tz, _ty)).normalized()
        _sun_light_obj.rotation_mode = "QUATERNION"
        _sun_light_obj.rotation_quaternion = _from.rotation_difference(_to)
        _ar, _ag, _ab = _env["ambient_color"]
        print(
            f"== blend_export: env sun=({_sr:.2f},{_sg:.2f},{_sb:.2f})"
            f" dir=({_tx:.3f},{_ty:.3f},{_tz:.3f})"
            f" amb=({_ar:.2f},{_ag:.2f},{_ab:.2f})",
            flush=True,
        )
    else:
        print("== blend_export: no env data, using default lighting", flush=True)

    bpy.ops.object.select_all(action="DESELECT")
    print("== blend_export: importing OBJ", flush=True)

    _before_import = set(bpy.data.objects)
    blender_ver = bpy.app.version
    if blender_ver >= (3, 3, 0):
        bpy.ops.wm.obj_import(filepath=args.obj, forward_axis='NEGATIVE_Z', up_axis='Y')
    else:
        bpy.ops.import_scene.obj(filepath=args.obj, axis_forward='-Z', axis_up='Y')

    imported = [o for o in bpy.data.objects if o not in _before_import and o.type == "MESH"]
    if not imported:
        imported = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    print(f"== blend_export: imported {len(imported)} mesh objects", flush=True)

    import mathutils
    for _imp in imported:
        _rot = _imp.rotation_euler.to_matrix().to_4x4()
        _imp.data.transform(_rot)
        _imp.data.update()
        _imp.rotation_euler = (0.0, 0.0, 0.0)
    print(f"== blend_export: applied import rotation to vertex positions", flush=True)

    import bmesh as _bmesh_weld
    for _wobj in imported:
        _wbm = _bmesh_weld.new()
        _wbm.from_mesh(_wobj.data)
        _bmesh_weld.ops.remove_doubles(_wbm, verts=_wbm.verts, dist=0.001)
        _wbm.to_mesh(_wobj.data)
        _wbm.free()
        _wobj.data.update()
    print(f"== blend_export: vertex weld done ({len(imported)} objects)", flush=True)

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

            if _env and _sun_light_data is not None:
                _amb_r, _amb_g, _amb_b = _env["ambient_color"]
                new_mat.f3d_mat.use_default_lighting = False
                new_mat.f3d_mat.set_ambient_from_light = False
                new_mat.f3d_mat.ambient_light_color = (_amb_r, _amb_g, _amb_b, 1.0)
                new_mat.f3d_mat.f3d_light1 = _sun_light_data

            if png_path:
                try:
                    img = bpy.data.images.load(png_path, check_existing=True)
                    new_mat.f3d_mat.tex0.tex_set = True
                    new_mat.f3d_mat.tex0.tex = img
                    new_mat.f3d_mat.tex0.tex_format = "RGBA16"
                    _iw, _ih = int(img.size[0]), int(img.size[1])
                    if _iw > 0 and _ih > 0 and new_mat.f3d_mat.tex0.autoprop:
                        import math as _imath
                        def _log2up(n):
                            return max(1, int(_imath.ceil(_imath.log2(n))))
                        new_mat.f3d_mat.tex0.S.mask = _log2up(_iw)
                        new_mat.f3d_mat.tex0.S.shift = 0
                        new_mat.f3d_mat.tex0.S.low = 0.0
                        new_mat.f3d_mat.tex0.S.high = float(_iw - 1)
                        new_mat.f3d_mat.tex0.T.mask = _log2up(_ih)
                        new_mat.f3d_mat.tex0.T.shift = 0
                        new_mat.f3d_mat.tex0.T.low = 0.0
                        new_mat.f3d_mat.tex0.T.high = float(_ih - 1)
                except RuntimeError as _e:
                    print(f"== blend_export: [warn] could not load {png_path!r}: {_e}", flush=True)
            else:
                print(f"== blend_export: [warn] no texture found for {mat_name!r}", flush=True)
                # Preset sets tex_set=True by default; clear it so Fast64 doesn't error
                new_mat.f3d_mat.tex0.tex_set = False
                new_mat.f3d_mat.tex1.tex_set = False

            _alpha_key = mat_name.lower().replace("\\", "/")
            props = mat_props.get(_alpha_key)
            if props is None:
                _aslash = underscore_to_slash.get(_alpha_key)
                if _aslash:
                    props = mat_props.get(_aslash)
            if props and props.get("alpha_mode", "opaque") != "opaque":
                apply_alpha_mode(new_mat, props["alpha_mode"])

            slot.material = new_mat
            mat_cache[mat_name] = new_mat

    print(f"== blend_export: {len(mat_cache)} F3D materials created", flush=True)

    for mat in mat_cache.values():
        mat.collision_type_simple = "SURFACE_DEFAULT"

    if args.decimate_ratio < 1.0:
        import math as _dmath
        import bmesh as _bmesh
        print(f"== blend_export: decimating with ratio={args.decimate_ratio}", flush=True)
        surviving = []
        for obj in imported:
            before = len(obj.data.polygons)
            if before == 0:
                surviving.append(obj)
                continue

            bpy.context.view_layer.objects.active = obj

            # Fuse co-located vertices: bsp2obj emits every face with independent verts
            # (no sharing), so the mesh is entirely non-manifold. remove_doubles
            # reconnects shared edge vertices, making DISSOLVE/COLLAPSE hole-free.
            _bm = _bmesh.new()
            _bm.from_mesh(obj.data)
            _bmesh.ops.remove_doubles(_bm, verts=_bm.verts, dist=0.01)
            _bm.to_mesh(obj.data)
            _bm.free()
            obj.data.update()
            after_merge = len(obj.data.polygons)

            # Pass 1: DISSOLVE — merges coplanar adjacent faces (now has shared edges)
            mod_d = obj.modifiers.new(name="Dissolve", type="DECIMATE")
            mod_d.decimate_type = "DISSOLVE"
            mod_d.angle_limit = _dmath.radians(1.0)
            bpy.ops.object.modifier_apply(modifier=mod_d.name)
            after_dissolve = len(obj.data.polygons)

            # Pass 2: COLLAPSE — safe now that mesh is manifold (no T-junction holes)
            target = max(1, int(before * args.decimate_ratio))
            after = after_dissolve
            if after_dissolve > target:
                effective_ratio = max(args.decimate_ratio, 1.0 / after_dissolve)
                mod_c = obj.modifiers.new(name="Decimate", type="DECIMATE")
                mod_c.ratio = effective_ratio
                bpy.ops.object.modifier_apply(modifier=mod_c.name)
                after = len(obj.data.polygons)

            if after == 0:
                print(f"  [skip] {obj.name}: {before} -> 0 polys, removing", flush=True)
                bpy.data.objects.remove(obj, do_unlink=True)
                continue

            print(
                f"  {obj.name}: {before} merge->{after_merge} dissolve->{after_dissolve} collapse->{after}"
                f" ({after/before*100:.0f}%)",
                flush=True,
            )
            surviving.append(obj)
        imported = surviving

    print(f"== blend_export: {len(imported)} per-material objects (split at OBJ import)", flush=True)

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

    if args.props_json and Path(args.props_json).exists():
        import math as _pmath
        with open(args.props_json) as _pf:
            _props = json.load(_pf)
        _s = args.bsp_scale
        for _i, _prop in enumerate(_props):
            _ox, _oy, _oz = _prop["origin"]
            _pa, _py, _pr = _prop["angles"]
            _mdl = _prop.get("model", "")
            _name = f"prop_{_i:04d}"
            _empty = bpy.data.objects.new(_name, None)
            _empty.empty_display_type = "CUBE"
            _empty.empty_display_size = 16.0
            bpy.context.scene.collection.objects.link(_empty)
            _empty.location = (_ox * _s, _oy * _s, _oz * _s)
            _empty.rotation_euler = (
                _pmath.radians(_pr),
                _pmath.radians(-_py),
                _pmath.radians(_pa),
            )
            _empty["model"] = _mdl
            _empty["skin"] = _prop.get("skin", 0)
            _empty.parent = area_root
        print(f"== blend_export: placed {len(_props)} static prop empties", flush=True)

    if args.triggers_json and Path(args.triggers_json).exists():
        with open(args.triggers_json, encoding="utf-8") as _tf:
            _triggers = json.load(_tf)
        _TYPE_COLORS = {
            "death":    (1.0, 0.24, 0.24),
            "teleport": (0.24, 0.50, 1.0),
            "script":   (1.0, 0.86, 0.24),
            "door":     (0.0,  0.78, 0.47),
            "brush":    (0.24, 0.86, 0.24),
            "logic":    (1.0,  0.55, 0.0),
            "landmark": (0.72, 0.72, 0.72),
        }
        _trig_col = bpy.data.collections.new("Triggers")
        bpy.context.scene.collection.children.link(_trig_col)
        _s = args.bsp_scale
        for _ti, _trig in enumerate(_triggers):
            _ox, _oy, _oz = _trig["origin"]
            _mnx, _mny, _mnz = _trig["mins"]
            _mxx, _mxy, _mxz = _trig["maxs"]
            _cx = (_mnx + _mxx) * 0.5 * _s
            _cy = (_mny + _mxy) * 0.5 * _s
            _cz = (_mnz + _mxz) * 0.5 * _s
            _sx2 = max(abs(_mxx - _mnx) * 0.5 * _s, 1.0)
            _sy2 = max(abs(_mxy - _mny) * 0.5 * _s, 1.0)
            _sz2 = max(abs(_mxz - _mnz) * 0.5 * _s, 1.0)
            _ttype = _trig.get("type", "script")
            _tname = f"trigger_{_ttype}_{_ti:04d}"
            _te = bpy.data.objects.new(_tname, None)
            _te.empty_display_type = "CUBE"
            _te.empty_display_size = 1.0
            _te.location = (_cx, _cz, -_cy)
            _te.scale = (_sx2, _sz2, _sy2)
            _te["trigger_type"] = _ttype
            _te["trigger_class"] = _trig.get("class", "")
            _te["targetname"] = _trig.get("targetname", "")
            _te["target"] = _trig.get("target", "")
            _tc = _TYPE_COLORS.get(_ttype, (1.0, 1.0, 1.0))
            _te.color = (_tc[0], _tc[1], _tc[2], 0.5)
            _trig_col.objects.link(_te)
        print(f"== blend_export: placed {len(_triggers)} trigger debug empties", flush=True)

    out_dir = Path(args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    sm64 = scene.fast64.sm64
    sm64.export_type = "C"
    sm64.blender_to_sm64_scale = args.scale

    ce = sm64.combined_export
    ce.non_decomp_level = True
    ce.custom_level_name = args.level_name
    ce.custom_level_path = str(out_dir)

    bpy.context.view_layer.objects.active = level_root
    level_root.select_set(True)
    print("== blend_export: calling sm64_export_level", flush=True)
    bpy.ops.object.sm64_export_level()
    print("== blend_export: main level done", flush=True)

    if args.sky_obj and Path(args.sky_obj).exists():
        print("== blend_export: starting sky export", flush=True)

        sky_scene = bpy.data.scenes.new("sky_export_scene")
        # Inherit the world from the main scene so Fast64 doesn't spam "No world selected"
        sky_scene.world = scene.world if scene.world else (bpy.data.worlds[0] if bpy.data.worlds else None)
        bpy.context.window.scene = sky_scene
        # Make the sun light object visible in this scene so Fast64 can resolve it
        if _sun_light_obj is not None and _sun_light_obj.name not in sky_scene.collection.objects:
            sky_scene.collection.objects.link(_sun_light_obj)
        sky_scene.f3d_type = "F3DEX2/LX2"
        sky_scene.display_settings.display_device = "sRGB"
        sky_scene.view_settings.view_transform = "Standard"
        sky_scene.view_settings.look = "None"
        sky_scene.view_settings.exposure = 0.0
        sky_scene.view_settings.gamma = 1.0

        _sky_before = set(bpy.data.objects)
        if blender_ver >= (3, 3, 0):
            bpy.ops.wm.obj_import(filepath=args.sky_obj, forward_axis='NEGATIVE_Z', up_axis='Y')
        else:
            bpy.ops.import_scene.obj(filepath=args.sky_obj, axis_forward='-Z', axis_up='Y')

        # Also import cubemap box if provided
        if args.sky_cube_obj and Path(args.sky_cube_obj).exists():
            print(f"== blend_export: importing cubemap box OBJ", flush=True)
            if blender_ver >= (3, 3, 0):
                bpy.ops.wm.obj_import(filepath=args.sky_cube_obj, forward_axis='NEGATIVE_Z', up_axis='Y')
            else:
                bpy.ops.import_scene.obj(filepath=args.sky_cube_obj, axis_forward='-Z', axis_up='Y')

        sky_imported = [o for o in bpy.data.objects if o not in _sky_before and o.type == "MESH"]
        print(f"== blend_export: sky imported {len(sky_imported)} mesh objects", flush=True)

        for _simp in sky_imported:
            _srot = _simp.rotation_euler.to_matrix().to_4x4()
            _simp.data.transform(_srot)
            _simp.data.update()
            _simp.rotation_euler = (0.0, 0.0, 0.0)

        import bmesh as _sky_bmesh
        for _swobj in sky_imported:
            _swbm = _sky_bmesh.new()
            _swbm.from_mesh(_swobj.data)
            _sky_bmesh.ops.remove_doubles(_swbm, verts=_swbm.verts, dist=0.001)
            _swbm.to_mesh(_swobj.data)
            _swbm.free()
            _swobj.data.update()

        sky_mat_cache = {}
        for _sobj in sky_imported:
            for _sslot in _sobj.material_slots:
                _sold = _sslot.material
                if _sold is None:
                    continue
                _smn = _sold.name
                if _smn in sky_mat_cache:
                    _sslot.material = sky_mat_cache[_smn]
                    continue
                _spng = find_png_for_material(args.textures, _smn, mat_props, underscore_to_slash)
                _spreset = "Shaded Texture" if _spng else "Shaded Solid"
                _snew = createF3DMat(None, _spreset)
                _snew.name = _smn
                if _env and _sun_light_data is not None:
                    _amb_r2, _amb_g2, _amb_b2 = _env["ambient_color"]
                    _snew.f3d_mat.use_default_lighting = False
                    _snew.f3d_mat.set_ambient_from_light = False
                    _snew.f3d_mat.ambient_light_color = (_amb_r2, _amb_g2, _amb_b2, 1.0)
                    _snew.f3d_mat.f3d_light1 = _sun_light_data
                if _spng:
                    import math as _simath
                    try:
                        _simg = bpy.data.images.load(_spng, check_existing=True)
                        _snew.f3d_mat.tex0.tex_set = True
                        _snew.f3d_mat.tex0.tex = _simg
                        _snew.f3d_mat.tex0.tex_format = "RGBA16"
                        _siw, _sih = int(_simg.size[0]), int(_simg.size[1])
                        if _siw > 0 and _sih > 0 and _snew.f3d_mat.tex0.autoprop:
                            def _slog2up(n):
                                return max(1, int(_simath.ceil(_simath.log2(n))))
                            _snew.f3d_mat.tex0.S.mask = _slog2up(_siw)
                            _snew.f3d_mat.tex0.S.shift = 0
                            _snew.f3d_mat.tex0.S.low = 0.0
                            _snew.f3d_mat.tex0.S.high = float(_siw - 1)
                            _snew.f3d_mat.tex0.T.mask = _slog2up(_sih)
                            _snew.f3d_mat.tex0.T.shift = 0
                            _snew.f3d_mat.tex0.T.low = 0.0
                            _snew.f3d_mat.tex0.T.high = float(_sih - 1)
                    except RuntimeError as _se:
                        print(f"== blend_export: [warn] sky could not load {_spng!r}: {_se}", flush=True)
                # Apply alpha mode (e.g. $translucent trees need XLU blend)
                _alpha_key_sky = _smn.lower().replace("\\", "/")
                _props_sky = mat_props.get(_alpha_key_sky)
                if _props_sky is None:
                    _aslash_sky = underscore_to_slash.get(_alpha_key_sky)
                    if _aslash_sky:
                        _props_sky = mat_props.get(_aslash_sky)
                if _props_sky and _props_sky.get("alpha_mode", "opaque") != "opaque":
                    apply_alpha_mode(_snew, _props_sky["alpha_mode"])
                    print(f"== blend_export: sky mat {_smn!r} alpha_mode={_props_sky['alpha_mode']!r}", flush=True)
                _sslot.material = _snew
                sky_mat_cache[_smn] = _snew

        for _sm in sky_mat_cache.values():
            _sm.collision_type_simple = "SURFACE_DEFAULT"

        import math as _sdmath
        import bmesh as _sdbmesh
        sky_surviving = []
        for _sobj in sky_imported:
            if len(_sobj.data.polygons) == 0:
                sky_surviving.append(_sobj)
                continue
            bpy.context.view_layer.objects.active = _sobj
            _sbm = _sdbmesh.new()
            _sbm.from_mesh(_sobj.data)
            _sdbmesh.ops.remove_doubles(_sbm, verts=_sbm.verts, dist=0.01)
            _sbm.to_mesh(_sobj.data)
            _sbm.free()
            _sobj.data.update()
            _smod = _sobj.modifiers.new(name="SkyDissolve", type="DECIMATE")
            _smod.decimate_type = "DISSOLVE"
            _smod.angle_limit = _sdmath.radians(1.0)
            if len(_sobj.data.polygons) > 3:
                bpy.ops.object.modifier_apply(modifier=_smod.name)
            else:
                _sobj.modifiers.remove(_smod)
            if len(_sobj.data.polygons) == 0:
                bpy.data.objects.remove(_sobj, do_unlink=True)
                continue
            sky_surviving.append(_sobj)
        sky_imported = sky_surviving

        sky_level_name = args.level_name + "_sky"
        sky_level_root = bpy.data.objects.new("Sky Level Root", None)
        sky_scene.collection.objects.link(sky_level_root)
        sky_level_root.sm64_obj_type = "Level Root"
        sky_level_root.useBackgroundColor = False
        sky_level_root.background = args.background_sky

        sky_area_root = bpy.data.objects.new("Sky Area Root", None)
        sky_scene.collection.objects.link(sky_area_root)
        sky_area_root.sm64_obj_type = "Area Root"
        sky_area_root.areaIndex = 2
        sky_area_root.parent = sky_level_root

        for _sobj in sky_imported:
            _sobj.parent = sky_area_root

        sky_out_dir = Path(args.output).resolve() / sky_level_name
        sky_out_dir.mkdir(parents=True, exist_ok=True)

        sky_sm64 = sky_scene.fast64.sm64
        sky_sm64.export_type = "C"
        sky_sm64.blender_to_sm64_scale = args.scale

        sky_ce = sky_sm64.combined_export
        sky_ce.non_decomp_level = True
        sky_ce.custom_level_name = sky_level_name
        sky_ce.custom_level_path = str(sky_out_dir.parent)

        bpy.context.view_layer.objects.active = sky_level_root
        sky_level_root.select_set(True)
        print("== blend_export: calling sm64_export_level for sky", flush=True)
        bpy.ops.object.sm64_export_level()
        print("== blend_export: sky level done", flush=True)

        bpy.context.window.scene = scene

    print("== blend_export: done", flush=True)


if __name__ == "__main__":
    main()
