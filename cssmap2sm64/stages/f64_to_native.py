import hashlib
import json
import math
import re
import shutil
from pathlib import Path
from typing import Optional, Tuple

_GEO_BOILERPLATE = """\
#include <ultra64.h>
#include "sm64.h"
#include "geo_commands.h"

#include "game/level_geo.h"
#include "game/geo_misc.h"
#include "game/camera.h"
#include "game/moving_texture.h"
#include "game/screen_transition.h"
#include "game/paintings.h"

#include "make_const_nonconst.h"

"""

_LEVELDATA_BOILERPLATE = """\
#include <ultra64.h>
#include "sm64.h"
#include "surface_terrains.h"
#include "moving_texture_macros.h"
#include "level_misc_macros.h"
#include "macro_preset_names.h"
#include "special_preset_names.h"
#include "textures.h"
#include "dialog_ids.h"

#include "make_const_nonconst.h"

"""


def _write_header(src: Path, dst: Path, level_name: str) -> None:
    content = src.read_text(encoding="utf-8")
    guard = level_name.upper() + "_HEADER_H"
    out = (
        f"#ifndef {guard}\n"
        f"#define {guard}\n\n"
        f'#include "types.h"\n\n'
        + content
        + f"\nextern const LevelScript level_{level_name}_entry[];\n"
        + f"\n#endif\n"
    )
    dst.write_text(out, encoding="utf-8")


def _write_geo(src_inc: Path, dst: Path, level_name: str) -> None:
    content = _GEO_BOILERPLATE
    content += f'#include "levels/{level_name}/header.h"\n\n'
    content += f'#include "levels/{level_name}/areas/1/geo.inc.c"\n'
    dst.write_text(content, encoding="utf-8")


_VTX_RE = re.compile(
    r'(\{\{\s*'
    r'\{\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*\}\s*,'
    r'\s*\d+\s*,)'
    r'(\s*\{\s*)(-?\d+)(\s*,\s*)(-?\d+)(\s*\}\s*,)'
    r'(\s*\{\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*\}\s*\}\})'
)


def _wrap_s16(v: int) -> int:
    return ((v + 32768) % 65536) - 32768


def _fix_model_uvs(src: Path, dst: Path) -> None:
    text = src.read_text(encoding='utf-8')
    def _repl(m: re.Match) -> str:
        u = _wrap_s16(int(m.group(3)))
        v = _wrap_s16(int(m.group(5)))
        return m.group(1) + m.group(2) + str(u) + m.group(4) + str(v) + m.group(6) + m.group(7)
    dst.write_text(_VTX_RE.sub(_repl, text), encoding='utf-8')


def _write_leveldata(dst: Path, level_name: str, has_lighting: bool = False) -> None:
    content = _LEVELDATA_BOILERPLATE
    content += f'#include "levels/{level_name}/texture.inc.c"\n'
    content += f'#include "levels/{level_name}/areas/1/1/model.inc.c"\n'
    content += f'#include "levels/{level_name}/areas/1/collision.inc.c"\n'
    content += f'#include "levels/{level_name}/areas/1/macro.inc.c"\n'
    if has_lighting:
        level_define = 'LEVEL_' + level_name.upper()
        content += f'#define LEVEL_LIGHTING_NUM {level_define}\n'
        content += f'#include "levels/{level_name}/level_lighting.inc.c"\n'
        content += f'#undef LEVEL_LIGHTING_NUM\n'
    dst.write_text(content, encoding="utf-8")


def _scale_collision(src: Path, dst: Path, divisor: int) -> None:
    text = src.read_text(encoding="utf-8")
    def _scale_vertex(m: re.Match) -> str:
        x = max(-32768, min(32767, round(int(m.group(1)) / divisor)))
        y = max(-32768, min(32767, round(int(m.group(2)) / divisor)))
        z = max(-32768, min(32767, round(int(m.group(3)) / divisor)))
        return f"COL_VERTEX({x}, {y}, {z})"
    def _scale_water_box(m: re.Match) -> str:
        idx = m.group(1)
        vals = [max(-32768, min(32767, round(int(v.strip()) / divisor))) for v in m.group(2).split(',')]
        return f"COL_WATER_BOX({idx}, {vals[0]}, {vals[1]}, {vals[2]}, {vals[3]}, {vals[4]})"
    result = re.sub(
        r'COL_VERTEX\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\)',
        _scale_vertex, text,
    )
    result = re.sub(
        r'COL_WATER_BOX\(\s*(0x[0-9a-fA-F]+|\d+)\s*,\s*(-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+)\s*\)',
        _scale_water_box, result,
    )
    dst.write_text(result, encoding="utf-8")


def _write_script(
    src: Path = Path("script.c"),
    dst: Path = Path("script.c"),
    sm64_spawn: Optional[Tuple[int, int, int]] = None
) -> None:
    #text = src.read_text(encoding="utf-8")
    #lines = text.splitlines(keepends=True)
    #result = []
    #for line in lines:
    #    if re.match(r'\s*MARIO_POS\s*\(', line):
    #        if sm64_spawn is not None:
    #            indent = re.match(r'(\s*)', line).group(1)
    #            x, y, z = sm64_spawn
    #            result.append(f"{indent}MARIO_POS(0x01, 0, {x}, {y}, {z}),\n")
    #        continue
    #    result.append(line)
    #dst.write_text("".join(result), encoding="utf-8")
    try:
        text = src.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    if sm64_spawn is not None:
        spawn_cmd = f"    MARIO_POS(0x01, 0, {sm64_spawn[0]}, {sm64_spawn[1]}, {sm64_spawn[2]}),\n"
        if "MARIO_POS" in text:
            text = re.sub(
                r'\s*MARIO_POS\s*\(\s*0x01\s*,\s*0\s*,\s*-?\d+\s*,\s*-?\d+\s*,\s*-?\d+\s*\)\s*,\n',
                spawn_cmd,
                text,
            )
        else:
            text = spawn_cmd + text
    dst.write_text(text, encoding="utf-8")



