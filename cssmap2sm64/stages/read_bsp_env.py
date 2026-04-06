import math
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
    Parse light_environment and env_fog_controller entities from BSP lump 0.
    Returns dict with:
      sun_color       (r, g, b)  0-1 normalized
      ambient_color   (r, g, b)  0-1 normalized
      sun_pitch       float  degrees, Source convention (negative = above horizon)
      sun_yaw         float  degrees, Source convention (0=east/+X, 90=north/+Y)
      fog             dict with fog_color, fog_start, fog_end, fog_max_density (optional)
    or None if no light_environment found.
    """
    with open(bsp_path, "rb") as f:
        f.read(8)
        lump_table = f.read(64 * 16)
    fileofs, filelen = struct.unpack_from("<ii", lump_table, 0 * 16)
    with open(bsp_path, "rb") as f:
        f.seek(fileofs)
        entities = f.read(filelen).decode("utf-8", errors="replace")

    blocks = re.split(r'(?<=\})\s*(?=\{)', entities)

    light_result = None
    fog_result = None

    for block in blocks:
        if light_result is None and '"classname" "light_environment"' in block:
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

            light_result = {
                "sun_color": list(sun_color),
                "ambient_color": list(amb_color),
                "sun_pitch": pitch,
                "sun_yaw": yaw,
            }

        if fog_result is None and '"classname" "env_fog_controller"' in block:
            def get_fog(key, default=""):
                m = re.search(r'"' + re.escape(key) + r'"\s+"([^"]*)"', block, re.IGNORECASE)
                return m.group(1).strip() if m else default

            if get_fog("fogenable", "0") == "1":
                raw_color = get_fog("fogcolor", "128 128 128").split()
                try:
                    fr, fg, fb = int(raw_color[0]) / 255.0, int(raw_color[1]) / 255.0, int(raw_color[2]) / 255.0
                except (ValueError, IndexError):
                    fr, fg, fb = 0.5, 0.5, 0.5
                try:
                    fog_start = float(get_fog("fogstart", "512"))
                    fog_end = float(get_fog("fogend", "2048"))
                    fog_max_density = float(get_fog("fogmaxdensity", "1.0") or "1.0")
                except ValueError:
                    fog_start, fog_end, fog_max_density = 512.0, 2048.0, 1.0
                fog_result = {
                    "fog_color": [fr, fg, fb],
                    "fog_start": fog_start,
                    "fog_end": fog_end,
                    "fog_max_density": fog_max_density,
                }

        if light_result is not None and fog_result is not None:
            break

    if light_result is None:
        return None

    if fog_result is not None:
        light_result["fog"] = fog_result

    sky_cam_result = None
    for block in blocks:
        if '"classname" "sky_camera"' in block:
            def get_sc(key, default=""):
                m = re.search(r'"' + re.escape(key) + r'"\s+"([^"]*)"', block, re.IGNORECASE)
                return m.group(1).strip() if m else default
            origin_str = get_sc("origin", "0 0 0")
            scale_str  = get_sc("scale", "16")
            try:
                ox, oy, oz = [float(v) for v in origin_str.split()]
            except ValueError:
                ox, oy, oz = 0.0, 0.0, 0.0
            try:
                sky_scale = float(scale_str)
            except ValueError:
                sky_scale = 16.0
            sky_cam_result = {"origin": [ox, oy, oz], "scale": sky_scale}
            break

    if sky_cam_result is not None:
        light_result["sky_camera"] = sky_cam_result

    point_lights = []
    for block in blocks:
        cn_m = re.search(r'"classname"\s+"([^"]*)"', block, re.IGNORECASE)
        if cn_m is None:
            continue
        cn = cn_m.group(1).lower()
        if cn not in ("light", "light_spot"):
            continue

        def get_pl(key, default=""):
            pm = re.search(r'"' + re.escape(key) + r'"\s+"([^"]*)"', block, re.IGNORECASE)
            return pm.group(1).strip() if pm else default

        if get_pl("style", "0") != "0":
            continue

        origin_str = get_pl("origin", "0 0 0")
        try:
            ox, oy, oz = [float(v) for v in origin_str.split()]
        except ValueError:
            continue

        light_str = get_pl("_light", "255 255 255 200")
        parts = light_str.strip().split()
        try:
            lr, lg, lb = int(parts[0]) / 255.0, int(parts[1]) / 255.0, int(parts[2]) / 255.0
            raw_intensity = float(parts[3]) if len(parts) >= 4 else 200.0
        except (ValueError, IndexError):
            continue

        try:
            dist = float(get_pl("distance", "0") or "0")
            kq   = float(get_pl("_quadratic_attn", "0") or "0")
            kl   = float(get_pl("_linear_attn", "0") or "0")
        except ValueError:
            dist, kq, kl = 0.0, 0.0, 0.0

        if dist > 0:
            radius_bsp = dist
        elif kq > 1e-9:
            radius_bsp = math.sqrt(raw_intensity / (kq * 0.05))
        elif kl > 1e-9:
            radius_bsp = raw_intensity / (kl * 0.05)
        else:
            radius_bsp = 512.0

        point_lights.append({
            "origin": [ox, oy, oz],
            "color": [lr, lg, lb],
            "intensity": raw_intensity / 200.0,
            "radius_bsp": radius_bsp,
        })

    point_lights.sort(key=lambda pl: pl["intensity"], reverse=True)
    if point_lights:
        light_result["point_lights"] = point_lights[:8]

    return light_result
