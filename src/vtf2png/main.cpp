#define STB_IMAGE_WRITE_IMPLEMENTATION
#include "stb_image_write.h"

#define STB_IMAGE_RESIZE_IMPLEMENTATION
#include "stb_image_resize2.h"

#include <VTFFile.h>

#include <cstdio>
#include <cstdlib>

static unsigned int floor_pot(unsigned int x) {
    if (x == 0) return 1;
    unsigned int p = 1;
    while (p * 2 <= x) p *= 2;
    return p;
}

int main(int argc, char* argv[]) {
    if (argc < 3 || argc > 4) {
        std::fprintf(stderr, "Usage: vtf2png <input.vtf> <output.png> [max_size]\n");
        return 1;
    }

    const char* vtf_path  = argv[1];
    const char* png_path  = argv[2];
    int max_size = (argc == 4) ? std::atoi(argv[3]) : 0;

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

    unsigned int nw = floor_pot(w);
    unsigned int nh = floor_pot(h);
    if (max_size > 0) {
        while (nw > (unsigned int)max_size) nw /= 2;
        while (nh > (unsigned int)max_size) nh /= 2;
    }

    vlByte* pixels = rgba;
    vlByte* resized = nullptr;
    if (nw != w || nh != h) {
        resized = static_cast<vlByte*>(std::malloc(nw * nh * 4));
        if (!resized) {
            std::fprintf(stderr, "Out of memory (resize)\n");
            std::free(rgba);
            return 1;
        }
        stbir_resize_uint8_srgb(rgba, (int)w, (int)h, 0, resized, (int)nw, (int)nh, 0, STBIR_RGBA);
        pixels = resized;
    }

    int ok = stbi_write_png(png_path, (int)nw, (int)nh, 4, pixels, (int)(nw * 4));
    std::free(rgba);
    if (resized) std::free(resized);

    if (!ok) {
        std::fprintf(stderr, "stbi_write_png failed\n");
        return 1;
    }

    return 0;
}
