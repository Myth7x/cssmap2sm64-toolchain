#include "obj_writer.h"

#include <cctype>
#include <filesystem>
#include <fstream>
#include <set>

namespace {

std::string mat_to_obj_name(const std::string& material) {
    std::string r = material;
    for (char& c : r) {
        if (c == '/') c = '_';
        c = (char)std::tolower((unsigned char)c);
    }
    return r;
}

} // namespace

void write_obj(const std::vector<BrushFace>& faces,
               const std::string& obj_path,
               const std::string& mtl_path,
               double scale) {
    std::string mtl_basename = std::filesystem::path(mtl_path).filename().string();

    std::ofstream obj(obj_path);
    std::ofstream mtl(mtl_path);

    std::set<std::string> seen_mats;
    for (const auto& face : faces) {
        std::string name = mat_to_obj_name(face.material);
        if (seen_mats.insert(name).second) {
            mtl << "newmtl " << name << "\n";
            mtl << "map_Kd " << name << ".png\n\n";
        }
    }

    obj << "mtllib " << mtl_basename << "\n\n";

    for (const auto& face : faces) {
        for (const auto& v : face.vertices) {
            obj << "v " << v[0] * scale
                << " "  << v[1] * scale
                << " "  << v[2] * scale << "\n";
        }
    }

    obj << "\n";

    for (const auto& face : faces) {
        obj << "vn " << face.normal[0]
            << " "   << face.normal[1]
            << " "   << face.normal[2] << "\n";
    }

    obj << "\nvt 0 0\n\n";

    size_t vi = 1;
    size_t ni = 1;
    for (const auto& face : faces) {
        obj << "usemtl " << mat_to_obj_name(face.material) << "\n";
        size_t n = face.vertices.size();
        for (size_t t = 1; t < n - 1; ++t) {
            obj << "f " << vi       << "/1/" << ni
                << " "  << vi + t   << "/1/" << ni
                << " "  << vi + t+1 << "/1/" << ni << "\n";
        }
        vi += n;
        ++ni;
    }
}
