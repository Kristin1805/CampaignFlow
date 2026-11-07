#include "cf_engine/cli.hpp"

#include <exception>
#include <ostream>

#include "cf_engine/errors.hpp"
#include "cf_engine/exit_codes.hpp"
#include "cf_engine/io.hpp"

namespace cf_engine {
namespace {

using json = nlohmann::json;

const char* usage() {
    return "usage: cf_engine <optimize|validate|echo> < input.json\n"
           "       cf_engine --version\n";
}

int dispatch(const std::vector<std::string>& args, std::istream& in,
             std::ostream& out, std::ostream& err) {
    if (args.empty()) {
        err << usage();
        throw EngineError(ExitCode::InvalidInput, "invalid_command", "missing command");
    }

    const std::string& command = args[0];

    if (command == "--version") {
        write_json(out, {{"engine_version", CF_ENGINE_VERSION}});
        return to_int(ExitCode::Ok);
    }
    if (command == "echo") {
        write_json(out, read_json(in));
        return to_int(ExitCode::Ok);
    }
    if (command == "optimize" || command == "validate") {
        // Implemented in later tickets (SCRUM-40, SCRUM-50).
        throw EngineError(ExitCode::InvalidInput, "not_implemented",
                          command + " is not implemented yet");
    }

    err << usage();
    throw EngineError(ExitCode::InvalidInput, "invalid_command",
                      "unknown command: " + command);
}

}  // namespace

int run(const std::vector<std::string>& args, std::istream& in,
        std::ostream& out, std::ostream& err) {
    // Django parses stdout, so every path must end with one JSON object there
    // and an exit code from the contract — never a crash or exit 1.
    try {
        return dispatch(args, in, out, err);
    } catch (const EngineError& e) {
        err << "cf_engine: " << e.code() << ": " << e.what() << "\n";
        write_error(out, e.code(), e.what(), e.details());
        return to_int(e.exit_code());
    } catch (const std::exception& e) {
        err << "cf_engine: internal_error: " << e.what() << "\n";
        write_error(out, "internal_error", e.what());
        return to_int(ExitCode::InvalidInput);
    }
}

}  // namespace cf_engine
