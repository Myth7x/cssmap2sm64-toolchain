#define STB_IMAGE_WRITE_IMPLEMENTATION
#include "stb_image_write.h"

#include <VTFFile.h>

#include <cstdio>
#include <cstdlib>

int main(int argc, char* argv[]) {
    if (argc != 3) {
        std::fprintf(stderr, "Usage: vtf2png <input.vtf> <output.png>\n");
        return 1;
    }

    const char* vtf_path = argv[1];
    const char* png_path  = argv[2];

    VTFLib::CVTFFile vtf;
    if (!vtf.Load(vtf_path)) {
        std::fprintf(stderr, "Failed to load: %s\n", vtf_path);
        return 1;
    }

    vlUInt w   = vtf.GetWidth();
    vlUInt h   = vtf.GetHeight();
    VTFImageFormat fmt = vtf.GetFormat();

    vlByte* raw = vtf.GetData(0, 0, 0, 0);

    vlUInt rgba_size = w * h * 4;
    vlByte* rgba = static_cast<vlByte*>(std::malloc(rgba_size));
    if (!rgba) {
        std::fprintf(stderr, "Out of memory\n");
        return 1;
    }

    if (!VTFLib::CVTFFile::ConvertToRGBA8888(raw, rgba, w, h, fmt)) {
        std::fprintf(stderr, "Conversion failed\n");
        std::free(rgba);
        return 1;
    }

    int ok = stbi_write_png(png_path, (int)w, (int)h, 4, rgba, (int)(w * 4));
    std::free(rgba);

    if (!ok) {
        std::fprintf(stderr, "stbi_write_png failed\n");
        return 1;
    }

    return 0;
}
