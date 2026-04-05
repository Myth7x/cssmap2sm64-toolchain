#include "bsp_types.h"
#include "bsp_reader.h"

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <limits>
#include <numeric>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <string>
#include <thread>
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

static std::string normalize_material(const std::string& name) {
    if (name.size() < 5) return name;
    std::string upper = name.substr(0, 5);
    for (char& c : upper) c = (char)std::toupper((unsigned char)c);
    if (upper != "MAPS/") return name;
    size_t second_slash = name.find('/', 5);
    if (second_slash == std::string::npos) return name;
    std::string inner = name.substr(second_slash + 1);
    static const std::regex suffix_re(R"((_-?\d+){3}$)");
    std::string stripped = std::regex_replace(inner, suffix_re, "");
    return stripped.empty() ? inner : stripped;
}

struct Face {
    std::vector<std::array<float, 3>> verts;
    std::vector<std::array<float, 2>> uvs;
    std::string material;
};

static std::array<float, 2> compute_uv(float x, float y, float z,
                                        const BSPTexInfo& ti,
                                        const BSPTexData& td) {
    float u = (x * ti.textureVecs[0][0] + y * ti.textureVecs[0][1]
             + z * ti.textureVecs[0][2] + ti.textureVecs[0][3])
            / (float)td.width;
    float v = (x * ti.textureVecs[1][0] + y * ti.textureVecs[1][1]
             + z * ti.textureVecs[1][2] + ti.textureVecs[1][3])
            / (float)td.height;
    return {u, -v};
}

