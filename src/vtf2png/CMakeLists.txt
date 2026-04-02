add_executable(vtf2png main.cpp)

target_link_libraries(vtf2png PRIVATE VTFLib13)
target_include_directories(vtf2png PRIVATE
    ${vtflib_SOURCE_DIR}/src
    ${vtflib_BINARY_DIR}/src
    ${stb_SOURCE_DIR}
)
