#include <catch2/catch_test_macros.hpp>
#include <nlohmann/json.hpp>
#include <sstream>

#include "cf_engine/cli.hpp"
#include "cf_engine/exit_codes.hpp"

using nlohmann::json;

namespace {

struct Result {
    int code;
    json out;
};

Result run_cli(std::vector<std::string> args, const std::string& stdin_text = "") {
    std::istringstream in(stdin_text);
    std::ostringstream out, err;
    int code = cf_engine::run(args, in, out, err);
    return {code, json::parse(out.str())};
}

}  // namespace

TEST_CASE("version flag prints the engine version") {
    auto r = run_cli({"--version"});
    REQUIRE(r.code == 0);
    REQUIRE(r.out["engine_version"] == "1.0.0");
}

TEST_CASE("missing or unknown command is invalid input") {
    REQUIRE(run_cli({}).code == 3);

    auto r = run_cli({"bogus"});
    REQUIRE(r.code == 3);
    REQUIRE(r.out["code"] == "invalid_command");
}

TEST_CASE("echo returns the input unchanged") {
    auto r = run_cli({"echo"}, R"({"title":"Graphic Design","n":1})");
    REQUIRE(r.code == 0);
    REQUIRE(r.out == json{{"title", "Graphic Design"}, {"n", 1}});
}

TEST_CASE("echo keeps UTF-8 text") {
    auto r = run_cli({"echo"}, R"({"title":"Копирайтинг"})");
    REQUIRE(r.code == 0);
    REQUIRE(r.out["title"] == "Копирайтинг");
}

TEST_CASE("not yet implemented commands still answer with JSON") {
    for (const char* cmd : {"optimize", "validate"}) {
        auto r = run_cli({cmd}, "{}");
        REQUIRE(r.code == 3);
        REQUIRE(r.out["code"] == "not_implemented");
    }
}

TEST_CASE("broken JSON exits with 3, not 2 (2 is reserved for cycles)") {
    for (const char* bad : {"", "not json", "{\"a\":"}) {
        auto r = run_cli({"echo"}, bad);
        REQUIRE(r.code == cf_engine::to_int(cf_engine::ExitCode::InvalidInput));
        REQUIRE(r.out["code"] == "invalid_json");
    }
}
