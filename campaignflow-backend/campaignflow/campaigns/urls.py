
from django.urls import path

from campaignflow.campaigns.apis import (
    CampaignListCreateApi,
    CampaignDetailApi,
    CampaignStatusApi,
)


urlpatterns = [
    path("workspaces/<uuid:workspace_id>/campaigns/",CampaignListCreateApi.as_view(), name="campaign-list-create",),
    path("workspaces/<uuid:workspace_id>/campaigns/<uuid:campaign_id>/", CampaignDetailApi.as_view(), name="campaign-detail",),
    path("workspaces/<uuid:workspace_id>/campaigns/<uuid:campaign_id>/status/", CampaignStatusApi.as_view(), name="campaign-status",),
]