static std::vector<Face> extract_faces(const BSPData& bsp, bool keep_tools) {
    // Build per-face origin from the BSP model that owns each face.
    // Source BSP stores brush entity vertices in entity-local space (relative to
    // model.origin); we add the origin to convert to world space.
    // Faces not owned by any model are unreferenced garbage and are skipped.
    struct FaceInfo { bool valid; float ox, oy, oz; };
    std::vector<FaceInfo> face_info(bsp.faces.size(), {false, 0.f, 0.f, 0.f});
    for (int mi = 0; mi < (int)bsp.models.size(); ++mi) {
        const auto& mdl = bsp.models[mi];
        int first = mdl.firstface;
        int last  = first + mdl.numfaces;
        if (first < 0) continue;
        float ox = 0.f, oy = 0.f, oz = 0.f;
        if (mi < (int)bsp.model_world_origins.size()) {
            ox = bsp.model_world_origins[mi][0];
            oy = bsp.model_world_origins[mi][1];
            oz = bsp.model_world_origins[mi][2];
        }
        for (int fi = first; fi < last && fi < (int)bsp.faces.size(); ++fi)
            face_info[fi] = {true, ox, oy, oz};
    }

    unsigned int hc = std::max(1u, std::thread::hardware_concurrency());
    size_t total = bsp.faces.size();
    size_t chunk_size = (total + hc - 1) / hc;

    auto process_range = [&](size_t lo, size_t hi) -> std::vector<Face> {
        std::vector<Face> sub;
        for (size_t fi = lo; fi < hi; ++fi) {
            const FaceInfo& fi_info = face_info[fi];
            if (!fi_info.valid) continue;
            const float ox = fi_info.ox, oy = fi_info.oy, oz = fi_info.oz;

            const auto& f = bsp.faces[fi];
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

            const std::string& raw_matname = bsp.texnames[nameID];
            if (f.dispInfo < 0 && !keep_tools && is_tool_material(raw_matname)) continue;

            const std::string matname = normalize_material(raw_matname);
            Face face;
            face.material = matname;

            const BSPTexData& td = bsp.texdatas[ti.texdata];
            for (int e = 0; e < f.numedges; ++e) {
                if (f.firstedge < 0 || f.firstedge + e >= (int)bsp.surfedges.size()) continue;
                int32_t se = bsp.surfedges[f.firstedge + e];
                int64_t ei64 = (se >= 0) ? (int64_t)se : -(int64_t)se;
                if (ei64 >= (int64_t)bsp.edges.size()) continue;
                size_t ei = (size_t)ei64;
                uint16_t vi = (se >= 0) ? bsp.edges[ei].v[0] : bsp.edges[ei].v[1];
                if (vi >= bsp.vertices.size()) continue;
                const BSPVertex& v = bsp.vertices[vi];
                float wx = v.x + ox, wy = v.y + oy, wz = v.z + oz;
                face.verts.push_back({wx, wy, wz});
                face.uvs.push_back(compute_uv(wx, wy, wz, ti, td));
            }

            if (face.verts.size() < 3) continue;

            if (f.dispInfo >= 0) {
                if (f.dispInfo >= (int)bsp.dispinfos.size()) continue;
                if (face.verts.size() != 4) continue;
                const BSPDispInfo& di = bsp.dispinfos[f.dispInfo];

                int start_idx = 0;
                float best = std::numeric_limits<float>::max();
                for (int k = 0; k < 4; ++k) {
                    float dx = face.verts[k][0] - (di.startPosition[0] + ox);
                    float dy = face.verts[k][1] - (di.startPosition[1] + oy);
                    float dz = face.verts[k][2] - (di.startPosition[2] + oz);
                    float d = dx*dx + dy*dy + dz*dz;
                    if (d < best) { best = d; start_idx = k; }
                }

                std::array<std::array<float,3>,4> c;
                for (int k = 0; k < 4; ++k)
                    c[k] = face.verts[(start_idx + k) % 4];

                if (di.power < 1 || di.power > 4) continue;
                int N = (1 << di.power) + 1;
                int base = di.dispVertStart;
                if (base < 0) continue;

                std::vector<std::array<float,3>> grid(N * N);
                for (int gi = 0; gi < N; ++gi) {
                    float v = (N > 1) ? (float)gi / (N - 1) : 0.0f;
                    for (int gj = 0; gj < N; ++gj) {
                        float u = (N > 1) ? (float)gj / (N - 1) : 0.0f;
                        float bx = c[0][0]*(1-u)*(1-v) + c[1][0]*u*(1-v) + c[2][0]*u*v + c[3][0]*(1-u)*v;
                        float by = c[0][1]*(1-u)*(1-v) + c[1][1]*u*(1-v) + c[2][1]*u*v + c[3][1]*(1-u)*v;
                        float bz = c[0][2]*(1-u)*(1-v) + c[1][2]*u*(1-v) + c[2][2]*u*v + c[3][2]*(1-u)*v;
                        int dv = base + gi * N + gj;
                        if (dv >= 0 && dv < (int)bsp.dispverts.size()) {
                            const BSPDispVert& dvert = bsp.dispverts[dv];
                            bx += dvert.vec[0] * dvert.dist;
                            by += dvert.vec[1] * dvert.dist;
                            bz += dvert.vec[2] * dvert.dist;
                        }
                        grid[gi * N + gj] = {bx, by, bz};
                    }
                }

                const BSPTexData& dtd = bsp.texdatas[ti.texdata];
                for (int gi = 0; gi < N - 1; ++gi) {
                    for (int gj = 0; gj < N - 1; ++gj) {
                        auto A = grid[gi * N + gj];
                        auto B = grid[gi * N + gj + 1];
                        auto C = grid[(gi+1) * N + gj + 1];
                        auto D = grid[(gi+1) * N + gj];
                        Face t1, t2;
                        t1.material = matname; t1.verts = {A, B, C};
                        t1.uvs = {compute_uv(A[0],A[1],A[2],ti,dtd),
                                  compute_uv(B[0],B[1],B[2],ti,dtd),
                                  compute_uv(C[0],C[1],C[2],ti,dtd)};
                        t2.material = matname; t2.verts = {A, C, D};
                        t2.uvs = {compute_uv(A[0],A[1],A[2],ti,dtd),
                                  compute_uv(C[0],C[1],C[2],ti,dtd),
                                  compute_uv(D[0],D[1],D[2],ti,dtd)};
                        sub.push_back(std::move(t1));
                        sub.push_back(std::move(t2));
                    }
                }
                continue;
            }

            sub.push_back(std::move(face));
        }
        return sub;
    };

    std::vector<std::future<std::vector<Face>>> futures;
    futures.reserve(hc);
    for (unsigned int t = 0; t < hc; ++t) {
        size_t lo = t * chunk_size;
        size_t hi = std::min(lo + chunk_size, total);
        if (lo >= hi) break;
        futures.push_back(std::async(std::launch::async, process_range, lo, hi));
    }

    std::vector<Face> out;
    for (auto& fut : futures) {
        auto sub = fut.get();
        out.insert(out.end(), std::make_move_iterator(sub.begin()), std::make_move_iterator(sub.end()));
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

    std::vector<size_t> order(faces.size());
    std::iota(order.begin(), order.end(), 0);
    std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
        return mat_to_obj_name(faces[a].material) < mat_to_obj_name(faces[b].material);
    });

    std::set<std::string> seen;
    for (size_t idx : order) {
        std::string n = mat_to_obj_name(faces[idx].material);
        if (seen.insert(n).second) {
            mtl << "newmtl " << n << "\n\n";
        }
    }

    obj << "mtllib " << mtl_basename << "\n\n";

    for (size_t idx : order) {
        for (const auto& v : faces[idx].verts) {
            obj << "v " << v[0] * scale
                << " "  << v[2] * scale
                << " "  << -v[1] * scale << "\n";
        }
    }
    obj << "\n";
    for (size_t idx : order) {
        for (const auto& uv : faces[idx].uvs) {
            obj << "vt " << uv[0] << " " << uv[1] << "\n";
        }
    }
    obj << "\n";

    std::string cur_mat;
    size_t vi = 1;
    for (size_t idx : order) {
        const auto& f = faces[idx];
        std::string mat = mat_to_obj_name(f.material);
        if (mat != cur_mat) {
            obj << "o " << mat << "\n";
            obj << "usemtl " << mat << "\n";
            cur_mat = mat;
        }
        size_t n = f.verts.size();
        for (size_t t = 1; t < n - 1; ++t) {
            const auto& A = f.verts[0];
            const auto& B = f.verts[t];
            const auto& C = f.verts[t + 1];
            float bax = B[0]-A[0], bay = B[1]-A[1], baz = B[2]-A[2];
            float cax = C[0]-A[0], cay = C[1]-A[1], caz = C[2]-A[2];
            float nx = bay*caz - baz*cay;
            float ny = baz*cax - bax*caz;
            float nz = bax*cay - bay*cax;
            if (nx*nx + ny*ny + nz*nz < 1e-6f) continue;
            obj << "f " << vi       << "/" << vi
                << " "  << vi + t+1 << "/" << vi + t+1
                << " "  << vi + t   << "/" << vi + t   << "\n";
        }
        vi += n;
    }
}

