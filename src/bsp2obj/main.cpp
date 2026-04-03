#include "bsp_types.h"
#include "bsp_reader.h"

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

static const std::vector<std::string> TOOL_PREFIXES = {
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
    "TOOLS/TOOLSSKYBOX2D",
    "TOOLS/TOOLSBLACK",
    "TOOLS/TOOLSOCCLUDER",
    "SKY",
};

static bool is_tool_material(const std::string& name) {
    std::string upper = name;
    for (char& c : upper) c = (char)std::toupper((unsigned char)c);
    for (const auto& t : TOOL_PREFIXES) {
        if (upper == t || upper.rfind(t, 0) == 0) return true;
    }
    return false;
}

static std::string mat_to_obj_name(const std::string& material) {
    std::string r = material;
    for (char& c : r) {
        if (c == '/') c = '_';
        c = (char)std::tolower((unsigned char)c);
    }
    return r;
}

struct Face {
    std::vector<std::array<float, 3>> verts;
    std::string material;
};

static std::vector<Face> extract_faces(const BSPData& bsp, bool keep_tools) {
    std::vector<Face> out;

    for (const auto& f : bsp.faces) {
        if (f.numedges < 3) continue;
        if (f.texinfo < 0 || f.texinfo >= (int)bsp.texinfos.size()) continue;

        const BSPTexInfo& ti = bsp.texinfos[f.texinfo];

        if (f.dispInfo < 0) {
            if (!keep_tools) {
                if (ti.flags & (SURF_NODRAW | SURF_SKY | SURF_SKY2D | SURF_HINT | SURF_SKIP)) continue;
            }
        }

        if (ti.texdata < 0 || ti.texdata >= (int)bsp.texdatas.size()) continue;

        int nameID = bsp.texdatas[ti.texdata].nameStringTableID;
        if (nameID < 0 || nameID >= (int)bsp.texnames.size()) continue;

        const std::string& matname = bsp.texnames[nameID];
        if (f.dispInfo < 0 && !keep_tools && is_tool_material(matname)) continue;

        Face face;
        face.material = matname;

        for (int e = 0; e < f.numedges; ++e) {
            int32_t se = bsp.surfedges[f.firstedge + e];
            uint16_t vi = (se >= 0) ? bsp.edges[se].v[0] : bsp.edges[-se].v[1];
            if (vi >= bsp.vertices.size()) continue;
            const BSPVertex& v = bsp.vertices[vi];
            face.verts.push_back({v.x, v.y, v.z});
        }

        if (face.verts.size() < 3) continue;

        if (f.dispInfo >= 0) {
            if (f.dispInfo >= (int)bsp.dispinfos.size()) continue;
            if (face.verts.size() != 4) continue;
            const BSPDispInfo& di = bsp.dispinfos[f.dispInfo];

            int start_idx = 0;
            float best = std::numeric_limits<float>::max();
            for (int k = 0; k < 4; ++k) {
                float dx = face.verts[k][0] - di.startPosition[0];
                float dy = face.verts[k][1] - di.startPosition[1];
                float dz = face.verts[k][2] - di.startPosition[2];
                float d = dx*dx + dy*dy + dz*dz;
                if (d < best) { best = d; start_idx = k; }
            }

            std::array<std::array<float,3>,4> c;
            for (int k = 0; k < 4; ++k)
                c[k] = face.verts[(start_idx + k) % 4];

            int N = (1 << di.power) + 1;
            int base = di.dispVertStart;

            std::vector<std::array<float,3>> grid(N * N);
            for (int gi = 0; gi < N; ++gi) {
                float v = (N > 1) ? (float)gi / (N - 1) : 0.0f;
                for (int gj = 0; gj < N; ++gj) {
                    float u = (N > 1) ? (float)gj / (N - 1) : 0.0f;
                    float bx = c[0][0]*(1-u)*(1-v) + c[1][0]*u*(1-v) + c[2][0]*u*v + c[3][0]*(1-u)*v;
                    float by = c[0][1]*(1-u)*(1-v) + c[1][1]*u*(1-v) + c[2][1]*u*v + c[3][1]*(1-u)*v;
                    float bz = c[0][2]*(1-u)*(1-v) + c[1][2]*u*(1-v) + c[2][2]*u*v + c[3][2]*(1-u)*v;
                    int dv = base + gi * N + gj;
                    if (dv < (int)bsp.dispverts.size()) {
                        const BSPDispVert& dvert = bsp.dispverts[dv];
                        bx += dvert.vec[0] * dvert.dist;
                        by += dvert.vec[1] * dvert.dist;
                        bz += dvert.vec[2] * dvert.dist;
                    }
                    grid[gi * N + gj] = {bx, by, bz};
                }
            }

            for (int gi = 0; gi < N - 1; ++gi) {
                for (int gj = 0; gj < N - 1; ++gj) {
                    auto A = grid[gi * N + gj];
                    auto B = grid[gi * N + gj + 1];
                    auto C = grid[(gi+1) * N + gj + 1];
                    auto D = grid[(gi+1) * N + gj];
                    Face t1, t2;
                    t1.material = matname; t1.verts = {A, B, C};
                    t2.material = matname; t2.verts = {A, C, D};
                    out.push_back(std::move(t1));
                    out.push_back(std::move(t2));
                }
            }
            continue;
        }

        out.push_back(std::move(face));
    }

    return out;
}

