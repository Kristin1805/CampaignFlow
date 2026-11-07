#include "cf_engine/io.hpp"

#include <istream>
#include <iterator>
#include <ostream>

#include "cf_engine/errors.hpp"

namespace cf_engine {

using json = nlohmann::json;

json read_json(std::istream& in) {
    std::string raw((std::istreambuf_iterator<char>(in)),
                    std::istreambuf_iterator<char>());
    try {
        return json::parse(raw);
    } catch (const json::parse_error& e) {
        throw EngineError(ExitCode::InvalidInput, "invalid_json", e.what());
    }
}

void write_json(std::ostream& out, const json& value) {
    // Invalid UTF-8 in strings is replaced instead of throwing mid-write.
    out << value.dump(-1, ' ', false, json::error_handler_t::replace) << "\n";
    out.flush();
}

void write_error(std::ostream& out, const std::string& code,
                 const std::string& message, const json& details) {
    json body = details.is_object() ? details : json::object();
    body["code"] = code;
    body["message"] = message;
    write_json(out, body);
}

}  // namespace cf_engine
