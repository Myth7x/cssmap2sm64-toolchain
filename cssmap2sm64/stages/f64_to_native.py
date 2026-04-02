import re
import shutil
from pathlib import Path

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


def _write_script(src: Path, dst: Path) -> None:
    text = src.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    result = []
    inside_area = False
    area_depth = 0
    for line in lines:
        stripped = line.strip()
        if re.match(r'AREA\s*\(', stripped):
            inside_area = True
            area_depth = 1
        elif inside_area:
            if re.match(r'AREA\s*\(', stripped):
                area_depth += 1
            elif stripped == "END_AREA(),":
                area_depth -= 1
                if area_depth == 0:
                    inside_area = False
            if inside_area and re.match(r'MARIO_POS\s*\(', stripped):
                continue
        result.append(line)
    dst.write_text("".join(result), encoding="utf-8")


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


def convert(fast64_dir: Path, out_dir: Path, level_name: str) -> None:
    fast64_dir = Path(fast64_dir)
    out_dir = Path(out_dir)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    areas1 = out_dir / "areas" / "1"
    areas1.mkdir(parents=True)
    (areas1 / "1").mkdir()

    for fname in ("collision.inc.c", "geo.inc.c", "macro.inc.c"):
        shutil.copy2(fast64_dir / "area_1" / fname, areas1 / fname)

    shutil.copy2(fast64_dir / "model.inc.c", areas1 / "1" / "model.inc.c")

    _write_header(
        fast64_dir / "header.inc.h",
        out_dir / "header.h",
        level_name,
    )

    _write_geo(fast64_dir / "geo.inc.c", out_dir / "geo.c", level_name)

    _write_leveldata(out_dir / "leveldata.c", level_name)

    _write_script(fast64_dir / "script.c", out_dir / "script.c")

    _write_level_yaml(out_dir / "level.yaml", level_name)

    (out_dir / "texture.inc.c").write_text("", encoding="utf-8")
