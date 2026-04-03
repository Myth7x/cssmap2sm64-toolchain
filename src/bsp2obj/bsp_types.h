#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <vector>

#pragma pack(push, 1)

struct BSPLump {
    int32_t fileofs;
    int32_t filelen;
    int32_t version;
    uint8_t fourCC[4];
};

struct BSPHeader {
    int32_t ident;
    int32_t version;
    BSPLump lumps[64];
    int32_t mapRevision;
};

struct BSPPlane {
    float normal[3];
    float dist;
    int32_t type;
};

struct BSPVertex {
    float x, y, z;
};

struct BSPEdge {
    uint16_t v[2];
};

struct BSPFace {
    uint16_t planenum;
    uint8_t side;
    uint8_t onNode;
    int32_t firstedge;
    int16_t numedges;
    int16_t texinfo;
    int16_t dispInfo;
    int16_t surfaceFogVolumeID;
    uint8_t styles[4];
    int32_t lightofs;
    float area;
    int32_t LightmapTextureMinsInLuxels[2];
    int32_t LightmapTextureSizeInLuxels[2];
    int32_t origFace;
    uint16_t numPrims;
    uint16_t firstPrimID;
    uint32_t smoothingGroups;
};

struct BSPTexInfo {
    float textureVecs[2][4];
    float lightmapVecs[2][4];
    int32_t flags;
    int32_t texdata;
};

struct BSPTexData {
    float reflectivity[3];
    int32_t nameStringTableID;
    int32_t width;
    int32_t height;
    int32_t view_width;
    int32_t view_height;
};

struct BSPBrush {
    int32_t firstside;
    int32_t numsides;
    int32_t contents;
};

struct BSPBrushSide {
    uint16_t planenum;
    int16_t texinfo;
    int16_t dispinfo;
    int16_t bevel;
};

struct BSPDispInfo {
    float   startPosition[3];  // 12 bytes
    int32_t dispVertStart;     //  4 bytes
    int32_t dispTriStart;      //  4 bytes
    int32_t power;             //  4 bytes
    uint8_t _unused[176 - 24]; // pad to 176
};
static_assert(sizeof(BSPDispInfo) == 176, "BSPDispInfo size mismatch");

struct BSPDispVert {
    float vec[3];   // displacement direction
    float dist;     // displacement magnitude
    float alpha;    // blend alpha
};
static_assert(sizeof(BSPDispVert) == 20, "BSPDispVert size mismatch");

#pragma pack(pop)

static constexpr int LUMP_ENTITIES   = 0;
static constexpr int LUMP_PLANES     = 1;
static constexpr int LUMP_TEXDATA    = 2;
static constexpr int LUMP_VERTICES   = 3;
static constexpr int LUMP_NODES      = 5;
static constexpr int LUMP_TEXINFO    = 6;
static constexpr int LUMP_FACES      = 7;
static constexpr int LUMP_EDGES      = 12;
static constexpr int LUMP_SURFEDGES  = 13;
static constexpr int LUMP_BRUSHES    = 18;
static constexpr int LUMP_BRUSHSIDES = 19;
static constexpr int LUMP_DISPINFO   = 26;
static constexpr int LUMP_DISP_VERTS = 33;
static constexpr int LUMP_TEXDATA_STRING_TABLE = 44;
static constexpr int LUMP_TEXDATA_STRING_DATA  = 43;

static constexpr int CONTENTS_SOLID     = 0x1;
static constexpr int CONTENTS_WINDOW    = 0x2;
static constexpr int CONTENTS_GRATE     = 0x8;
static constexpr int CONTENTS_DETAIL    = 0x8000000;
static constexpr int CONTENTS_TRANSLUCENT = 0x20000;
static constexpr int SURF_NODRAW        = 0x80;
static constexpr int SURF_SKY          = 0x4;
static constexpr int SURF_SKY2D        = 0x2;
static constexpr int SURF_HINT         = 0x100;
static constexpr int SURF_SKIP         = 0x200;
static constexpr int SURF_TRIGGER      = 0x40;
static constexpr int SURF_NOLIGHT      = 0x400;

struct BSPData {
    std::vector<BSPPlane>    planes;
    std::vector<BSPVertex>   vertices;
    std::vector<BSPEdge>     edges;
    std::vector<int32_t>     surfedges;
    std::vector<BSPFace>     faces;
    std::vector<BSPTexInfo>  texinfos;
    std::vector<BSPTexData>  texdatas;
    std::vector<std::string> texnames;
    std::vector<BSPBrush>    brushes;
    std::vector<BSPBrushSide> brushsides;
    std::vector<BSPDispInfo>  dispinfos;
    std::vector<BSPDispVert>  dispverts;
    std::string              entities;
};
