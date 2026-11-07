#include <catch2/catch_test_macros.hpp>
#include <fstream>
#include <nlohmann/json.hpp>
#include <sstream>

#include "cf_engine/cli.hpp"
#include "cf_engine/errors.hpp"
#include "cf_engine/io.hpp"

using nlohmann::json;

namespace {

std::string read_file(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    REQUIRE(f.good());
    return {std::istreambuf_iterator<char>(f), std::istreambuf_iterator<char>()};
}

}  // namespace

TEST_CASE("echo of the fixture returns identical JSON") {
    std::string text = read_file(std::string(CF_ENGINE_FIXTURES_DIR) + "/echo.json");
    std::istringstream in(text);
    std::ostringstream out, err;

    REQUIRE(cf_engine::run({"echo"}, in, out, err) == 0);
    REQUIRE(json::parse(out.str()) == json::parse(text));
    REQUIRE(err.str().empty());
}

TEST_CASE("read_json throws invalid_json on empty input") {
    std::istringstream in("");
    try {
        cf_engine::read_json(in);
        FAIL("expected EngineError");
    } catch (const cf_engine::EngineError& e) {
        REQUIRE(e.code() == "invalid_json");
        REQUIRE(e.exit_code() == cf_engine::ExitCode::InvalidInput);
    }
}

TEST_CASE("read_json accepts a UTF-8 BOM (PowerShell pipes add one)") {
    std::istringstream in("\xEF\xBB\xBF{\"a\":1}");
    REQUIRE(cf_engine::read_json(in) == json{{"a", 1}});
}

TEST_CASE("stdout gets exactly one JSON line, details go to stderr") {
    std::istringstream in("{broken");
    std::ostringstream out, err;

    REQUIRE(cf_engine::run({"echo"}, in, out, err) == 3);

    std::string s = out.str();
    REQUIRE(s.back() == '\n');
    REQUIRE(s.find('\n') == s.size() - 1);
    REQUIRE(json::parse(s)["code"] == "invalid_json");
    REQUIRE(err.str().find("invalid_json") != std::string::npos);
}

TEST_CASE("write_error merges details into the error object") {
    std::ostringstream out;
    cf_engine::write_error(out, "dependency_cycle", "cycle found",
                           {{"cycle", {"a", "b", "a"}}});
    json body = json::parse(out.str());
    REQUIRE(body["code"] == "dependency_cycle");
    REQUIRE(body["message"] == "cycle found");
    REQUIRE(body["cycle"] == json{"a", "b", "a"});
}

TEST_CASE("invalid UTF-8 in strings does not break the output") {
    std::ostringstream out;
    cf_engine::write_json(out, {{"title", std::string("bad \xC3\x28 byte")}});
    REQUIRE(json::accept(out.str()));
}
