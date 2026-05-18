cmake_minimum_required(VERSION 3.16)

project(calibration_bind)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Find pybind11
find_package(pybind11 REQUIRED)

# Path to PokeFinder source
set(POKEFINDER_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../wasm/lib/PokeFinder/Source")

# Build PokeFinderCore as a static library
add_subdirectory("${POKEFINDER_SOURCE_DIR}/Core" "${CMAKE_BINARY_DIR}/PokeFinderCore")

# Create the pybind11 module
pybind11_add_module(calibration_bind calibration_bind.cpp)

target_include_directories(calibration_bind PRIVATE
    "${POKEFINDER_SOURCE_DIR}/Core/External/fph"
    "${POKEFINDER_SOURCE_DIR}/Core/External/nlohmann"
    "${POKEFINDER_SOURCE_DIR}"
)

target_link_libraries(calibration_bind PRIVATE PokeFinderCore)

# Optimize
if(CMAKE_BUILD_TYPE STREQUAL "Release")
    target_compile_options(calibration_bind PRIVATE -O3 -march=native)
endif()
