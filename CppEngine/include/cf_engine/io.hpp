#pragma once

#include <iosfwd>
#include <nlohmann/json.hpp>
#include <string>

namespace cf_engine {

// Reads the whole stream and parses it as one JSON value.
// Throws EngineError(InvalidInput, "invalid_json") on empty or broken input.
nlohmann::json read_json(std::istream& in);

// The only way anything should reach stdout: one JSON object per line.
void write_json(std::ostream& out, const nlohmann::json& value);

// {"code": code, "message": message} merged with the keys of `details`.
void write_error(std::ostream& out, const std::string& code,
                 const std::string& message,
                 const nlohmann::json& details = nlohmann::json::object());

}  // namespace cf_engine
