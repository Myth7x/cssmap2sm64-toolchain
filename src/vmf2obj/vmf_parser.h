#pragma once

#include <array>
#include <string>
#include <string_view>
#include <vector>

struct KVNode {
    std::string key;
    std::string value;
    std::vector<KVNode> children;
};

KVNode parse_document(std::string_view input);

struct SideDef {
    std::array<std::array<double, 3>, 3> plane_points;
    std::string material;
};

struct SolidDef {
    std::vector<SideDef> sides;
};

std::vector<SolidDef> extract_solids(const KVNode& root);