def _write_level_lighting(dst: Path, env: dict, scale_factor: float = 1.0, net: float = 1.0,
                          pl_radius_mult: float = 5.0, pl_intensity_mult: float = 1.0) -> None:
    pitch = env.get("sun_pitch", -45.0)
    yaw_deg = env.get("sun_yaw", 0.0)
    elev = math.radians(-pitch)
    yaw_r = math.radians(yaw_deg)
    dx = math.cos(elev) * math.cos(yaw_r)
    dy = math.sin(elev)
    dz = -math.cos(elev) * math.sin(yaw_r)
    ar, ag, ab = env.get("ambient_color", [0.3, 0.3, 0.3])
    sr, sg, sb = env.get("sun_color", [1.0, 1.0, 1.0])
    fog = env.get("fog", None)
    point_lights = env.get("point_lights", [])
    lines = [
        '#include "src/pc/gfx/level_lights.h"',
        '#include "level_table.h"',
        'static void s_lighting_apply(void) {',
        f'    level_lights_set_ambient({ar:.6f}f, {ag:.6f}f, {ab:.6f}f, 1.0f);',
        f'    level_lights_set_sun({dx:.6f}f, {dy:.6f}f, {dz:.6f}f, {sr:.6f}f, {sg:.6f}f, {sb:.6f}f);',
        '    level_lights_set_shadow_count(1);',
        '    level_lights_compute_shadow_vp_sun(0, 0.0f, 0.0f, 0.0f, 10000.0f);',
    ]
    for pl in point_lights[:8]:
        ox, oy, oz = pl["origin"]
        px, py, pz = _bsp_to_sm64(ox, oy, oz, scale_factor, net)
        radius = pl["radius_bsp"] * scale_factor * net * pl_radius_mult
        r, g, b = pl["color"]
        intensity = pl["intensity"] * pl_intensity_mult
        lines.append(
            f'    {{ LevelLight _pl = {{{{{px:.1f}f, {py:.1f}f, {pz:.1f}f}}, {radius:.1f}f,'
            f' {{{r:.6f}f, {g:.6f}f, {b:.6f}f}}, {intensity:.6f}f}}; level_lights_add(&_pl); }}'
        )
    if fog:
        fr, fg_c, fb = fog["fog_color"]
        lines.append(
            f'    level_lights_set_fog({fr:.6f}f, {fg_c:.6f}f, {fb:.6f}f,'
            f' {fog["fog_start"]:.1f}f, {fog["fog_end"]:.1f}f, {fog["fog_max_density"]:.4f}f);'
        )
    lines += [
        '}',
        '__attribute__((constructor)) static void s_lighting_register(void) {',
        '    level_lighting_register(LEVEL_LIGHTING_NUM, s_lighting_apply);',
        '}',
    ]
    dst.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _write_level_yaml(dst: Path, level_name: str, skybox_bin: str = "water") -> None:
    content = (
        f"short-name: {level_name}\n"
        f"full-name: {level_name}\n"
        f"texture-file: []\n"
        f"area-count: 1\n"
        f"objects: []\n"
        f"shared-path: []\n"
        f"skybox-bin: {skybox_bin}\n"
        f"texture-bin: generic\n"
        f"effects: false\n"
        f"actor-bins: []\n"
        f"common-bin: []\n"
    )
    dst.write_text(content, encoding="utf-8")


_MAX_TRIS_PER_GROUP: int = 65535
_MAX_VERTS_PER_BLOCK: int = 65535


def generate_collision_from_obj(obj_path: Path, out_path: Path, level_name: str, net: float) -> None:
    import io as _io

    vertices: list = []
    faces: list = []

    with open(obj_path, encoding="utf-8", errors="replace") as _f:
        for line in _f:
            if line.startswith("v "):
                p = line.split()
                vertices.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("f "):
                p = line.split()[1:]
                idx = [int(pt.split("/")[0]) - 1 for pt in p]
                for i in range(1, len(idx) - 1):
                    a, b, c = idx[0], idx[i], idx[i + 1]
                    v1, v2, v3 = vertices[a], vertices[b], vertices[c]
                    ax, ay, az = v2[0]-v1[0], v2[1]-v1[1], v2[2]-v1[2]
                    bx, by, bz = v3[0]-v2[0], v3[1]-v2[1], v3[2]-v2[2]
                    ny = az * bx - ax * bz
                    if ny < 0:
                        faces.append((a, c, b))
                    else:
                        faces.append((a, b, c))

    array_name = f"{level_name}_area_1_collision"

    blocks: list = []
    cur_vmap: dict = {}
    cur_verts: list = []
    cur_tris: list = []

    for i0, i1, i2 in faces:
        needed = sum(1 for v in (i0, i1, i2) if v not in cur_vmap)
        if len(cur_verts) + needed > _MAX_VERTS_PER_BLOCK:
            if cur_verts:
                blocks.append((list(cur_verts), list(cur_tris)))
            cur_vmap = {}
            cur_verts = []
            cur_tris = []
        local = []
        for v in (i0, i1, i2):
            if v not in cur_vmap:
                cur_vmap[v] = len(cur_verts)
                cur_verts.append(v)
            local.append(cur_vmap[v])
        cur_tris.append((local[0], local[1], local[2]))

    if cur_verts:
        blocks.append((list(cur_verts), list(cur_tris)))

    def _sm64(v_idx: int):
        x, y, z = vertices[v_idx]
        return (
            max(-32767, min(32767, round(x * net))),
            max(-32767, min(32767, round(y * net))),
            max(-32767, min(32767, round(z * net))),
        )

    buf = _io.StringIO()
    buf.write(f"const Collision {array_name}[] = {{\n")
    for vert_indices, tris in blocks:
        buf.write("\tCOL_INIT(),\n")
        buf.write(f"\tCOL_VERTEX_INIT({len(vert_indices)}),\n")
        for vi in vert_indices:
            sx, sy, sz = _sm64(vi)
            buf.write(f"\tCOL_VERTEX({sx}, {sy}, {sz}),\n")
        for chunk_start in range(0, len(tris), _MAX_TRIS_PER_GROUP):
            chunk = tris[chunk_start:chunk_start + _MAX_TRIS_PER_GROUP]
            buf.write(f"\tCOL_TRI_INIT(SURFACE_DEFAULT, {len(chunk)}),\n")
            for v0, v1, v2 in chunk:
                buf.write(f"\tCOL_TRI({v0}, {v1}, {v2}),\n")
            buf.write("\tCOL_TRI_STOP(),\n")
    buf.write("\tCOL_END()\n};\n")

    out_path.write_text(buf.getvalue(), encoding="utf-8")


