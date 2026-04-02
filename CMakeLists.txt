cmake_minimum_required(VERSION 3.25)
project(cssmap2sm64 LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR})
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_RELEASE ${CMAKE_BINARY_DIR})
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_DEBUG ${CMAKE_BINARY_DIR})

include(FetchContent)

set(USE_LIBTXC_DXTN OFF CACHE BOOL "" FORCE)
set(USE_NVDXT        OFF CACHE BOOL "" FORCE)
set(BUILD_DOCS       OFF CACHE BOOL "" FORCE)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(CMAKE_POLICY_VERSION_MINIMUM 3.5 CACHE STRING "" FORCE)
set(FETCHCONTENT_UPDATES_DISCONNECTED ON CACHE BOOL "" FORCE)

FetchContent_Declare(
    VTFLib
    URL https://github.com/panzi/VTFLib/archive/refs/heads/master.zip
)
FetchContent_MakeAvailable(VTFLib)

get_target_property(_vtflib_srcs VTFLib13 SOURCES)
list(FILTER _vtflib_srcs EXCLUDE REGEX "\\.rc$")
set_property(TARGET VTFLib13 PROPERTY SOURCES ${_vtflib_srcs})

FetchContent_Declare(
    stb
    URL https://github.com/nothings/stb/archive/refs/heads/master.zip
)
FetchContent_MakeAvailable(stb)

add_subdirectory(src/vmf2obj)
add_subdirectory(src/vtf2png)
