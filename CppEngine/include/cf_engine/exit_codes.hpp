#pragma once

namespace cf_engine {

// Contract with Django's OptimizerService. Never return anything else.
enum class ExitCode : int {
    Ok = 0,
    DependencyCycle = 2,
    InvalidInput = 3,
    Infeasible = 4,  // e.g. no person has the skill a task requires
};

inline int to_int(ExitCode code) { return static_cast<int>(code); }

}  // namespace cf_engine