def _split_large_collision_blocks(path: Path, max_verts: int = 65535) -> None:
    text = path.read_text(encoding="utf-8")
    m = re.search(r'COL_VERTEX_INIT\((\d+)\)', text)
    if not m or int(m.group(1)) <= max_verts:
        return

    decl_m = re.search(r'(const Collision \w+\[\] = \{)', text)
    if not decl_m:
        return

    preamble = text[:decl_m.start()]
    decl = decl_m.group(1)

    vertices = [(int(x), int(y), int(z)) for x, y, z in
                re.findall(r'COL_VERTEX\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\)', text)]

    tri_groups = []
    for tm in re.finditer(r'COL_TRI_INIT\((\w+)\s*,\s*\d+\)', text):
        surf_type = tm.group(1)
        after = text[tm.end():]
        stop_m = re.search(r'COL_TRI_STOP\s*\(\s*\)|COL_TRI_INIT\s*\(', after)
        chunk = after[:stop_m.start()] if stop_m else after
        tris = [(int(a), int(b), int(c)) for a, b, c in
                re.findall(r'COL_TRI\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', chunk)]
        tri_groups.append((surf_type, tris))

    specials_m = re.search(
        r'(COL_SPECIAL_INIT\(.*?\)(?:.*?\n)*?.*?(?=\s*COL_WATER_BOX|\s*COL_END))',
        text, re.DOTALL)
    water_m = re.search(
        r'(COL_WATER_BOX_INIT\(.*?\)(?:.*?\n)*?.*?(?=\s*COL_END))',
        text, re.DOTALL)

    all_tris = [(st, tri) for st, tris in tri_groups for tri in tris]

    blocks = []
    cur_vmap: dict = {}
    cur_verts: list = []
    cur_tris_by_type: dict = {}

    for surf_type, (g0, g1, g2) in all_tris:
        needed = sum(1 for v in (g0, g1, g2) if v not in cur_vmap)
        if len(cur_verts) + needed > max_verts:
            if cur_verts:
                blocks.append((list(cur_verts), dict(cur_tris_by_type)))
            cur_vmap = {}
            cur_verts = []
            cur_tris_by_type = {}
        local = []
        for v in (g0, g1, g2):
            if v not in cur_vmap:
                cur_vmap[v] = len(cur_verts)
                cur_verts.append(vertices[v])
            local.append(cur_vmap[v])
        cur_tris_by_type.setdefault(surf_type, []).append(tuple(local))

    if cur_verts:
        blocks.append((list(cur_verts), dict(cur_tris_by_type)))

    out = preamble + decl + "\n"
    for verts, tris_by_type in blocks:
        out += "\tCOL_INIT(),\n"
        out += f"\tCOL_VERTEX_INIT({len(verts)}),\n"
        for x, y, z in verts:
            out += f"\tCOL_VERTEX({x}, {y}, {z}),\n"
        for surf_type, tris in tris_by_type.items():
            for chunk_start in range(0, len(tris), _MAX_TRIS_PER_GROUP):
                chunk = tris[chunk_start:chunk_start + _MAX_TRIS_PER_GROUP]
                out += f"\tCOL_TRI_INIT({surf_type}, {len(chunk)}),\n"
                for v1, v2, v3 in chunk:
                    out += f"\tCOL_TRI({v1}, {v2}, {v3}),\n"
                out += "\tCOL_TRI_STOP(),\n"

    if specials_m:
        out += "\t" + specials_m.group(1).strip() + "\n"
    if water_m:
        out += "\t" + water_m.group(1).strip() + "\n"

    out += "\tCOL_END()\n};\n"
    path.write_text(out, encoding="utf-8")


_EBOX_TYPE = {
    "death":    1,
    "teleport": 2,
    "script":   3,
    "door":     4,
    "brush":    5,
    "logic":    6,
    "landmark": 7,
    "push":     8,
}

_EBOX_TYPE_NAME = {v: k for k, v in _EBOX_TYPE.items()}


def _bsp_to_sm64(bsp_x: float, bsp_y: float, bsp_z: float,
                  scale_factor: float, net: float) -> tuple:
    return (
        round(bsp_x * scale_factor * net),
        round(bsp_z * scale_factor * net),
        round(-bsp_y * scale_factor * net),
    )


def _clamp_s16(v: int) -> int:
    return max(-32768, min(32767, v))


