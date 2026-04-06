import argparse


def build_parser():
    p = argparse.ArgumentParser(
        prog="cssmap2sm64",
        description="Convert a CS:S .bsp map to an SM64 decomp level"
    )
    p.add_argument("bsp", help="Input .bsp file")
    p.add_argument("--config", default="pipeline.json", help="Path to pipeline.json")
    p.add_argument("--output", default="out", help="Output working directory")
    p.add_argument("--keep-tools", action="store_true",
                   help="Include tool-textured faces in OBJ output")
    p.add_argument("--no-blend", action="store_true",
                   help="Stop after OBJ export (skip Blender/Fast64 stage)")
    p.add_argument("--collision-only", action="store_true",
                   help="Regenerate and deploy only collision.inc.c (skip Blender, requires existing deployment)")
    return p
