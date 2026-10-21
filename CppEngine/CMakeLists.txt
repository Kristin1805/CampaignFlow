cmake_minimum_required(VERSION 3.16)
project(cf_engine CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(cf_engine src/main.cpp)
target_include_directories(cf_engine PRIVATE include)

include(FetchContent)
FetchContent_Declare(json
  URL https://github.com/nlohmann/json/releases/download/v3.11.3/json.tar.xz)
FetchContent_MakeAvailable(json)
target_link_libraries(cf_engine PRIVATE nlohmann_json::nlohmann_json)