def _write_entities_inc(
    dst_path: Path,
    level_name: str,
    triggers: list,
    scale_factor: float,
    net: float,
    sm64_spawn: Optional[Tuple[int, int, int]] = None,
) -> None:
    landmark_map = {
        e['targetname']: e['origin']
        for e in triggers
        if e.get('type') == 'landmark' and e.get('targetname')
    }
    lines = [
        '#include "game/entity_boxes.h"',
        '',
        f'const struct EntityBox {level_name}_entity_boxes[] = {{',
    ]
    for t in triggers:
        ttype = _EBOX_TYPE.get(t.get("type", ""), 0)
        if ttype == 0:
            continue
        mnx, mny, mnz = t["mins"]
        mxx, mxy, mxz = t["maxs"]
        sm64_mnx = _clamp_s16(round(mnx * scale_factor * net))
        sm64_mxx = _clamp_s16(round(mxx * scale_factor * net))
        sm64_mny = _clamp_s16(round(mnz * scale_factor * net))
        sm64_mxy = _clamp_s16(round(mxz * scale_factor * net))
        sm64_mnz = _clamp_s16(round(-mxy * scale_factor * net))
        sm64_mxz = _clamp_s16(round(-mny * scale_factor * net))
        r_mnx, r_mxx = min(sm64_mnx, sm64_mxx), max(sm64_mnx, sm64_mxx)
        r_mny, r_mxy = min(sm64_mny, sm64_mxy), max(sm64_mny, sm64_mxy)
        r_mnz, r_mxz = min(sm64_mnz, sm64_mxz), max(sm64_mnz, sm64_mxz)
        if ttype == _EBOX_TYPE['teleport']:
            _MIN_EXT, _TARGET_EXT = 128, 256
            if r_mxx - r_mnx < _MIN_EXT:
                cx = (r_mnx + r_mxx) // 2
                r_mnx, r_mxx = cx - _TARGET_EXT // 2, cx + _TARGET_EXT // 2
            if r_mxy - r_mny < _MIN_EXT:
                cy = (r_mny + r_mxy) // 2
                r_mny, r_mxy = cy - _TARGET_EXT // 2, cy + _TARGET_EXT // 2
            if r_mxz - r_mnz < _MIN_EXT:
                cz = (r_mnz + r_mxz) // 2
                r_mnz, r_mxz = cz - _TARGET_EXT // 2, cz + _TARGET_EXT // 2
        if ttype == _EBOX_TYPE['teleport']:
            target_name = t.get('target', '')
            bsp_origin = landmark_map.get(target_name, [0, 0, 0])
            dx, dy, dz = _bsp_to_sm64(bsp_origin[0], bsp_origin[1], bsp_origin[2], scale_factor, net)
            dest_x, dest_y, dest_z = _clamp_s16(dx), _clamp_s16(dy), _clamp_s16(dz)
        elif ttype == _EBOX_TYPE['push']:
            pushdir_str = t.get('pushdir', '0 0 0')
            speed = float(t.get('speed', 0) or 0)
            parts = [float(s) for s in (pushdir_str or '0 0 0').split()]
            pitch_rad = math.radians(parts[0] if len(parts) > 0 else 0.0)
            yaw_rad = math.radians(parts[1] if len(parts) > 1 else 0.0)
            spf = speed * scale_factor * net / 30.0
            dest_x = _clamp_s16(round(math.cos(pitch_rad) * math.cos(yaw_rad) * spf))
            dest_y = _clamp_s16(round(-math.sin(pitch_rad) * spf))
            dest_z = _clamp_s16(round(-math.cos(pitch_rad) * math.sin(yaw_rad) * spf))
        else:
            dest_x, dest_y, dest_z = 0, 0, 0
        lines.append(
            f'    {{{ttype},'
            f' {{{r_mnx}, {r_mny}, {r_mnz}}},'
            f' {{{r_mxx}, {r_mxy}, {r_mxz}}},'
            f' {{{dest_x}, {dest_y}, {dest_z}}}}},'
        )
    lines += [
        '    {0, {0, 0, 0}, {0, 0, 0}, {0, 0, 0}}',
        '};',
        '',
        f's32 {level_name}_entities_init(UNUSED s16 arg, UNUSED s32 unused) {{',
    ]
    if sm64_spawn is not None:
        x, y, z = sm64_spawn
        lines.append(f'    entity_boxes_set_default_spawn({x}.0f, {y}.0f, {z}.0f);')
    lines += [
        f'    entity_boxes_register({level_name}_entity_boxes);',
        '    return 0;',
        '}',
        '',
    ]
    dst_path.write_text('\n'.join(lines), encoding='utf-8')


def _patch_header_entities(header_path: Path, level_name: str) -> None:
    text = header_path.read_text(encoding='utf-8')
    inc_line   = '#include "game/entity_boxes.h"\n'
    decl_box   = f'extern const struct EntityBox {level_name}_entity_boxes[];\n'
    decl_fn    = f's32 {level_name}_entities_init(s16, s32);\n'
    # Build the block to insert (include must precede the extern)
    block = ''
    if inc_line not in text:
        block += inc_line
    if decl_box not in text:
        block += decl_box
    if decl_fn not in text:
        block += decl_fn
    if not block:
        return
    # Insert before #endif at end of file
    text = text.rstrip()
    if text.endswith('#endif'):
        text = text[:-len('#endif')].rstrip() + '\n\n' + block + '#endif\n'
    else:
        text += '\n' + block
    header_path.write_text(text, encoding='utf-8')


def _inject_triggers(
    script_path: Path,
    triggers: list,
    collision_divisor: int,
    scale_factor: float,
    blender_to_sm64_scale: float,
    level_name: str,
) -> None:
    try:
        text = script_path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return

    net = blender_to_sm64_scale / collision_divisor

    death_objs = []
    teleport_objs = []
    warp_nodes = []
    warp_id = 0x10

    for t in triggers:
        ox, oy, oz = t["origin"]
        mnx, mny, mnz = t["mins"]
        mxx, mxy, mxz = t["maxs"]
        sm_x, sm_y, sm_z = _bsp_to_sm64(ox, oy, oz, scale_factor, net)

        ttype = t.get("type", "")

        if ttype == "death":
            hw = max(abs(mxx - mnx), abs(mxy - mny), abs(mxz - mnz)) * 0.5
            radius_sm64 = hw * scale_factor * net
            param_val = max(1, min(25, round(radius_sm64 / 10.0)))
            beh_param = (param_val << 24) & 0xFFFFFFFF
            death_objs.append(
                f'\t\tOBJECT(MODEL_NONE, {sm_x}, {sm_y}, {sm_z},'
                f' 0, 0, 0, {beh_param:#010x}, bhvDeathWarp),'
            )

        elif ttype == "teleport":
            src_id = warp_id
            warp_id = (warp_id + 1) & 0xEF
            if warp_id >= 0xF0:
                warp_id = 0x10
            dest_id = src_id
            tname = t.get("targetname", "")
            landmark_pos = None
            for lt in triggers:
                if lt.get("type") == "landmark" and lt.get("targetname") == t.get("target", ""):
                    lox, loy, loz = lt["origin"]
                    landmark_pos = _bsp_to_sm64(lox, loy, loz, scale_factor, net)
                    break
            beh_param = ((src_id & 0xFF) << 16) & 0xFFFFFFFF
            teleport_objs.append(
                f'\t\tOBJECT(MODEL_NONE, {sm_x}, {sm_y}, {sm_z},'
                f' 0, 0, 0, {beh_param:#010x}, bhvInstantActiveWarp),'
            )
            level_const = 'LEVEL_' + level_name.upper()
            warp_nodes.append(
                f'\t\tWARP_NODE(0x{src_id:02X}, {level_const}, 0x01, 0x{dest_id:02X}, 0x00),'
            )
            if landmark_pos:
                lx, ly, lz = landmark_pos
                teleport_objs.append(
                    f'\t\tOBJECT(MODEL_NONE, {lx}, {ly}, {lz},'
                    f' 0, 0, 0, {beh_param:#010x}, bhvInstantActiveWarp),'
                )

    all_objects = death_objs + teleport_objs

    entities_call = f'\t\tCALL(0, {level_name}_entities_init),\n'

    if all_objects:
        obj_block = '\n'.join(all_objects) + '\n'
        text = re.sub(
            r'(\s*END_AREA\s*\(\s*\)\s*,)',
            '\n' + obj_block + r'\1',
            text, count=1,
        )

    if warp_nodes:
        wn_block = '\n'.join(warp_nodes) + '\n'
        text = re.sub(
            r'(\s*END_AREA\s*\(\s*\)\s*,)',
            '\n' + wn_block + r'\1',
            text, count=1,
        )

    if entities_call not in text:
        text = re.sub(
            r'([ \t]*CALL\s*\(\s*0\s*,\s*lvl_init_or_update\s*\)\s*,[ \t]*\n)',
            r'\1' + entities_call,
            text,
        )

    script_path.write_text(text, encoding='utf-8')