static void write_props_json(const std::vector<StaticProp>& props, const std::string& path) {
    std::ofstream f(path);
    if (!f) throw std::runtime_error("Cannot write props JSON: " + path);
    f << "[\n";
    for (size_t i = 0; i < props.size(); ++i) {
        const auto& p = props[i];
        f << "  {"
          << "\"model\":\"" << p.model << "\""
          << ",\"origin\":[" << p.origin[0] << "," << p.origin[1] << "," << p.origin[2] << "]"
          << ",\"angles\":[" << p.angles[0] << "," << p.angles[1] << "," << p.angles[2] << "]"
          << ",\"skin\":" << p.skin
          << "}";
        if (i + 1 < props.size()) f << ",";
        f << "\n";
    }
    f << "]\n";
}

struct SkyCamera {
    float origin[3];
    float scale;
};

static std::optional<SkyCamera> find_sky_camera(const std::string& entities) {
    std::istringstream ss(entities);
    std::string line;
    std::string classname;
    float origin[3]{};
    float scale = 16.0f;
    bool in_ent = false, has_class = false, has_origin = false;

    auto trim = [](const std::string& s) {
        size_t a = s.find_first_not_of(" \t\r\n");
        size_t b = s.find_last_not_of(" \t\r\n");
        if (a == std::string::npos) return std::string{};
        return s.substr(a, b - a + 1);
    };

    while (std::getline(ss, line)) {
        std::string tl = trim(line);
        if (tl == "{") {
            in_ent = true; has_class = false; has_origin = false;
            classname.clear(); scale = 16.0f;
            continue;
        }
        if (tl == "}") {
            if (in_ent && has_class && has_origin)
                return SkyCamera{{origin[0], origin[1], origin[2]}, scale};
            in_ent = false;
            continue;
        }
        if (!in_ent) continue;
        std::regex kv_re("\"([^\"]+)\"\\s+\"([^\"]+)\"");
        std::smatch m;
        if (!std::regex_search(tl, m, kv_re)) continue;
        std::string key = m[1].str(), val = m[2].str();
        if (key == "classname" && val == "sky_camera") {
            has_class = true;
        } else if (key == "origin") {
            std::istringstream vs(val);
            if (vs >> origin[0] >> origin[1] >> origin[2]) has_origin = true;
        } else if (key == "scale") {
            try { scale = std::stof(val); } catch (...) {}
        }
    }
    return std::nullopt;
}

