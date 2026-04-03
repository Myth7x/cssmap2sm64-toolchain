import io
import os
import struct
import zipfile
from pathlib import Path


def extract_pak(bsp_path, out_dir):
    with open(bsp_path, "rb") as f:
        magic = f.read(4)
        if magic != b"VBSP":
            raise ValueError(f"Not a valid BSP file: {bsp_path}")
        f.read(4)
        lump_table = f.read(64 * 16)
        offset, length = struct.unpack_from("<ii", lump_table, 40 * 16)
        f.seek(offset)
        pak_data = f.read(length)

    os.makedirs(out_dir, exist_ok=True)

    zf = zipfile.ZipFile(io.BytesIO(pak_data))
    zf.extractall(out_dir)

    names = zf.namelist()
    vtf_paths = [
        str(Path(out_dir) / name)
        for name in names
        if name.lower().endswith(".vtf")
    ]
    vmt_paths = [
        str(Path(out_dir) / name)
        for name in names
        if name.lower().endswith(".vmt")
    ]
    return vtf_paths, vmt_paths