def convert(
    fast64_dir: Path,
    out_dir: Path,
    level_name: str,
    collision_divisor: int = 150,
    sm64_spawn: Optional[Tuple[int, int, int]] = None,
    skybox_bin: str = "water",
    env_json: Optional[Path] = None,
    triggers_json: Optional[Path] = None,
    scale_factor: float = 1.0,
    blender_to_sm64_scale: float = 300.0,
    point_light_radius_mult: float = 5.0,
    point_light_intensity_mult: float = 1.0,
) -> None:
    fast64_dir = Path(fast64_dir)
    out_dir = Path(out_dir)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    areas1 = out_dir / "areas" / "1"
    areas1.mkdir(parents=True)
    (areas1 / "1").mkdir()

    _scale_collision(
        fast64_dir / "area_1" / "collision.inc.c",
        areas1 / "collision.inc.c",
        collision_divisor,
    )
    _split_large_collision_blocks(areas1 / "collision.inc.c")
    for fname in ("geo.inc.c", "macro.inc.c"):
        shutil.copy2(fast64_dir / "area_1" / fname, areas1 / fname)

    _fix_model_uvs(fast64_dir / "model.inc.c", areas1 / "1" / "model.inc.c")

    _write_header(
        fast64_dir / "header.inc.h",
        out_dir / "header.h",
        level_name,
    )

    _write_geo(fast64_dir / "geo.inc.c", out_dir / "geo.c", level_name)

    env = None
    if env_json is not None:
        env_path = Path(env_json)
        if env_path.exists():
            with open(env_path, encoding="utf-8") as _f:
                env = json.load(_f)
            _write_level_lighting(
                out_dir / "level_lighting.inc.c", env,
                scale_factor, blender_to_sm64_scale / collision_divisor,
                point_light_radius_mult, point_light_intensity_mult,
            )

    _write_leveldata(out_dir / "leveldata.c", level_name, has_lighting=(env is not None))

    _write_script(fast64_dir / "script.c", out_dir / "script.c", sm64_spawn)

    triggers = []
    if triggers_json is not None:
        _tj = Path(triggers_json)
        if _tj.exists():
            with open(_tj, encoding="utf-8") as _tf:
                triggers = json.load(_tf)

    if triggers:
        net = blender_to_sm64_scale / collision_divisor
        _write_entities_inc(
            out_dir / "entities.inc.c",
            level_name,
            triggers,
            scale_factor,
            net,
            sm64_spawn,
        )
        _patch_header_entities(out_dir / "header.h", level_name)
        ld_path = out_dir / "leveldata.c"
        ld_text = ld_path.read_text(encoding="utf-8")
        ent_include = f'#include "levels/{level_name}/entities.inc.c"\n'
        if ent_include not in ld_text:
            ld_path.write_text(ld_text + ent_include, encoding="utf-8")
        _inject_triggers(
            out_dir / "script.c",
            triggers,
            collision_divisor,
            scale_factor,
            blender_to_sm64_scale,
            level_name,
        )

    _write_level_yaml(out_dir / "level.yaml", level_name, skybox_bin)

    (out_dir / "texture.inc.c").write_text("", encoding="utf-8")


_GFX_MAX_CACHE: int = 32


