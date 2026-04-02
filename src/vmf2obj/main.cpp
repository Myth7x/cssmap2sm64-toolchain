#include "vmf_parser.h"
#include "brush_solver.h"
#include "obj_writer.h"

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

static const std::vector<std::string> TOOL_MATS = {
    "TOOLS/TOOLSNODRAW",
    "TOOLS/TOOLSSKIP",
    "TOOLS/TOOLSTRIGGER",
    "TOOLS/TOOLSCLIP",
    "TOOLS/TOOLSPLAYERCLIP",
    "TOOLS/TOOLSNPCCLIP",
    "TOOLS/TOOLSBLOCKLIGHT",
    "TOOLS/TOOLSAREAPORTAL",
    "TOOLS/TOOLSHINT",
    "TOOLS/TOOLSSKYBOX",
};

static bool is_tool_material(const std::string& material) {
    std::string upper = material;
    for (char& c : upper) c = (char)std::toupper((unsigned char)c);
    for (const auto& t : TOOL_MATS) {
        if (upper == t) return true;
    }
    return false;
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: vmf2obj <input.vmf> <output.obj> [--scale F] [--keep-tools]\n";
        return 1;
    }

    std::string vmf_path = argv[1];
    std::string obj_path = argv[2];
    double scale = 1.0;
    bool keep_tools = false;

    for (int i = 3; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--keep-tools") {
            keep_tools = true;
        } else if (arg == "--scale" && i + 1 < argc) {
            scale = std::stod(argv[++i]);
        }
    }

    std::ifstream f(vmf_path);
    if (!f) {
        std::cerr << "Failed to open: " << vmf_path << "\n";
        return 1;
    }
    std::ostringstream buf;
    buf << f.rdbuf();
    std::string content = buf.str();

    KVNode root = parse_document(content);
    std::vector<SolidDef> solids = extract_solids(root);

    std::vector<BrushFace> all_faces;
    for (const auto& solid : solids) {
        std::vector<Plane> planes;
        for (const auto& side : solid.sides) {
            Vec3 p1 = {side.plane_points[0][0], side.plane_points[0][1], side.plane_points[0][2]};
            Vec3 p2 = {side.plane_points[1][0], side.plane_points[1][1], side.plane_points[1][2]};
            Vec3 p3 = {side.plane_points[2][0], side.plane_points[2][1], side.plane_points[2][2]};
            planes.push_back(plane_from_points(p1, p2, p3, side.material));
        }
        auto faces = solve_brush(planes);
        for (auto& face : faces) {
            if (!keep_tools && is_tool_material(face.material)) continue;
            all_faces.push_back(std::move(face));
        }
    }

    std::string mtl_path = std::filesystem::path(obj_path).replace_extension(".mtl").string();
    write_obj(all_faces, obj_path, mtl_path, scale);

    std::cout << "Wrote " << all_faces.size() << " faces to " << obj_path << "\n";
    return 0;
}
