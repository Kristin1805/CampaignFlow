from django.urls import path

from campaignflow.content.apis import (
    ContentListApi, CampaignContentApi, ContentDetailsApi,
    ContentStatusApi, ContentStatusHistoryApi, ContentDuplicateApi,
    ContentPlatformListApi, ContentPlatformDetailsApi,
    ContentFormatListApi, ContentFormatDetailsApi,
)


urlpatterns = [
    path("workspaces/<uuid:workspace_id>/content/", ContentListApi.as_view(), name="content-list"),
    path("workspaces/<uuid:workspace_id>/campaigns/<uuid:campaign_id>/content/", CampaignContentApi.as_view(), name="campaign-content"),
    path("workspaces/<uuid:workspace_id>/content/<uuid:content_id>/", ContentDetailsApi.as_view(), name="content-details"),
    path("workspaces/<uuid:workspace_id>/content/<uuid:content_id>/status/", ContentStatusApi.as_view(), name="content-status"),
    path("workspaces/<uuid:workspace_id>/content/<uuid:content_id>/status-history/", ContentStatusHistoryApi.as_view(), name="content-status-history"),
    path("workspaces/<uuid:workspace_id>/content/<uuid:content_id>/duplicate/", ContentDuplicateApi.as_view(), name="content-duplicate"),
    path("workspaces/<uuid:workspace_id>/content-platforms/", ContentPlatformListApi.as_view(), name="content-platform-list"),
    path("workspaces/<uuid:workspace_id>/content-platforms/<uuid:definition_id>/", ContentPlatformDetailsApi.as_view(), name="content-platform-details"),
    path("workspaces/<uuid:workspace_id>/content-formats/", ContentFormatListApi.as_view(), name="content-format-list"),
    path("workspaces/<uuid:workspace_id>/content-formats/<uuid:definition_id>/", ContentFormatDetailsApi.as_view(), name="content-format-details"),
]