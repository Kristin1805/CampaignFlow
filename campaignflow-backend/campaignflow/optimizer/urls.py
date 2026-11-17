from django.urls import path

from campaignflow.optimizer.apis import (
    OptimizationApplyApi,
    OptimizationDetailsApi,
    OptimizationHistoryApi,
    OptimizationPreviewApi,
)


urlpatterns = [
    path("campaigns/<uuid:campaign_id>/optimize/", OptimizationPreviewApi.as_view(), name="campaign-optimize",),
    path("optimization-runs/<uuid:run_id>/apply/", OptimizationApplyApi.as_view(), name="optimization-run-apply",),
    path("campaigns/<uuid:campaign_id>/optimization-runs/", OptimizationHistoryApi.as_view(), name="optimization-history",),
    path("optimization-runs/<uuid:run_id>/", OptimizationDetailsApi.as_view(), name="optimization-run-details",),
]