import re
import struct


def _parse_light_str(s, ref_intensity=200.0):
    parts = s.strip().split()
    if len(parts) < 3:
        return (1.0, 1.0, 1.0)
    r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
    if r < 0 or g < 0 or b < 0:
        return None
    intensity = float(parts[3]) if len(parts) >= 4 else ref_intensity
    scale = intensity / ref_intensity
    raw = (r / 255.0 * scale, g / 255.0 * scale, b / 255.0 * scale)
    m = max(raw)
    if m > 1.0:
        inv = 1.0 / m
        return (raw[0] * inv, raw[1] * inv, raw[2] * inv)
    return raw


def read_env(bsp_path):
    """
    Parse light_environment entity from BSP lump 0.
    Returns dict with:
      sun_color       (r, g, b)  0-1 normalized
      ambient_color   (r, g, b)  0-1 normalized
      sun_pitch       float  degrees, Source convention (negative = above horizon)
      sun_yaw         float  degrees, Source convention (0=east/+X, 90=north/+Y)
    or None if no light_environment found.
    """
    with open(bsp_path, "rb") as f:
        f.read(8)
        lump_table = f.read(64 * 16)
    fileofs, filelen = struct.unpack_from("<ii", lump_table, 0 * 16)
    with open(bsp_path, "rb") as f:
        f.seek(fileofs)
        entities = f.read(filelen).decode("utf-8", errors="replace")

    for block in re.split(r'(?<=\})\s*(?=\{)', entities):
        if '"classname" "light_environment"' not in block:
            continue

        def get(key, default=""):
            m = re.search(r'"' + re.escape(key) + r'"\s+"([^"]*)"', block, re.IGNORECASE)
            return m.group(1).strip() if m else default

        sun_str = get("_light", "255 255 255 200")
        amb_str = get("_ambient", "128 128 128 200")
        angles_str = get("angles", "0 270 0")
        pitch_str = get("pitch", "")

        angles_parts = angles_str.split()
        yaw = float(angles_parts[1]) if len(angles_parts) >= 2 else 270.0

        if pitch_str:
            pitch = float(pitch_str)
        elif len(angles_parts) >= 1:
            pitch = float(angles_parts[0])
        else:
            pitch = -45.0

        sun_color = _parse_light_str(sun_str)
        amb_color = _parse_light_str(amb_str)

        if sun_color is None:
            sun_color = (1.0, 1.0, 1.0)
        if amb_color is None:
            amb_color = (0.5, 0.5, 0.5)

        return {
            "sun_color": list(sun_color),
            "ambient_color": list(amb_color),
            "sun_pitch": pitch,
            "sun_yaw": yaw,
        }

    return None
