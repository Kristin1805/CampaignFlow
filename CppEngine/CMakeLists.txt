cmake_minimum_required(VERSION 3.16)
project(cf_engine VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(CF_ENGINE_BUILD_TESTS "Build Catch2 unit tests" ON)

include(FetchContent)
FetchContent_Declare(json
  URL https://github.com/nlohmann/json/releases/download/v3.11.3/json.tar.xz
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_MakeAvailable(json)

# Core logic lives in a library so tests can link it without main().
add_library(cf_engine_core
  src/cli.cpp
  src/io.cpp)
target_include_directories(cf_engine_core PUBLIC include)
target_link_libraries(cf_engine_core PUBLIC nlohmann_json::nlohmann_json)
target_compile_definitions(cf_engine_core PUBLIC
  CF_ENGINE_VERSION="${PROJECT_VERSION}")

if(MSVC)
  target_compile_options(cf_engine_core PRIVATE /W4 /utf-8)
else()
  target_compile_options(cf_engine_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

add_executable(cf_engine src/main.cpp)
target_link_libraries(cf_engine PRIVATE cf_engine_core)

if(CF_ENGINE_BUILD_TESTS)
  FetchContent_Declare(Catch2
    GIT_REPOSITORY https://github.com/catchorg/Catch2.git
    GIT_TAG v3.7.1)
  FetchContent_MakeAvailable(Catch2)

  enable_testing()
  add_executable(cf_engine_tests
    tests/test_cli.cpp
    tests/test_io.cpp)
  target_link_libraries(cf_engine_tests PRIVATE cf_engine_core Catch2::Catch2WithMain)
  target_compile_definitions(cf_engine_tests PRIVATE
    CF_ENGINE_FIXTURES_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")

  list(APPEND CMAKE_MODULE_PATH ${catch2_SOURCE_DIR}/extras)
  include(Catch)
  catch_discover_tests(cf_engine_tests)
endif()
