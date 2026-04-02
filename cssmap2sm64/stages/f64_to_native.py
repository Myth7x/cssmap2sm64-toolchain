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
        + f"\nextern const LevelScript level_{level_name}_entry[];\n"
        + f"\nextern const LevelScript level_{level_name}_entry[];\n"
        + f"\n#endif\n"
    )
    dst.write_text(out, encoding="utf-8")


def _write_geo(src_inc: Path, dst: Path, level_name: str) -> None:
    content = _GEO_BOILERPLATE
    content += f'#include "levels/{level_name}/header.h"\n\n'
    content += f'#include "levels/{level_name}/areas/1/geo.inc.c"\n'
    dst.write_text(content, encoding="utf-8")


def _write_leveldata(dst: Path, level_name: str) -> None:
    content = _LEVELDATA_BOILERPLATE
    content += f'#include "levels/{level_name}/texture.inc.c"\n'
    content += f'#include "levels/{level_name}/areas/1/1/model.inc.c"\n'
    content += f'#include "levels/{level_name}/areas/1/collision.inc.c"\n'
    content += f'#include "levels/{level_name}/areas/1/macro.inc.c"\n'
    dst.write_text(content, encoding="utf-8")


def _scale_collision(src: Path, dst: Path, divisor: int) -> None:
    text = src.read_text(encoding="utf-8")
    def _scale_vertex(m: re.Match) -> str:
        x = round(int(m.group(1)) / divisor)
        y = round(int(m.group(2)) / divisor)
        z = round(int(m.group(3)) / divisor)
        return f"COL_VERTEX({x}, {y}, {z})"
    result = re.sub(
        r'COL_VERTEX\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\)',
        _scale_vertex,
        text,
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



def _write_level_yaml(dst: Path, level_name: str) -> None:
    content = (
        f"short-name: {level_name}\n"
        f"full-name: {level_name}\n"
        f"texture-file: []\n"
        f"area-count: 1\n"
        f"objects: []\n"
        f"shared-path: []\n"
        f"skybox-bin: water\n"
        f"texture-bin: generic\n"
        f"effects: false\n"
        f"actor-bins: []\n"
        f"common-bin: []\n"
    )
    dst.write_text(content, encoding="utf-8")


def convert(
    fast64_dir: Path,
    out_dir: Path,
    level_name: str,
    collision_divisor: int = 150,
    sm64_spawn: Optional[Tuple[int, int, int]] = None,
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
    for fname in ("geo.inc.c", "macro.inc.c"):
        shutil.copy2(fast64_dir / "area_1" / fname, areas1 / fname)

    shutil.copy2(fast64_dir / "model.inc.c", areas1 / "1" / "model.inc.c")

    _write_header(
        fast64_dir / "header.inc.h",
        out_dir / "header.h",
        level_name,
    )

    _write_geo(fast64_dir / "geo.inc.c", out_dir / "geo.c", level_name)

    _write_leveldata(out_dir / "leveldata.c", level_name), 

    _write_script(fast64_dir / "script.c", out_dir / "script.c", sm64_spawn)

    _write_level_yaml(out_dir / "level.yaml", level_name)

    (out_dir / "texture.inc.c").write_text("", encoding="utf-8")
