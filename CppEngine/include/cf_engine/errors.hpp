#pragma once

#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>

#include "cf_engine/exit_codes.hpp"

namespace cf_engine {

// Thrown anywhere in the engine; cli::run turns it into
// {"code": ..., "message": ..., ...details} on stdout and the matching exit code.
class EngineError : public std::runtime_error {
public:
    EngineError(ExitCode exit_code, std::string code, const std::string& message,
                nlohmann::json details = nlohmann::json::object())
        : std::runtime_error(message),
          exit_code_(exit_code),
          code_(std::move(code)),
          details_(std::move(details)) {}

    ExitCode exit_code() const { return exit_code_; }
    const std::string& code() const { return code_; }
    const nlohmann::json& details() const { return details_; }

private:
    ExitCode exit_code_;
    std::string code_;
    nlohmann::json details_;
};

}  // namespace cf_engine
