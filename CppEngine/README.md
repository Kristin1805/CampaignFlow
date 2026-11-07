# cf_engine

C++17 CLI used by Django's OptimizerService. Reads one JSON object from stdin,
writes one JSON object to stdout. Logs and usage go to stderr.

## Build

```
cmake -S CppEngine -B CppEngine/build
cmake --build CppEngine/build
ctest --test-dir CppEngine/build --output-on-failure
```

Tests are built by default; pass `-DCF_ENGINE_BUILD_TESTS=OFF` to skip Catch2.

## Commands

```
cf_engine --version
cf_engine echo     < input.json   # returns {"echo": <input>}
cf_engine validate < input.json   # not implemented yet
cf_engine optimize < input.json   # not implemented yet
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | OK |
| 2 | Dependency cycle (stdout contains the cycle) |
| 3 | Invalid input / invalid JSON / unknown command |
| 4 | Infeasible (e.g. nobody has the required skill) |

On any non-zero exit stdout is still a JSON object: `{"code": "...", "message": "..."}`.
