#pragma once

#include <array>
#include <string>
#include <vector>

using Vec3 = std::array<double, 3>;

struct Plane {
    Vec3 normal;
    double d;
    std::string material;
};

struct BrushFace {
    std::vector<Vec3> vertices;
    Vec3 normal;
    std::string material;
};

Plane plane_from_points(const Vec3& p1, const Vec3& p2, const Vec3& p3, const std::string& material);
std::vector<BrushFace> solve_brush(std::vector<Plane>& planes);
