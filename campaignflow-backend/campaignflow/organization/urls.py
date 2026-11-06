from django.urls import path

from campaignflow.organization.apis import (WorkspaceDetailApi, WorkspaceListCreateApi,)

urlpatterns = [
    path("workspaces/", WorkspaceListCreateApi.as_view(),
        name="workspace-list-create",
    ),
    path("workspaces/<uuid:workspace_id>/", WorkspaceDetailApi.as_view(), name="workspace-detail",),
]