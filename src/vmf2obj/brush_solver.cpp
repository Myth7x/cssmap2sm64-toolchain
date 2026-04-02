#include "brush_solver.h"

#include <algorithm>
#include <cmath>
#include <numeric>

namespace {

double dot(const Vec3& a, const Vec3& b) {
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

Vec3 cross(const Vec3& a, const Vec3& b) {
    return {a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]};
}

Vec3 sub(const Vec3& a, const Vec3& b) {
    return {a[0] - b[0], a[1] - b[1], a[2] - b[2]};
}

Vec3 scale(const Vec3& a, double s) {
    return {a[0] * s, a[1] * s, a[2] * s};
}

double length(const Vec3& a) {
    return std::sqrt(dot(a, a));
}

Vec3 normalize(const Vec3& a) {
    double l = length(a);
    if (l < 1e-12) return {0.0, 0.0, 0.0};
    return scale(a, 1.0 / l);
}

bool verts_equal(const Vec3& a, const Vec3& b) {
    constexpr double eps = 0.01;
    return std::abs(a[0] - b[0]) < eps
        && std::abs(a[1] - b[1]) < eps
        && std::abs(a[2] - b[2]) < eps;
}

} // namespace

Plane plane_from_points(const Vec3& p1, const Vec3& p2, const Vec3& p3, const std::string& material) {
    Vec3 n = normalize(cross(sub(p2, p1), sub(p3, p1)));
    return {n, -dot(n, p1), material};
}

std::vector<BrushFace> solve_brush(std::vector<Plane>& planes) {
    const size_t N = planes.size();
    std::vector<std::vector<Vec3>> face_verts(N);

    for (size_t i = 0; i < N; ++i) {
        for (size_t j = i + 1; j < N; ++j) {
            for (size_t k = j + 1; k < N; ++k) {
                const Vec3& ni = planes[i].normal;
                const Vec3& nj = planes[j].normal;
                const Vec3& nk = planes[k].normal;

                Vec3 njxnk = cross(nj, nk);
                double det = dot(ni, njxnk);
                if (std::abs(det) < 1e-6) continue;

                double di = -planes[i].d;
                double dj = -planes[j].d;
                double dk = -planes[k].d;

                Vec3 nkxni = cross(nk, ni);
                Vec3 nixnj = cross(ni, nj);

                Vec3 pt = {
                    (di * njxnk[0] + dj * nkxni[0] + dk * nixnj[0]) / det,
                    (di * njxnk[1] + dj * nkxni[1] + dk * nixnj[1]) / det,
                    (di * njxnk[2] + dj * nkxni[2] + dk * nixnj[2]) / det,
                };

                bool valid = true;
                for (size_t m = 0; m < N && valid; ++m) {
                    if (m == i || m == j || m == k) continue;
                    double dist = dot(planes[m].normal, pt) + planes[m].d;
                    if (dist < -0.01) valid = false;
                }
                if (!valid) continue;

                for (size_t fi : {i, j, k}) {
                    bool found = false;
                    for (const auto& v : face_verts[fi]) {
                        if (verts_equal(v, pt)) { found = true; break; }
                    }
                    if (!found) face_verts[fi].push_back(pt);
                }
            }
        }
    }

    std::vector<BrushFace> result;
    for (size_t i = 0; i < N; ++i) {
        if (face_verts[i].size() < 3) continue;

        Vec3 centroid = {0.0, 0.0, 0.0};
        for (const auto& v : face_verts[i]) {
            centroid[0] += v[0];
            centroid[1] += v[1];
            centroid[2] += v[2];
        }
        double n_verts = (double)face_verts[i].size();
        centroid[0] /= n_verts;
        centroid[1] /= n_verts;
        centroid[2] /= n_verts;

        const Vec3& normal = planes[i].normal;

        Vec3 ref = {0.0, 0.0, 0.0};
        for (size_t vi = 0; vi < face_verts[i].size(); ++vi) {
            ref = sub(face_verts[i][vi], centroid);
            if (length(ref) > 1e-9) break;
        }
        ref = normalize(ref);
        Vec3 perp = normalize(cross(normal, ref));

        std::vector<size_t> indices(face_verts[i].size());
        std::iota(indices.begin(), indices.end(), 0);
        std::sort(indices.begin(), indices.end(), [&](size_t a, size_t b) {
            Vec3 va = sub(face_verts[i][a], centroid);
            Vec3 vb = sub(face_verts[i][b], centroid);
            double angle_a = std::atan2(dot(va, perp), dot(va, ref));
            double angle_b = std::atan2(dot(vb, perp), dot(vb, ref));
            return angle_a < angle_b;
        });

        BrushFace face;
        face.material = planes[i].material;
        face.normal = normal;
        for (size_t idx : indices) {
            face.vertices.push_back(face_verts[i][idx]);
        }

        if (face.vertices.size() >= 3) {
            Vec3 computed_n = normalize(cross(
                sub(face.vertices[1], face.vertices[0]),
                sub(face.vertices[2], face.vertices[0])
            ));
            if (dot(computed_n, normal) < 0.0) {
                std::reverse(face.vertices.begin(), face.vertices.end());
            }
        }

        result.push_back(std::move(face));
    }

    return result;
}
