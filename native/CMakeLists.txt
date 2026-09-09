cmake_minimum_required(VERSION 3.20)

project(
    blender_projection_tool_native
    VERSION 0.1.0
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(
    CMAKE_POSITION_INDEPENDENT_CODE
    ON
)

# ---------------------------------------------------------
# Library
# ---------------------------------------------------------

add_library(
    bpt_core
    SHARED

    src/api.cpp
    src/visual_hull.cpp
    src/mesh.cpp
    src/surface_nets.cpp
)

target_include_directories(
    bpt_core

    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# ---------------------------------------------------------
# Compiler warnings
# ---------------------------------------------------------

if(MSVC)

    target_compile_options(
        bpt_core
        PRIVATE
            /W4
            /permissive-
    )

else()

    target_compile_options(
        bpt_core
        PRIVATE
            -Wall
            -Wextra
            -Wpedantic
    )

endif()

# ---------------------------------------------------------
# Export symbols
# ---------------------------------------------------------

target_compile_definitions(
    bpt_core

    PRIVATE
        BPT_CORE_BUILD
)

# ---------------------------------------------------------
# Output
# ---------------------------------------------------------

set_target_properties(
    bpt_core

    PROPERTIES
        OUTPUT_NAME "bpt_core"
)

if(WIN32)

    set_target_properties(
        bpt_core

        PROPERTIES
            WINDOWS_EXPORT_ALL_SYMBOLS OFF
    )

endif()

# ---------------------------------------------------------
# Tests
# ---------------------------------------------------------

option(
    BPT_BUILD_TESTS
    "Build native tests"
    ON
)

if(BPT_BUILD_TESTS)

    enable_testing()

    # -----------------------------------------------------
    # Test helper
    # -----------------------------------------------------

    function(
        bpt_add_test
        target_name
        source_file
    )

        add_executable(
            ${target_name}
            ${source_file}
        )

        target_link_libraries(
            ${target_name}

            PRIVATE
                bpt_core
        )

        target_include_directories(
            ${target_name}

            PRIVATE
                ${CMAKE_CURRENT_SOURCE_DIR}/include
                ${CMAKE_CURRENT_SOURCE_DIR}/tests
        )

        if(MSVC)

            target_compile_options(
                ${target_name}

                PRIVATE
                    /W4
                    /permissive-
            )

        else()

            target_compile_options(
                ${target_name}

                PRIVATE
                    -Wall
                    -Wextra
                    -Wpedantic
            )

        endif()

        add_test(
            NAME ${target_name}
            COMMAND ${target_name}
        )

    endfunction()

    # -----------------------------------------------------
    # Visual Hull
    # -----------------------------------------------------

    bpt_add_test(
        bpt_visual_hull_tests
        tests/test_visual_hull.cpp
    )

    # -----------------------------------------------------
    # Historical block mesher
    # -----------------------------------------------------

    bpt_add_test(
        bpt_mesh_blocks_tests
        tests/test_mesh_blocks.cpp
    )

    # -----------------------------------------------------
    # Surface Nets
    # -----------------------------------------------------

    bpt_add_test(
        bpt_surface_nets_tests
        tests/test_surface_nets.cpp
    )

    # -----------------------------------------------------
    # Public mesh API
    # -----------------------------------------------------

    bpt_add_test(
        bpt_mesh_api_tests
        tests/test_mesh_api.cpp
    )

endif()

# ---------------------------------------------------------
# Install
# ---------------------------------------------------------

install(
    TARGETS bpt_core

    RUNTIME DESTINATION .
    LIBRARY DESTINATION .
    ARCHIVE DESTINATION .
)