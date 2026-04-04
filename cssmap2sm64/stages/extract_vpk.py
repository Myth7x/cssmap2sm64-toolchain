import os
import struct
from pathlib import Path


def _read_cstr(data, pos):
    end = data.index(b'\x00', pos)
    return data[pos:end].decode('utf-8', errors='replace'), end + 1


def build_vpk_index(vpk_dir_path):
    """
    Parse a *_dir.vpk file and return:
      slug → {'vpk': path, 'arch': idx, 'off': offset, 'len': length, 'preload': bytes, 'orig': str}
    where slug = path-within-materials, slashes→underscores, no extension.
    Only material VTF and VMT entries are indexed.
    """
    vpk_dir_path = str(vpk_dir_path)
    try:
        with open(vpk_dir_path, 'rb') as f:
            data = f.read()
    except OSError:
        return {}

    if len(data) < 12:
        return {}

    magic, version, tree_size = struct.unpack_from('<III', data, 0)
    if magic != 0x55AA1234:
        return {}

    if version == 1:
        hdr_size = 12
    elif version == 2:
        hdr_size = 28
    else:
        return {}

    pos = hdr_size
    tree_end = hdr_size + tree_size
    embedded_base = tree_end

    index = {}
    while pos < tree_end:
        try:
            ext, pos = _read_cstr(data, pos)
        except (ValueError, IndexError):
            break
        if not ext:
            break

        while pos < tree_end:
            try:
                vpath, pos = _read_cstr(data, pos)
            except (ValueError, IndexError):
                break
            if not vpath:
                break

            while pos < tree_end:
                try:
                    fname, pos = _read_cstr(data, pos)
                except (ValueError, IndexError):
                    break
                if not fname:
                    break

                if pos + 18 > len(data):
                    break
                crc32, preload_sz, arch_idx, entry_off, entry_len, term = \
                    struct.unpack_from('<IHHIIH', data, pos)
                pos += 18

                preload = b''
                if preload_sz > 0 and pos + preload_sz <= len(data):
                    preload = data[pos:pos + preload_sz]
                    pos += preload_sz

                lext = ext.lower()
                if lext not in ('vtf', 'vmt'):
                    continue

                if vpath == ' ':
                    orig = f'{fname}.{ext}'
                else:
                    orig = f'{vpath}/{fname}.{ext}'

                lorig = orig.lower()
                if not lorig.startswith('materials/'):
                    continue

                rel = lorig[len('materials/'):]
                no_ext = rel[:-(len(lext) + 1)]
                slug = no_ext.replace('/', '_').replace('\\', '_')

                actual_off = (embedded_base + entry_off) if arch_idx == 0x7fff else entry_off
                index[f"{slug}.{lext}"] = {
                    'vpk': vpk_dir_path,
                    'arch': arch_idx,
                    'off': actual_off,
                    'len': entry_len,
                    'preload': preload,
                    'orig': orig,
                }

    return index


def build_game_index(game_path):
    """Build a combined VPK index from all *_dir.vpk files under game_path (recursive)."""
    combined = {}
    game_dir = Path(game_path)
    if not game_dir.is_dir():
        return combined
    for vpk_dir in sorted(game_dir.rglob('*_dir.vpk')):
        try:
            idx = build_vpk_index(vpk_dir)
            combined.update(idx)
        except Exception:
            pass
    return combined


def extract_vtf(entry, out_path):
    """Extract a single VTF/VMT from a VPK entry dict to out_path."""
    arch_idx = entry['arch']
    offset   = entry['off']
    length   = entry['len']
    preload  = entry['preload']
    vpk_path = entry['vpk']

    if arch_idx == 0x7fff:
        with open(vpk_path, 'rb') as f:
            f.seek(offset)
            payload = preload + f.read(length)
    else:
        data_path = vpk_path.replace('_dir.vpk', f'_{arch_idx:03d}.vpk')
        if not os.path.exists(data_path):
            return False
        with open(data_path, 'rb') as f:
            f.seek(offset)
            payload = preload + f.read(length)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'wb') as f:
        f.write(payload)
    return True


def extract_materials_from_vpk(game_path, material_slugs, tex_dir):
    """
    For each slug (e.g. 'brick_brickwall014a'), extract the corresponding
    VTF (and VMT) to tex_dir/materials/<original_path>.
    Returns list of VTF paths that were successfully extracted.
    """
    if not game_path or not Path(game_path).is_dir():
        return []

    print(f"  Building VPK index from {game_path} ...", flush=True)
    index = build_game_index(game_path)
    if not index:
        print("  [warn] VPK index is empty — check game_path", flush=True)
        return []

    vtf_out = []
    missing = 0
    for slug in material_slugs:
        sl = slug.lower()
        found_any = False
        for ext in ('vtf', 'vmt'):
            entry = index.get(f"{sl}.{ext}")
            if entry is None:
                continue
            found_any = True
            orig = entry['orig']
            out = os.path.join(tex_dir, orig)
            if os.path.exists(out):
                if ext == 'vtf':
                    vtf_out.append(out)
                continue
            if extract_vtf(entry, out):
                if ext == 'vtf':
                    vtf_out.append(out)
            else:
                found_any = False
        if not found_any:
            missing += 1

    print(f"  VPK: extracted {len(vtf_out)} VTFs ({missing} slugs not found in VPK)", flush=True)
    return vtf_out
