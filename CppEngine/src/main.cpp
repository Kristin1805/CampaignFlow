#include <iostream>
#include <string>
#include <vector>

#include "cf_engine/cli.hpp"

int main(int argc, char* argv[]) {
    // echo '{"hello":"world"}' | ./build/cf_engine.exe echo
    std::vector<std::string> args(argv + 1, argv + argc);
    return cf_engine::run(args, std::cin, std::cout, std::cerr);
}
