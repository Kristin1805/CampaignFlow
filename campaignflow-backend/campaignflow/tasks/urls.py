
from django.urls import path

from campaignflow.tasks.apis import CampaignTasksApi, TaskDetailApi, TaskDependencyDeleteApi, \
    TaskDependencyListCreateApi

urlpatterns = [
    path("workspaces/<uuid:workspace_id>/campaigns/<uuid:campaign_id>/tasks/", CampaignTasksApi.as_view(), name="campaign-tasks",),
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/", TaskDetailApi.as_view(), name="task-detail",),


    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/dependencies/", TaskDependencyListCreateApi.as_view(), name="task-dependency-list-create",),
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/dependencies/<uuid:dependency_id>/", TaskDependencyDeleteApi.as_view(), name="task-dependency-delete",),
]
