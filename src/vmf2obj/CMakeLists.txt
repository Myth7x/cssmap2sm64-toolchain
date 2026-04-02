add_executable(vmf2obj
    main.cpp
    vmf_parser.cpp
    brush_solver.cpp
    obj_writer.cpp
)

target_compile_features(vmf2obj PRIVATE cxx_std_23)