def generate_dl_from_obj(obj_path: Path, out_path: Path, array_name: str, net: float) -> None:
    import io as _io

    raw_verts: list = []
    faces: list = []

    with open(obj_path, encoding="utf-8", errors="replace") as _f:
        for line in _f:
            if line.startswith("v "):
                p = line.split()
                raw_verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("f "):
                p = line.split()[1:]
                idx = [int(pt.split("/")[0]) - 1 for pt in p]
                for i in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[i], idx[i + 1]))

    def _s16(v: float) -> int:
        return max(-32767, min(32767, round(v * net)))

    batches: list = []
    cur_vmap: dict = {}
    cur_verts: list = []
    cur_tris: list = []

    for tri in faces:
        needed = [v for v in tri if v not in cur_vmap]
        if len(cur_verts) + len(needed) > _GFX_MAX_CACHE:
            if cur_verts:
                batches.append((list(cur_verts), list(cur_tris)))
            cur_vmap = {}
            cur_verts = []
            cur_tris = []
            needed = list(tri)
        for v in needed:
            cur_vmap[v] = len(cur_verts)
            cur_verts.append(v)
        cur_tris.append(tuple(cur_vmap[v] for v in tri))

    if cur_verts:
        batches.append((cur_verts, cur_tris))

    all_verts: list = []
    batch_offsets: list = []
    for verts, _ in batches:
        batch_offsets.append(len(all_verts))
        all_verts.extend(verts)

    buf = _io.StringIO()
    buf.write(f"Vtx {array_name}_vtx[{len(all_verts)}] = {{\n")
    for gv in all_verts:
        x, y, z = raw_verts[gv]
        buf.write(f"    {{{{{{{_s16(x)}, {_s16(y)}, {_s16(z)}}}, 0, {{0, 0}}, {{0x80, 0x80, 0x80, 0xFF}}}}}},\n")
    buf.write("};\n\n")

    buf.write(f"Gfx {array_name}_dl[] = {{\n")
    buf.write("    gsDPPipeSync(),\n")
    buf.write("    gsDPSetCombineMode(G_CC_SHADE, G_CC_SHADE),\n")

    for bi, (verts, tris) in enumerate(batches):
        n = len(verts)
        off = batch_offsets[bi]
        buf.write(f"    gsSPVertex({array_name}_vtx + {off}, {n}, 0),\n")
        i = 0
        while i < len(tris):
            if i + 1 < len(tris):
                t0, t1 = tris[i], tris[i + 1]
                buf.write(
                    f"    gsSP2Triangles({t0[0]}, {t0[1]}, {t0[2]}, 0x0,"
                    f" {t1[0]}, {t1[1]}, {t1[2]}, 0x0),\n"
                )
                i += 2
            else:
                t0 = tris[i]
                buf.write(f"    gsSP1Triangle({t0[0]}, {t0[1]}, {t0[2]}, 0),\n")
                i += 1

    buf.write("    gsSPEndDisplayList(),\n")
    buf.write("};\n")

    out_path.write_text(buf.getvalue(), encoding="utf-8")


