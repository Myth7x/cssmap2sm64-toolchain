#pragma once

#include "brush_solver.h"
#include <string>
#include <vector>

void write_obj(const std::vector<BrushFace>& faces,
               const std::string& obj_path,
               const std::string& mtl_path,
               double scale);
