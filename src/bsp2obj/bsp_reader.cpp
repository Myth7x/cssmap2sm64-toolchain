#include "bsp_reader.h"

#include <cstring>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

static constexpr int32_t VBSP_IDENT = ('P' << 24) | ('S' << 16) | ('B' << 8) | 'V';

static std::vector<uint8_t> read_file_bytes(const std::string& path) {
    std::ifstream f(path, std::ios::binary | std::ios::ate);
    if (!f) throw std::runtime_error("Cannot open BSP: " + path);
    auto sz = f.tellg();
    f.seekg(0);
    std::vector<uint8_t> buf(static_cast<size_t>(sz));
    f.read(reinterpret_cast<char*>(buf.data()), sz);
    return buf;
}

template<typename T>
static std::vector<T> lump_as(const std::vector<uint8_t>& data, const BSPLump& lump) {
    size_t count = static_cast<size_t>(lump.filelen) / sizeof(T);
    std::vector<T> out(count);
    if (count > 0)
        std::memcpy(out.data(), data.data() + lump.fileofs, count * sizeof(T));
    return out;
}

BSPData load_bsp(const std::string& path) {
    auto data = read_file_bytes(path);
    if (data.size() < sizeof(BSPHeader))
        throw std::runtime_error("File too small to be a BSP");

    BSPHeader hdr;
    std::memcpy(&hdr, data.data(), sizeof(hdr));

    if (hdr.ident != VBSP_IDENT)
        throw std::runtime_error("Not a VBSP file (bad magic)");
    if (hdr.version < 19 || hdr.version > 21)
        throw std::runtime_error("Unsupported BSP version: " + std::to_string(hdr.version));

    BSPData bsp;

    bsp.planes    = lump_as<BSPPlane>   (data, hdr.lumps[LUMP_PLANES]);
    bsp.vertices  = lump_as<BSPVertex>  (data, hdr.lumps[LUMP_VERTICES]);
    bsp.edges     = lump_as<BSPEdge>    (data, hdr.lumps[LUMP_EDGES]);
    bsp.surfedges = lump_as<int32_t>    (data, hdr.lumps[LUMP_SURFEDGES]);
    bsp.faces     = lump_as<BSPFace>    (data, hdr.lumps[LUMP_FACES]);
    bsp.texinfos  = lump_as<BSPTexInfo> (data, hdr.lumps[LUMP_TEXINFO]);
    bsp.texdatas  = lump_as<BSPTexData> (data, hdr.lumps[LUMP_TEXDATA]);
    bsp.brushes   = lump_as<BSPBrush>   (data, hdr.lumps[LUMP_BRUSHES]);
    bsp.brushsides = lump_as<BSPBrushSide>(data, hdr.lumps[LUMP_BRUSHSIDES]);

    {
        const auto& el = hdr.lumps[LUMP_ENTITIES];
        bsp.entities.assign(
            reinterpret_cast<const char*>(data.data() + el.fileofs),
            static_cast<size_t>(el.filelen)
        );
    }

    {
        const auto& tbl = hdr.lumps[LUMP_TEXDATA_STRING_TABLE];
        const auto& dat = hdr.lumps[LUMP_TEXDATA_STRING_DATA];
        size_t n = static_cast<size_t>(tbl.filelen) / sizeof(int32_t);
        bsp.texnames.resize(n);
        for (size_t i = 0; i < n; ++i) {
            int32_t off;
            std::memcpy(&off, data.data() + tbl.fileofs + i * 4, 4);
            const char* s = reinterpret_cast<const char*>(data.data() + dat.fileofs + off);
            bsp.texnames[i] = s;
        }
    }

    return bsp;
}
