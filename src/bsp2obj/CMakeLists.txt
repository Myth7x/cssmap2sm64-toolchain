add_executable(bsp2obj
    main.cpp
    bsp_reader.cpp
)

target_compile_features(bsp2obj PRIVATE cxx_std_23)