def convert_moving_platforms(
    triggers: list,
    moving_brushes_dir: Path,
    out_dir: Path,
    level_name: str,
    scale_factor: float,
    net: float,
    script_path: Path,
    leveldata_path: Path,
    header_path: Path,
) -> None:
    import io as _io

    moving_brushes_dir = Path(moving_brushes_dir)
    out_dir = Path(out_dir)
    script_path = Path(script_path)
    leveldata_path = Path(leveldata_path)
    header_path = Path(header_path)

    door_triggers = [t for t in triggers if t.get("type") == "door" and t.get("meshfile")]
    if not door_triggers:
        return

    out_dir.mkdir(parents=True, exist_ok=True)

    plat_inc_lines: list = []
    plat_inc_lines.append('#include <ultra64.h>')
    plat_inc_lines.append('#include "sm64.h"')
    plat_inc_lines.append('#include "game/bhv_moving_platform.h"')
    plat_inc_lines.append('')

    struct_entries: list = []
    model_ids: list = []
    object_macros: list = []
    load_macros: list = []
    _hash_to_model_id: dict = {}
    _hash_to_ref_name: dict = {}
    _next_model_id = 0xE2
    _unique_meshes: list = []

    for idx, t in enumerate(door_triggers):
        meshfile = t["meshfile"]
        obj_path = moving_brushes_dir / meshfile
        if not obj_path.exists():
            continue

        array_name = f"{level_name}_moving_{idx}"
        obj_hash = hashlib.md5(obj_path.read_bytes()).hexdigest()
        if obj_hash in _hash_to_model_id:
            model_id = _hash_to_model_id[obj_hash]
            ref_name = _hash_to_ref_name[obj_hash]
        else:
            if _next_model_id > 0xFF:
                continue
            model_id = _next_model_id
            _next_model_id += 1
            ref_name = array_name
            _hash_to_model_id[obj_hash] = model_id
            _hash_to_ref_name[obj_hash] = ref_name
            _unique_meshes.append((idx, model_id, ref_name, obj_path))

        spawnpos = t.get("spawnpos", t["origin"])
        ox, oy, oz = spawnpos[0], spawnpos[1], spawnpos[2]
        sm_sx = _clamp_s16(round(ox * scale_factor * net))
        sm_sy = _clamp_s16(round(oz * scale_factor * net))
        sm_sz = _clamp_s16(round(-oy * scale_factor * net))

        movedir_str = t.get("movedir", "0 0 0") or "0 0 0"
        movedist = float(t.get("movedist", 0) or 0)
        speed = float(t.get("speed", 100) or 100)
        parts = [float(s) for s in movedir_str.split()]
        pitch_rad = math.radians(parts[0] if len(parts) > 0 else 0.0)
        yaw_rad = math.radians(parts[1] if len(parts) > 1 else 0.0)
        bsp_dx = math.cos(pitch_rad) * math.cos(yaw_rad)
        bsp_dy = math.cos(pitch_rad) * math.sin(yaw_rad)
        bsp_dz = -math.sin(pitch_rad)
        sm64_ex = _clamp_s16(round((ox + bsp_dx * movedist) * scale_factor * net))
        sm64_ey = _clamp_s16(round((oz + bsp_dz * movedist) * scale_factor * net))
        sm64_ez = _clamp_s16(round((-oy - bsp_dy * movedist) * scale_factor * net))

        dist_sm64 = movedist * scale_factor * net
        period = max(1, round(dist_sm64 / max(1.0, speed * scale_factor * net / 30.0)))

        spawnflags = int(t.get("spawnflags", 0) or 0)
        _wait_val = t.get("wait")
        wait_secs = float(_wait_val) if _wait_val is not None else 3.0
        activator = t.get("activator")

        is_use = bool(spawnflags & 256)
        is_touch = activator is not None and not is_use
        is_step = movedist > 0 and not is_use and not is_touch
        mode = 2 if is_use else (1 if is_touch else (3 if is_step else 0))

        if wait_secs == -1.0:
            wait_frames = -1
        else:
            wait_frames = _clamp_s16(round(wait_secs * 30))

        if activator and mode != 0:
            act_mnx = _clamp_s16(round(activator["mins"][0] * scale_factor * net))
            act_mny = _clamp_s16(round(activator["mins"][2] * scale_factor * net))
            act_mnz = _clamp_s16(round(-activator["maxs"][1] * scale_factor * net))
            act_mxx = _clamp_s16(round(activator["maxs"][0] * scale_factor * net))
            act_mxy = _clamp_s16(round(activator["maxs"][2] * scale_factor * net))
            act_mxz = _clamp_s16(round(-activator["mins"][1] * scale_factor * net))
            r_act_mnx, r_act_mxx = min(act_mnx, act_mxx), max(act_mnx, act_mxx)
            r_act_mny, r_act_mxy = min(act_mny, act_mxy), max(act_mny, act_mxy)
            r_act_mnz, r_act_mxz = min(act_mnz, act_mxz), max(act_mnz, act_mxz)
        else:
            r_act_mnx = r_act_mny = r_act_mnz = 0
            r_act_mxx = r_act_mxy = r_act_mxz = 0

        struct_entries.append(
            f"    {{{{{sm_sx}, {sm_sy}, {sm_sz}}}, {{{sm64_ex}, {sm64_ey}, {sm64_ez}}},"
            f" {period}, {wait_frames}, {mode}, {{0, 0, 0}},"
            f" {{{r_act_mnx}, {r_act_mny}, {r_act_mnz}}}, {{{r_act_mxx}, {r_act_mxy}, {r_act_mxz}}},"
            f" {ref_name}_area_1_collision}},"
        )

        beh_param = (idx & 0xFF) << 16
        object_macros.append(
            f"\t\tOBJECT(0x{model_id:02X}, {sm_sx}, {sm_sy}, {sm_sz},"
            f" 0, 0, 0, 0x{beh_param:08X}, bhvCustomMovingPlatform),"
        )
        model_ids.append(model_id)

    for uid_idx, uid_model_id, uid_ref_name, uid_obj_path in _unique_meshes:
        dl_inc = out_dir / f"moving_{uid_idx}.inc.c"
        col_inc = out_dir / f"moving_{uid_idx}_col.inc.c"
        generate_dl_from_obj(uid_obj_path, dl_inc, uid_ref_name, net)
        generate_collision_from_obj(uid_obj_path, col_inc, uid_ref_name, net)
        plat_inc_lines.append(f'#include "levels/{level_name}/moving_{uid_idx}.inc.c"')
        plat_inc_lines.append(f'#include "levels/{level_name}/moving_{uid_idx}_col.inc.c"')
        plat_inc_lines.append('')
        load_macros.append(
            f"\t\tLOAD_MODEL_FROM_DL(0x{uid_model_id:02X}, {uid_ref_name}_dl, LAYER_OPAQUE),"
        )

    if not struct_entries:
        return

    plat_inc_lines.append(f'static const struct LevelMovingPlatform {level_name}_moving_platforms[] = {{')
    plat_inc_lines.extend(struct_entries)
    plat_inc_lines.append('};')
    plat_inc_lines.append('')
    plat_inc_lines.append(f'__attribute__((constructor)) static void s_{level_name}_register_platforms(void) {{')
    plat_inc_lines.append(f'    moving_platform_register({level_name}_moving_platforms);')
    plat_inc_lines.append('}')
    plat_inc_lines.append('')

    (out_dir / "moving_platforms.inc.c").write_text('\n'.join(plat_inc_lines), encoding='utf-8')

    ld_text = leveldata_path.read_text(encoding='utf-8')
    mp_include = f'#include "levels/{level_name}/moving_platforms.inc.c"\n'
    if mp_include not in ld_text:
        leveldata_path.write_text(ld_text + mp_include, encoding='utf-8')

    hdr_text = header_path.read_text(encoding='utf-8')
    mp_hdr = '#include "game/bhv_moving_platform.h"\n'
    extern_decls = ''.join(
        f'extern Gfx {uid_ref_name}_dl[];\n'
        for _, uid_model_id, uid_ref_name, uid_obj_path in _unique_meshes
    )
    block_to_add = ''
    if mp_hdr not in hdr_text:
        block_to_add += mp_hdr
    for line in extern_decls.splitlines(keepends=True):
        if line not in hdr_text:
            block_to_add += line
    if block_to_add:
        hdr_text = hdr_text.rstrip()
        if hdr_text.endswith('#endif'):
            hdr_text = hdr_text[:-6].rstrip() + '\n\n' + block_to_add + '#endif\n'
        else:
            hdr_text += '\n' + block_to_add
        header_path.write_text(hdr_text, encoding='utf-8')

    if not load_macros and not object_macros:
        return

    script_text = script_path.read_text(encoding='utf-8')
    load_block = '\n'.join(load_macros) + '\n'
    obj_block = '\n'.join(object_macros) + '\n'

    script_text = re.sub(
        r'[ \t]*LOAD_MODEL_FROM_DL\(0x[0-9A-Fa-f]+,\s*' + re.escape(level_name) + r'_moving_\d+_dl[^\n]*\n',
        '', script_text,
    )
    script_text = re.sub(
        r'[ \t]*OBJECT\(0x[0-9A-Fa-f]+,[^\n]*bhvCustomMovingPlatform\),\n',
        '', script_text,
    )

    if load_macros:
        script_text = re.sub(
            r'([ \t]*ALLOC_LEVEL_POOL\s*\(\s*\)\s*,[ \t]*\n)',
            r'\1' + load_block,
            script_text, count=1,
        )
    if object_macros:
        script_text = re.sub(
            r'(\s*END_AREA\s*\(\s*\)\s*,)',
            '\n' + obj_block + r'\1',
            script_text, count=1,
        )

    script_path.write_text(script_text, encoding='utf-8')


