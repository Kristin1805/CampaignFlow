build commands:

cmake -S CppEngine -B CppEngine/build
cmake --build CppEngine/build
./CppEngine/build/cf_engine


add path to cmake:

$env:Path += ";C:\Program Files\CMake\bin"
cmake --version