#include "cf_engine/cli.hpp"

#include <iostream>
#include <iterator>
#include <nlohmann/json.hpp>

#include "cf_engine/exit_codes.hpp"

namespace cf_engine {
namespace {

using json = nlohmann::json;

void write_error(std::ostream& out, const std::string& code,
                 const std::string& message) {
    out << json{{"code", code}, {"message", message}}.dump() << "\n";
}

const char* usage() {
    return "usage: cf_engine <optimize|validate|echo> < input.json\n"
           "       cf_engine --version\n";
}

int echo(std::istream& in, std::ostream& out) {
    std::string raw((std::istreambuf_iterator<char>(in)),
                    std::istreambuf_iterator<char>());
    json input;
    try {
        input = json::parse(raw);
    } catch (const json::parse_error& e) {
        write_error(out, "invalid_json", e.what());
        return to_int(ExitCode::InvalidInput);
    }
    out << json{{"echo", input}}.dump() << "\n";
    return to_int(ExitCode::Ok);
}

}  // namespace

int run(const std::vector<std::string>& args, std::istream& in,
        std::ostream& out, std::ostream& err) {
    if (args.empty()) {
        err << usage();
        write_error(out, "invalid_command", "missing command");
        return to_int(ExitCode::InvalidInput);
    }

    const std::string& command = args[0];

    if (command == "--version") {
        out << json{{"engine_version", CF_ENGINE_VERSION}}.dump() << "\n";
        return to_int(ExitCode::Ok);
    }
    if (command == "echo") {
        return echo(in, out);
    }
    if (command == "optimize" || command == "validate") {
        // Implemented in later tickets (SCRUM-40, SCRUM-50).
        write_error(out, "not_implemented", command + " is not implemented yet");
        return to_int(ExitCode::InvalidInput);
    }

    err << usage();
    write_error(out, "invalid_command", "unknown command: " + command);
    return to_int(ExitCode::InvalidInput);
}

}  // namespace cf_engine