def convert_sky(
    f64_sky_dir: Path,
    dst_sky_dir: Path,
    level_name: str,
    sky_origin: list,
    sky_scale: float,
    scale_factor: float = 1.0,
    blender_to_sm64_scale: float = 300.0,
    collision_divisor: float = 150.0,
) -> None:
    """Convert Fast64 sky-level output to native SM64-port sky files.

    Writes sky_model.inc.c, sky_camera.inc.h, and sky_geo.inc.c into
    *dst_sky_dir*, then patches the sibling leveldata.c / script.c to
    include / call the sky init function.
    """
    f64_sky_dir = Path(f64_sky_dir)
    dst_sky_dir = Path(dst_sky_dir)
    native_out = dst_sky_dir.parent  # contains the main level's leveldata.c/script.c

    dst_sky_dir.mkdir(parents=True, exist_ok=True)

    # 1. Fix model UVs and write sky_model.inc.c
    model_src = f64_sky_dir / "model.inc.c"
    if not model_src.exists():
        model_src = f64_sky_dir / "area_2" / "1" / "model.inc.c"
    if model_src.exists():
        _fix_model_uvs(model_src, dst_sky_dir / "sky_model.inc.c")
    else:
        (dst_sky_dir / "sky_model.inc.c").write_text("", encoding="utf-8")

    # 2. Parse display list names from Fast64 sky geo.inc.c
    geo_src = f64_sky_dir / "area_2" / "geo.inc.c"
    dl_names: list = []
    if geo_src.exists():
        geo_text = geo_src.read_text(encoding="utf-8")
        dl_names = re.findall(
            r'GEO_DISPLAY_LIST\(\s*\w+\s*,\s*(\w+)\s*\)', geo_text
        )

    # 3. Compute SM64 sky origin (Source world coords → SM64 units)
    #    The sky geometry in bsp2obj is exported scaled by (scale_factor * sky_scale),
    #    so the origin must also be multiplied by sky_scale to match the geometry's
    #    coordinate space.
    ox, oy, oz = sky_origin
    net = blender_to_sm64_scale / collision_divisor
    sm64_x = round(ox * scale_factor * net * sky_scale)
    sm64_y = round(oz * scale_factor * net * sky_scale)   # Source Z → SM64 Y
    sm64_z = round(-oy * scale_factor * net * sky_scale)  # Source Y (negated) → SM64 Z

    # 4. Write sky_camera.inc.h
    guard = f"SKY3D_CAMERA_{level_name.upper()}_H"
    cam_h = (
        f"#ifndef {guard}\n"
        f"#define {guard}\n\n"
        f"#define SKY3D_ORIGIN_X {sm64_x}\n"
        f"#define SKY3D_ORIGIN_Y {sm64_y}\n"
        f"#define SKY3D_ORIGIN_Z {sm64_z}\n"
        f"#define SKY3D_SCALE    {int(sky_scale)}\n\n"
        f"#ifndef __ASSEMBLER__\n"
        f"#include <PR/gbi.h>\n"
        f"#endif\n\n"
        f"#endif /* {guard} */\n"
    )
    (dst_sky_dir / "sky_camera.inc.h").write_text(cam_h, encoding="utf-8")

    # 5. Write sky_geo.inc.c
    geo_lines = [
        f'#include "levels/{level_name}/sky/sky_model.inc.c"',
        f'#include "levels/{level_name}/sky/sky_camera.inc.h"',
        "",
        "/* forward declaration — defined in src/game/skybox3d.c */",
        "void sky3d_register(Gfx *dl, s32 ox, s32 oy, s32 oz, s32 scale);",
        "",
        "static Gfx sky3d_display_list[] = {",
    ]
    # Put cubemap DLs first so they render as the far background before BSP sky geometry.
    # Without this ordering, BSP sky geometry writes depth first and the cubemap
    # (200 000 units away) fails the Z-test and is invisible.
    cubemap_dls = [d for d in dl_names if "_skybox_" in d and "_tides" in d]
    other_dls   = [d for d in dl_names if d not in cubemap_dls]
    for dl in cubemap_dls + other_dls:
        geo_lines.append(f"    gsSPDisplayList({dl}),")
    geo_lines += [
        "    gsDPNoOpTag(0x534B5944u),  /* sky depth-clear marker (SKYD) */",
        "    gsSPEndDisplayList(),",
        "};",
        "",
        f"s32 {level_name}_sky_init(UNUSED s16 arg, UNUSED s32 unused) {{",
        f"    sky3d_register(sky3d_display_list,"
        f" SKY3D_ORIGIN_X, SKY3D_ORIGIN_Y, SKY3D_ORIGIN_Z, SKY3D_SCALE);",
        "    return 0;",
        "}",
        "",
    ]
    (dst_sky_dir / "sky_geo.inc.c").write_text("\n".join(geo_lines), encoding="utf-8")

    # 6b. Add forward declaration to header.h so script.c can reference sky_init
    hdr_path = native_out / "header.h"
    if hdr_path.exists():
        hdr_text = hdr_path.read_text(encoding="utf-8")
        sky_decl = f"s32 {level_name}_sky_init(s16, s32);\n"
        if sky_decl not in hdr_text:
            # Insert before the final #endif
            hdr_text = hdr_text.rstrip()
            if hdr_text.endswith("#endif"):
                hdr_text = hdr_text[:-len("#endif")].rstrip() + "\n\n" + sky_decl + "\n#endif\n"
            else:
                hdr_text += "\n" + sky_decl
            hdr_path.write_text(hdr_text, encoding="utf-8")

    # 6. Append sky include to native leveldata.c
    ld_path = native_out / "leveldata.c"
    if ld_path.exists():
        ld_text = ld_path.read_text(encoding="utf-8")
        sky_include = f'#include "levels/{level_name}/sky/sky_geo.inc.c"\n'
        if sky_include not in ld_text:
            ld_path.write_text(ld_text + sky_include, encoding="utf-8")

    # 7. Inject sky_init CALL into native script.c AFTER lvl_init_or_update (init call)
    #    so that init_level() runs first (clearing any stale sky state before sky is registered)
    sc_path = native_out / "script.c"
    if sc_path.exists():
        sc_text = sc_path.read_text(encoding="utf-8")
        sky_call = f"\tCALL(0, {level_name}_sky_init),\n"
        if sky_call not in sc_text:
            sc_text = re.sub(
                r'([ \t]*CALL\s*\(\s*0\s*,\s*lvl_init_or_update\s*\)\s*,[ \t]*\n)',
                r'\1' + sky_call,
                sc_text,
            )
            sc_path.write_text(sc_text, encoding="utf-8")