static void write_sky_camera_json(const SkyCamera& cam, const std::string& path) {
    std::ofstream f(path);
    if (!f) throw std::runtime_error("Cannot write sky camera JSON: " + path);
    f << "{\"origin\":[" << cam.origin[0] << "," << cam.origin[1] << "," << cam.origin[2]
      << "],\"scale\":" << cam.scale << "}\n";
}

static void write_sky_obj(const std::vector<Face>& faces,
                          const std::string& obj_path,
                          const std::string& mtl_path,
                          double scale,
                          float sky_scale) {
    std::string mtl_basename = std::filesystem::path(mtl_path).filename().string();
    std::ofstream obj(obj_path);
    std::ofstream mtl(mtl_path);
    if (!obj) throw std::runtime_error("Cannot write sky OBJ: " + obj_path);
    if (!mtl) throw std::runtime_error("Cannot write sky MTL: " + mtl_path);

    std::vector<size_t> order(faces.size());
    std::iota(order.begin(), order.end(), 0);
    std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
        return mat_to_obj_name(faces[a].material) < mat_to_obj_name(faces[b].material);
    });

    std::set<std::string> seen;
    for (size_t idx : order) {
        std::string n = mat_to_obj_name(faces[idx].material);
        if (seen.insert(n).second)
            mtl << "newmtl " << n << "\n\n";
    }

    obj << "mtllib " << mtl_basename << "\n\n";

    double vs = scale * static_cast<double>(sky_scale);
    for (size_t idx : order) {
        for (const auto& v : faces[idx].verts)
            obj << "v " << v[0]*vs << " " << v[2]*vs << " " << -v[1]*vs << "\n";
    }
    obj << "\n";
    for (size_t idx : order) {
        for (const auto& uv : faces[idx].uvs)
            obj << "vt " << uv[0] << " " << uv[1] << "\n";
    }
    obj << "\n";

    std::string cur_mat;
    size_t vi = 1;
    for (size_t idx : order) {
        const auto& f = faces[idx];
        std::string mat = mat_to_obj_name(f.material);
        if (mat != cur_mat) {
            obj << "o " << mat << "\n";
            obj << "usemtl " << mat << "\n";
            cur_mat = mat;
        }
        size_t n = f.verts.size();
        for (size_t t = 1; t < n - 1; ++t) {
            const auto& A = f.verts[0];
            const auto& B = f.verts[t];
            const auto& C = f.verts[t + 1];
            float bax = B[0]-A[0], bay = B[1]-A[1], baz = B[2]-A[2];
            float cax = C[0]-A[0], cay = C[1]-A[1], caz = C[2]-A[2];
            float nx = bay*caz - baz*cay;
            float ny = baz*cax - bax*caz;
            float nz = bax*cay - bay*cax;
            if (nx*nx + ny*ny + nz*nz < 1e-6f) continue;
            obj << "f " << vi       << "/" << vi
                << " "  << vi + t+1 << "/" << vi + t+1
                << " "  << vi + t   << "/" << vi + t   << "\n";
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

static const std::unordered_map<std::string, std::string> ENTITY_TYPE_MAP = {
    {"trigger_hurt",         "death"},
    {"trigger_push",         "death"},
    {"trigger_kill",         "death"},
    {"trigger_teleport",     "teleport"},
    {"trigger_multiple",     "script"},
    {"trigger_once",         "script"},
    {"trigger_changelevel",  "script"},
    {"trigger_look",         "script"},
    {"trigger_proximity",    "script"},
    {"trigger_wind",         "script"},
    {"func_door",            "door"},
    {"func_door_rotating",   "door"},
    {"func_rotating",        "door"},
    {"func_movelinear",      "door"},
    {"func_tracktrain",      "door"},
    {"func_brush",           "brush"},
    {"func_wall",            "brush"},
    {"func_illusionary",     "brush"},
    {"func_detail",          "brush"},
    {"func_lod",             "brush"},
    {"func_occluder",        "brush"},
    {"logic_relay",          "logic"},
    {"logic_case",           "logic"},
    {"logic_auto",           "logic"},
    {"logic_timer",          "logic"},
    {"logic_branch",         "logic"},
    {"logic_compare",        "logic"},
    {"logic_multicompare",   "logic"},
    {"info_landmark",        "landmark"},
    {"info_target",          "landmark"},
    {"info_teleport_destination", "landmark"},
};

static std::string json_escape(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 4);
    for (unsigned char c : s) {
        if (c == '"')       out += "\\\"";
        else if (c == '\\') out += "\\\\";
        else if (c < 0x20)  out += "?";
        else                out += (char)c;
    }
    return out;
}

static void write_triggers_json(
    const std::string& entities,
    const std::vector<BSPModel>& models,
    const std::vector<std::array<float,3>>& bsp_world_origins,
    const std::string& path)
{
    auto trim = [](const std::string& s) {
        size_t a = s.find_first_not_of(" \t\r\n");
        size_t b = s.find_last_not_of(" \t\r\n");
        if (a == std::string::npos) return std::string{};
        return s.substr(a, b - a + 1);
    };

    std::ofstream f(path);
    if (!f) throw std::runtime_error("Cannot write triggers JSON: " + path);

    std::istringstream ss(entities);
    std::string line;
    bool in_ent = false;
    std::unordered_map<std::string, std::string> kv;

    std::vector<std::unordered_map<std::string, std::string>> ent_list;

    while (std::getline(ss, line)) {
        std::string tl = trim(line);
        if (tl == "{") { in_ent = true; kv.clear(); continue; }
        if (tl == "}") {
            if (in_ent && !kv.empty()) ent_list.push_back(kv);
            in_ent = false; continue;
        }
        if (!in_ent) continue;
        std::regex kv_re("\"([^\"]+)\"\\s+\"([^\"]+)\"");
        std::smatch m;
        if (std::regex_search(tl, m, kv_re))
            kv[m[1].str()] = m[2].str();
    }

    f << "[\n";
    size_t written = 0;
    for (const auto& e : ent_list) {
        auto it_class = e.find("classname");
        if (it_class == e.end()) continue;
        const std::string& cls = it_class->second;
        auto it_type = ENTITY_TYPE_MAP.find(cls);
        if (it_type == ENTITY_TYPE_MAP.end()) continue;
        const std::string& type = it_type->second;

        std::string targetname, target, model_key;
        float mins[3]{}, maxs[3]{}, origin[3]{};
        bool has_aabb = false;

        auto get = [&](const std::string& k, std::string& out) {
            auto it = e.find(k);
            if (it != e.end()) out = it->second;
        };

        get("targetname", targetname);
        get("target",     target);
        get("model",      model_key);

        if (!model_key.empty() && model_key[0] == '*') {
            int idx = -1;
            try { idx = std::stoi(model_key.substr(1)); } catch (...) {}
            if (idx > 0 && idx < (int)models.size()) {
                const BSPModel& mdl = models[idx];
                float wo[3] = {0.f, 0.f, 0.f};
                if (idx < (int)bsp_world_origins.size()) {
                    wo[0] = bsp_world_origins[idx][0];
                    wo[1] = bsp_world_origins[idx][1];
                    wo[2] = bsp_world_origins[idx][2];
                }
                mins[0] = mdl.mins[0] + wo[0]; mins[1] = mdl.mins[1] + wo[1]; mins[2] = mdl.mins[2] + wo[2];
                maxs[0] = mdl.maxs[0] + wo[0]; maxs[1] = mdl.maxs[1] + wo[1]; maxs[2] = mdl.maxs[2] + wo[2];
                origin[0] = (mins[0]+maxs[0])*0.5f;
                origin[1] = (mins[1]+maxs[1])*0.5f;
                origin[2] = (mins[2]+maxs[2])*0.5f;
                has_aabb = true;
            }
        }

        if (!has_aabb) {
            auto it_o = e.find("origin");
            if (it_o != e.end()) {
                std::istringstream vs(it_o->second);
                if (vs >> origin[0] >> origin[1] >> origin[2]) {
                    const float r = 32.0f;
                    mins[0] = origin[0]-r; mins[1] = origin[1]-r; mins[2] = origin[2]-r;
                    maxs[0] = origin[0]+r; maxs[1] = origin[1]+r; maxs[2] = origin[2]+r;
                    has_aabb = true;
                }
            }
        }

        if (!has_aabb) continue;

        if (written > 0) f << ",\n";
        f << "  {"
          << "\"class\":\"" << json_escape(cls) << "\""
          << ",\"type\":\"" << json_escape(type) << "\""
          << ",\"targetname\":\"" << json_escape(targetname) << "\""
          << ",\"target\":\"" << json_escape(target) << "\""
          << ",\"origin\":[" << origin[0] << "," << origin[1] << "," << origin[2] << "]"
          << ",\"mins\":["   << mins[0]   << "," << mins[1]   << "," << mins[2]   << "]"
          << ",\"maxs\":["   << maxs[0]   << "," << maxs[1]   << "," << maxs[2]   << "]"
          << "}";
        ++written;
    }

    f << "\n]\n";
    std::cout << "Triggers: " << written << " entities to " << path << "\n";
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: bsp2obj <input.bsp> <output.obj> [--scale F] [--keep-tools] [--spawn-out FILE] [--props-out FILE] [--skybox-out FILE] [--sky-camera-out FILE] [--sky-radius F] [--triggers-out FILE]\n";
        return 1;
    }

    std::string bsp_path = argv[1];
    std::string obj_path = argv[2];
    double scale = 1.0;
    bool keep_tools = false;
    std::string spawn_out;
    std::string props_out;
    std::string skybox_out;
    std::string sky_camera_out;
    std::string triggers_out;
    float sky_radius = 0.0f;

    for (int i = 3; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--keep-tools") {
            keep_tools = true;
        } else if (arg == "--scale" && i + 1 < argc) {
            scale = std::stod(argv[++i]);
        } else if (arg == "--spawn-out" && i + 1 < argc) {
            spawn_out = argv[++i];
        } else if (arg == "--props-out" && i + 1 < argc) {
            props_out = argv[++i];
        } else if (arg == "--skybox-out" && i + 1 < argc) {
            skybox_out = argv[++i];
        } else if (arg == "--sky-camera-out" && i + 1 < argc) {
            sky_camera_out = argv[++i];
        } else if (arg == "--sky-radius" && i + 1 < argc) {
            sky_radius = std::stof(argv[++i]);
        } else if (arg == "--triggers-out" && i + 1 < argc) {
            triggers_out = argv[++i];
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

    if (!skybox_out.empty()) {
        auto sky_cam = find_sky_camera(bsp.entities);
        if (sky_cam) {
            auto spawn = find_spawn(bsp.entities);
            float radius = sky_radius;
            if (radius <= 0.0f) {
                if (spawn) {
                    float dx = sky_cam->origin[0] - (*spawn)[0];
                    float dy = sky_cam->origin[1] - (*spawn)[1];
                    float dz = sky_cam->origin[2] - (*spawn)[2];
                    radius = std::sqrt(dx*dx + dy*dy + dz*dz) * 0.5f;
                }
                if (radius <= 0.0f) radius = 8192.0f;
            }

            std::vector<Face> sky_faces, main_faces;
            for (auto& face : faces) {
                float cx = 0.0f, cy = 0.0f, cz = 0.0f;
                for (const auto& v : face.verts) { cx += v[0]; cy += v[1]; cz += v[2]; }
                float n = static_cast<float>(face.verts.size());
                cx /= n; cy /= n; cz /= n;
                float ddx = cx - sky_cam->origin[0];
                float ddy = cy - sky_cam->origin[1];
                float ddz = cz - sky_cam->origin[2];
                float d = std::sqrt(ddx*ddx + ddy*ddy + ddz*ddz);
                if (d <= radius)
                    sky_faces.push_back(std::move(face));
                else
                    main_faces.push_back(std::move(face));
            }
            faces = std::move(main_faces);

            if (!sky_faces.empty()) {
                std::string sky_mtl = std::filesystem::path(skybox_out).replace_extension(".sky.mtl").string();
                try {
                    write_sky_obj(sky_faces, skybox_out, sky_mtl, scale, sky_cam->scale);
                    std::cout << "Sky: " << sky_faces.size() << " faces to " << skybox_out << "\n";
                } catch (const std::exception& e) {
                    std::cerr << "Error writing sky OBJ: " << e.what() << "\n";
                }
            } else {
                std::cout << "Sky: sky_camera found but no faces within radius " << radius << "\n";
            }

            if (!sky_camera_out.empty()) {
                try {
                    write_sky_camera_json(*sky_cam, sky_camera_out);
                    std::cout << "Sky camera: origin=(" << sky_cam->origin[0] << "," << sky_cam->origin[1] << "," << sky_cam->origin[2] << ") scale=" << sky_cam->scale << "\n";
                } catch (const std::exception& e) {
                    std::cerr << "Error writing sky camera JSON: " << e.what() << "\n";
                }
            }
        } else {
            std::cout << "Sky: no sky_camera entity found, skipping skybox export\n";
        }
    }

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

    if (!props_out.empty()) {
        try {
            write_props_json(bsp.static_props, props_out);
            std::cout << "Props: " << bsp.static_props.size() << " static props to " << props_out << "\n";
        } catch (const std::exception& e) {
            std::cerr << "Error writing props JSON: " << e.what() << "\n";
        }
    }

    if (!triggers_out.empty()) {
        try {
            write_triggers_json(bsp.entities, bsp.models, bsp.model_world_origins, triggers_out);
        } catch (const std::exception& e) {
            std::cerr << "Error writing triggers JSON: " << e.what() << "\n";
        }
    }

    return 0;
}
