from rest_framework.exceptions import APIException


class OptimizationConflict(APIException):
    status_code = 409
    default_detail = "The optimization plan is stale."
    default_code = "optimization_conflict"


class OptimizerTimeout(APIException):
    status_code = 503
    default_code = "optimizer_timeout"
    default_detail = "Optimization engine timed out."


class OptimizerInternalError(APIException):
    status_code = 500
    default_code = "optimizer_internal_error"
    default_detail = "Optimization engine failed."


class OptimizerInvalidInput(OptimizerInternalError):
    default_code = "invalid_optimizer_input"


class OptimizerInfeasible(APIException):
    status_code = 422
    default_code = "optimizer_infeasible"
    default_detail = "No feasible optimization plan was found."


class OptimizerDependencyCycle(APIException):
    status_code = 422
    default_code = "dependency_cycle"

    def __init__(self, *, cycle=None, message=None):
        super().__init__({
            "code": "dependency_cycle",
            "message": message or "Task dependency cycle detected.",
            "cycle": cycle or [],
        })