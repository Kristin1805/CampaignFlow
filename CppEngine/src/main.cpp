#include <iostream>
#include <iterator>
#include <nlohmann/json.hpp>
using json = nlohmann::json;
using namespace std;

int main(){

    // echo '{"hello":"world"}' | ./build/cf_engine.exe
    //test cin input ^^^

    std::string raw((std::istreambuf_iterator<char>(std::cin)),
                     std::istreambuf_iterator<char>());
    json input;
    try {
        input = json::parse(raw);
    } catch (const json::parse_error& e) {
        std::cout << json{{"ok", false}, {"code", "invalid_json"},
                          {"message", e.what()}}.dump() << "\n";
        return 2;   // код 2 = плохой ввод
    }
    std::cout << json{{"ok", true}, {"echo", input}}.dump() << "\n";

    return 0;
}