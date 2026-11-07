from django.urls import path
from campaignflow.optimizer.apis import OptimizationApplyApi

urlpatterns = [
    path("runs/<uuid:run_id>/apply/", OptimizationApplyApi.as_view(), name="optimization-run-apply"),
]