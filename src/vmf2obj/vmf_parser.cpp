#include "vmf_parser.h"

#include <cctype>
#include <cstdio>
#include <stdexcept>

namespace {

struct Tokenizer {
    std::string_view src;
    size_t pos = 0;

    void skip() {
        while (pos < src.size()) {
            if (std::isspace((unsigned char)src[pos])) {
                ++pos;
            } else if (pos + 1 < src.size() && src[pos] == '/' && src[pos + 1] == '/') {
                while (pos < src.size() && src[pos] != '\n') ++pos;
            } else {
                break;
            }
        }
    }

    std::string next() {
        skip();
        if (pos >= src.size()) return {};
        char c = src[pos];
        if (c == '{' || c == '}') {
            ++pos;
            return std::string(1, c);
        }
        if (c == '"') {
            ++pos;
            std::string r;
            while (pos < src.size() && src[pos] != '"') {
                if (src[pos] == '\\' && pos + 1 < src.size()) {
                    ++pos;
                    r += src[pos];
                } else {
                    r += src[pos];
                }
                ++pos;
            }
            if (pos < src.size()) ++pos;
            return r;
        }
        std::string r;
        while (pos < src.size()
               && !std::isspace((unsigned char)src[pos])
               && src[pos] != '{' && src[pos] != '}'
               && src[pos] != '"') {
            r += src[pos++];
        }
        return r;
    }

    bool peek_open() {
        size_t saved = pos;
        skip();
        bool r = pos < src.size() && src[pos] == '{';
        pos = saved;
        return r;
    }
};

KVNode parse_block(Tokenizer& tok, std::string key) {
    KVNode node;
    node.key = std::move(key);
    while (true) {
        std::string tok_str = tok.next();
        if (tok_str.empty() || tok_str == "}") break;
        if (tok.peek_open()) {
            tok.next();
            node.children.push_back(parse_block(tok, tok_str));
        } else {
            KVNode child;
            child.key = tok_str;
            child.value = tok.next();
            node.children.push_back(std::move(child));
        }
    }
    return node;
}

} // namespace

KVNode parse_document(std::string_view input) {
    Tokenizer tok{input, 0};
    KVNode root;
    root.key = "__root__";
    while (true) {
        std::string t = tok.next();
        if (t.empty()) break;
        if (tok.peek_open()) {
            tok.next();
            root.children.push_back(parse_block(tok, t));
        } else {
            KVNode child;
            child.key = t;
            child.value = tok.next();
            root.children.push_back(std::move(child));
        }
    }
    return root;
}

std::vector<SolidDef> extract_solids(const KVNode& root) {
    std::vector<SolidDef> solids;

    auto process_entity = [&](const KVNode& entity) {
        for (const auto& child : entity.children) {
            if (child.key != "solid") continue;
            SolidDef solid;
            for (const auto& sc : child.children) {
                if (sc.key != "side") continue;
                SideDef side;
                bool has_plane = false;
                for (const auto& sv : sc.children) {
                    if (sv.key == "plane") {
                        double x1, y1, z1, x2, y2, z2, x3, y3, z3;
                        int n = std::sscanf(sv.value.c_str(),
                            "(%lf %lf %lf) (%lf %lf %lf) (%lf %lf %lf)",
                            &x1, &y1, &z1, &x2, &y2, &z2, &x3, &y3, &z3);
                        if (n == 9) {
                            side.plane_points[0] = {x1, y1, z1};
                            side.plane_points[1] = {x2, y2, z2};
                            side.plane_points[2] = {x3, y3, z3};
                            has_plane = true;
                        }
                    } else if (sv.key == "material") {
                        side.material = sv.value;
                    }
                }
                if (has_plane) solid.sides.push_back(std::move(side));
            }
            if (!solid.sides.empty()) solids.push_back(std::move(solid));
        }
    };

    for (const auto& top : root.children) {
        if (top.key == "world" || top.key == "entity") {
            process_entity(top);
        }
    }

    return solids;
}
