from django.urls import path

from campaignflow.optimizer.apis import OptimizationApplyApi, OptimizationPreviewApi

urlpatterns = [
    path("campaigns/<uuid:campaign_id>/optimize/", OptimizationPreviewApi.as_view(), name="campaign-optimize",),
    path("optimization-runs/<uuid:run_id>/apply/", OptimizationApplyApi.as_view(), name="optimization-run-apply",),
]