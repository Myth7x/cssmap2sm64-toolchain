import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent.parent / "blender" / "blend_export.py"


def run(blender, obj_path, textures_dir, output_dir, level_name, area_id, scale, spawn=(0.0, 0.0, 0.0), materials_json=None, background="ABOVE_CLOUDS", decimate_ratio=1.0, props_json=None, bsp_scale=1.0, env_json=None, sky_obj=None, sky_camera_json=None, sky_cube_obj=None, triggers_json=None):
    cmd = [
        blender,
        "--background",
        "--python", str(_SCRIPT),
        "--",
        "--obj", obj_path,
        "--textures", textures_dir,
        "--output", output_dir,
        "--level-name", level_name,
        "--area-id", str(area_id),
        "--scale", str(scale),
        f"--spawn={spawn[0]},{spawn[1]},{spawn[2]}",
        "--background-sky", background,
        "--decimate-ratio", str(decimate_ratio),
        "--bsp-scale", str(bsp_scale),
    ]
    if materials_json is not None:
        cmd += ["--materials-json", str(materials_json)]
    if props_json is not None:
        cmd += ["--props-json", str(props_json)]
    if env_json is not None:
        cmd += ["--env-json", str(env_json)]
    if sky_obj is not None:
        cmd += ["--sky-obj", str(sky_obj)]
    if sky_camera_json is not None:
        cmd += ["--sky-camera-json", str(sky_camera_json)]
    if sky_cube_obj is not None:
        cmd += ["--sky-cube-obj", str(sky_cube_obj)]
    if triggers_json is not None:
        cmd += ["--triggers-json", str(triggers_json)]
    subprocess.run(cmd, check=True)
