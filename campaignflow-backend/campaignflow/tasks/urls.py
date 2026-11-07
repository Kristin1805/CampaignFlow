
from django.urls import path

from campaignflow.tasks.apis import CampaignTasksApi, TaskDetailApi, TaskDependencyDeleteApi, \
    TaskDependencyListCreateApi, TaskStatusUpdateApi, TaskStatusHistoryApi

urlpatterns = [
    path("workspaces/<uuid:workspace_id>/campaigns/<uuid:campaign_id>/tasks/", CampaignTasksApi.as_view(), name="campaign-tasks",),
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/", TaskDetailApi.as_view(), name="task-detail",),


    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/dependencies/", TaskDependencyListCreateApi.as_view(), name="task-dependency-list-create",),
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/dependencies/<uuid:dependency_id>/", TaskDependencyDeleteApi.as_view(), name="task-dependency-delete",),

    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/status/", TaskStatusUpdateApi.as_view(), name="task-status-update",),
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/status-history/", TaskStatusHistoryApi.as_view(), name="task-status-history",),
]
