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

    add_executable(
        bpt_core_tests

        tests/test_visual_hull.cpp
    )

    target_link_libraries(
        bpt_core_tests

        PRIVATE
            bpt_core
    )

    target_include_directories(
        bpt_core_tests

        PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/include
    )

    add_test(
        NAME bpt_core_tests
        COMMAND bpt_core_tests
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