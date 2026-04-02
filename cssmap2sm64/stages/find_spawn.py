import re
from pathlib import Path

_SPAWN_CLASSNAMES = [
    "info_player_counterterrorist",
    "info_player_terrorist",
    "info_player_start",
]

_ENTITY_RE = re.compile(r'\{[^{}]*\}', re.DOTALL)
_CLASSNAME_RE = re.compile(r'"classname"\s+"([^"]+)"')
_ORIGIN_RE = re.compile(r'"origin"\s+"([^"]+)"')


def find_spawn(vmf_path: str):
    text = Path(vmf_path).read_text(encoding="utf-8", errors="replace")
    for block in _ENTITY_RE.finditer(text):
        block_text = block.group(0)
        cm = _CLASSNAME_RE.search(block_text)
        if cm is None:
            continue
        if cm.group(1) not in _SPAWN_CLASSNAMES:
            continue
        om = _ORIGIN_RE.search(block_text)
        if om is None:
            continue
        parts = om.group(1).split()
        if len(parts) == 3:
            return float(parts[0]), float(parts[1]), float(parts[2])
    return None
