#pragma once

#include <iosfwd>
#include <string>
#include <vector>

namespace cf_engine {

// Entry point used by main() and by tests. `args` excludes the program name.
// Writes exactly one JSON object to `out`; human-readable details go to `err`.
int run(const std::vector<std::string>& args, std::istream& in,
        std::ostream& out, std::ostream& err);

}  // namespace cf_engine