static void write_obj(const std::vector<Face>& faces,
                      const std::string& obj_path,
                      const std::string& mtl_path,
                      double scale) {
    std::string mtl_basename = std::filesystem::path(mtl_path).filename().string();
    std::ofstream obj(obj_path);
    std::ofstream mtl(mtl_path);
    if (!obj) throw std::runtime_error("Cannot write OBJ: " + obj_path);
    if (!mtl) throw std::runtime_error("Cannot write MTL: " + mtl_path);

    std::set<std::string> seen;
    for (const auto& f : faces) {
        std::string n = mat_to_obj_name(f.material);
        if (seen.insert(n).second) {
            mtl << "newmtl " << n << "\n\n";
        }
    }

    obj << "mtllib " << mtl_basename << "\n\n";

    for (const auto& f : faces) {
        for (const auto& v : f.verts) {
            obj << "v " << v[0] * scale
                << " "  << v[2] * scale
                << " "  << -v[1] * scale << "\n";
        }
    }
    obj << "\nvt 0 0\n\n";

    size_t vi = 1;
    for (const auto& f : faces) {
        obj << "usemtl " << mat_to_obj_name(f.material) << "\n";
        size_t n = f.verts.size();
        for (size_t t = 1; t < n - 1; ++t) {
            obj << "f " << vi       << "/1"
                << " "  << vi + t   << "/1"
                << " "  << vi + t+1 << "/1\n";
        }
        vi += n;
    }
}

static std::optional<std::array<float, 3>> find_spawn(const std::string& entities) {
    static const std::vector<std::string> SPAWN_CLASSES = {
        "info_player_counterterrorist",
        "info_player_terrorist",
        "info_player_start",
    };

    std::istringstream ss(entities);
    std::string line;
    std::string classname;
    std::array<float, 3> origin{};
    bool in_ent = false;
    bool has_class = false;
    bool has_origin = false;

    auto trim = [](const std::string& s) {
        size_t a = s.find_first_not_of(" \t\r\n");
        size_t b = s.find_last_not_of(" \t\r\n");
        if (a == std::string::npos) return std::string{};
        return s.substr(a, b - a + 1);
    };

    while (std::getline(ss, line)) {
        std::string tl = trim(line);
        if (tl == "{") {
            in_ent = true;
            has_class = false;
            has_origin = false;
            classname.clear();
            continue;
        }
        if (tl == "}") {
            if (in_ent && has_class && has_origin) {
                for (const auto& sc : SPAWN_CLASSES) {
                    if (classname == sc)
                        return origin;
                }
            }
            in_ent = false;
            continue;
        }
        if (!in_ent) continue;

        std::regex kv_re("\"([^\"]+)\"\\s+\"([^\"]+)\"");
        std::smatch m;
        if (!std::regex_search(tl, m, kv_re)) continue;
        std::string key = m[1].str();
        std::string val = m[2].str();

        if (key == "classname") {
            classname = val;
            for (const auto& sc : SPAWN_CLASSES) {
                if (classname == sc) { has_class = true; break; }
            }
        } else if (key == "origin") {
            std::istringstream vs(val);
            if (!(vs >> origin[0] >> origin[1] >> origin[2])) continue;
            has_origin = true;
        }
    }
    return std::nullopt;
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: bsp2obj <input.bsp> <output.obj> [--scale F] [--keep-tools] [--spawn-out FILE]\n";
        return 1;
    }

    std::string bsp_path = argv[1];
    std::string obj_path = argv[2];
    double scale = 1.0;
    bool keep_tools = false;
    std::string spawn_out;

    for (int i = 3; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--keep-tools") {
            keep_tools = true;
        } else if (arg == "--scale" && i + 1 < argc) {
            scale = std::stod(argv[++i]);
        } else if (arg == "--spawn-out" && i + 1 < argc) {
            spawn_out = argv[++i];
        }
    }

    BSPData bsp;
    try {
        bsp = load_bsp(bsp_path);
    } catch (const std::exception& e) {
        std::cerr << "Error loading BSP: " << e.what() << "\n";
        return 1;
    }

    auto faces = extract_faces(bsp, keep_tools);
    std::string mtl_path = std::filesystem::path(obj_path).replace_extension(".mtl").string();

    try {
        write_obj(faces, obj_path, mtl_path, scale);
    } catch (const std::exception& e) {
        std::cerr << "Error writing OBJ: " << e.what() << "\n";
        return 1;
    }

    std::cout << "Wrote " << faces.size() << " faces to " << obj_path << "\n";

    if (!spawn_out.empty()) {
        auto sp = find_spawn(bsp.entities);
        std::ofstream sf(spawn_out);
        if (sp) {
            sf << (*sp)[0] << " " << (*sp)[1] << " " << (*sp)[2] << "\n";
            std::cout << "Spawn: " << (*sp)[0] << " " << (*sp)[1] << " " << (*sp)[2] << "\n";
        } else {
            sf << "none\n";
        }
    }

    return 0;
}
