from django.urls import path

from campaignflow.organization.apis import (
    WorkspaceDetailApi,
    WorkspaceListCreateApi,
    WorkspaceInvitationListCreateApi,
    WorkspaceInvitationAcceptApi,
    WorkspaceInvitationRevokeApi,
)

urlpatterns = [
    path("workspaces/", WorkspaceListCreateApi.as_view(), name="workspace-list-create"),
    path("workspaces/<uuid:workspace_id>/", WorkspaceDetailApi.as_view(), name="workspace-detail"),

    path("workspaces/<uuid:workspace_id>/invitations/", WorkspaceInvitationListCreateApi.as_view(), name="workspace-invitation-list-create"),
    path("workspace-invitations/<str:token>/accept/", WorkspaceInvitationAcceptApi.as_view(), name="workspace-invitation-accept"),
    path("workspaces/<uuid:workspace_id>/invitations/<uuid:invitation_id>/", WorkspaceInvitationRevokeApi.as_view(), name="workspace-invitation-revoke"),
]