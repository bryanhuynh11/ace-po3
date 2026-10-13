cmake_minimum_required(VERSION 3.16)
project(ace_po3 CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)   # lets Cursor / clangd understand the code
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# The engine as a small library
add_library(po3 STATIC src/engine.cpp)
target_include_directories(po3 PUBLIC include)
set_target_properties(po3 PROPERTIES POSITION_INDEPENDENT_CODE ON)
if(MSVC)
  target_compile_options(po3 PRIVATE /W4)
else()
  target_compile_options(po3 PRIVATE -Wall -Wextra -Wpedantic)
endif()

# Level 5: command-line runner
add_executable(po3_cli src/main.cpp)
target_link_libraries(po3_cli PRIVATE po3)

# Level 6: Python module (only if pybind11 is installed: pip install pybind11)
find_package(Python COMPONENTS Interpreter Development.Module QUIET)
if(Python_FOUND)
  execute_process(COMMAND ${Python_EXECUTABLE} -m pybind11 --cmakedir
                  OUTPUT_VARIABLE pybind11_DIR OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
endif()
find_package(pybind11 CONFIG QUIET)
if(pybind11_FOUND)
  pybind11_add_module(po3cpp bindings/po3_bindings.cpp)
  target_link_libraries(po3cpp PRIVATE po3)
  message(STATUS "pybind11 found: building Python module po3cpp")
else()
  message(STATUS "pybind11 not found: skipping Python module (pip install pybind11)")
endif()
