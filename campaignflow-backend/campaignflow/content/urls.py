from django.urls import path

from campaignflow.content.apis import (
    ContentListApi, CampaignContentApi, ContentDetailsApi,
    ContentStatusApi, ContentStatusHistoryApi, ContentDuplicateApi,
    ContentPlatformListApi, ContentPlatformDetailsApi,
    ContentFormatListApi, ContentFormatDetailsApi,
    ContentCalendarApi, ContentCalendarSummaryApi,
    ContentCalendarUnscheduledApi, ContentCalendarConflictsApi,
    ContentRescheduleApi, ContentBulkRescheduleApi,
)


urlpatterns = [
    # Content management
    path("workspaces/<uuid:workspace_id>/content/", ContentListApi.as_view(), name="content-list"),
    path("workspaces/<uuid:workspace_id>/campaigns/<uuid:campaign_id>/content/", CampaignContentApi.as_view(), name="campaign-content"),
    path("workspaces/<uuid:workspace_id>/content/<uuid:content_id>/", ContentDetailsApi.as_view(), name="content-details"),
    path("workspaces/<uuid:workspace_id>/content/<uuid:content_id>/status/", ContentStatusApi.as_view(), name="content-status"),
    path("workspaces/<uuid:workspace_id>/content/<uuid:content_id>/status-history/", ContentStatusHistoryApi.as_view(), name="content-status-history"),
    path("workspaces/<uuid:workspace_id>/content/<uuid:content_id>/duplicate/", ContentDuplicateApi.as_view(), name="content-duplicate"),
    # Content platforms
    path("workspaces/<uuid:workspace_id>/content-platforms/", ContentPlatformListApi.as_view(), name="content-platform-list"),
    path("workspaces/<uuid:workspace_id>/content-platforms/<uuid:definition_id>/", ContentPlatformDetailsApi.as_view(), name="content-platform-details"),
    # Content formats
    path("workspaces/<uuid:workspace_id>/content-formats/", ContentFormatListApi.as_view(), name="content-format-list"),
    path("workspaces/<uuid:workspace_id>/content-formats/<uuid:definition_id>/", ContentFormatDetailsApi.as_view(), name="content-format-details"),
    # Content calendar
    path("workspaces/<uuid:workspace_id>/content-calendar/", ContentCalendarApi.as_view(), name="content-calendar"),
    path("workspaces/<uuid:workspace_id>/campaigns/<uuid:campaign_id>/content-calendar/", ContentCalendarApi.as_view(), name="campaign-content-calendar"),
    path("workspaces/<uuid:workspace_id>/content-calendar/summary/", ContentCalendarSummaryApi.as_view(), name="content-calendar-summary"),
    path("workspaces/<uuid:workspace_id>/content-calendar/unscheduled/", ContentCalendarUnscheduledApi.as_view(), name="content-calendar-unscheduled"),
    path("workspaces/<uuid:workspace_id>/content-calendar/conflicts/", ContentCalendarConflictsApi.as_view(), name="content-calendar-conflicts"),
    path("workspaces/<uuid:workspace_id>/content/<uuid:content_id>/reschedule/", ContentRescheduleApi.as_view(), name="content-reschedule"),
    path("workspaces/<uuid:workspace_id>/content-calendar/bulk-reschedule/", ContentBulkRescheduleApi.as_view(), name="content-bulk-reschedule"),
]