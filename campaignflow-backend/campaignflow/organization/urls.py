from django.urls import path

from campaignflow.organization.apis import (
    WorkspaceDetailApi,
    WorkspaceListCreateApi,
    WorkspaceInvitationListCreateApi,
    WorkspaceInvitationAcceptApi,
    WorkspaceInvitationRevokeApi, WorkspaceMemberListApi, WorkspaceMemberDetailApi, SkillListApi,
    WorkspaceMemberSkillListCreateApi, WorkspaceMemberSkillDeleteApi, WorkspaceMemberAvailabilityApi,
    WorkspaceMemberTimeOffListCreateApi, WorkspaceMemberTimeOffDeleteApi, WorkspaceTeamCapacityApi,
    WorkspaceMemberCapacityApi,
)

urlpatterns = [
    path("workspaces/", WorkspaceListCreateApi.as_view(), name="workspace-list-create"),
    path("workspaces/<uuid:workspace_id>/", WorkspaceDetailApi.as_view(), name="workspace-detail"),

    path("workspaces/<uuid:workspace_id>/invitations/", WorkspaceInvitationListCreateApi.as_view(), name="workspace-invitation-list-create"),
    path("workspace-invitations/<str:token>/accept/", WorkspaceInvitationAcceptApi.as_view(), name="workspace-invitation-accept"),
    path("workspaces/<uuid:workspace_id>/invitations/<uuid:invitation_id>/", WorkspaceInvitationRevokeApi.as_view(), name="workspace-invitation-revoke"),
    path("workspaces/<uuid:workspace_id>/members/", WorkspaceMemberListApi.as_view(), name="workspace-member-list"),
    path("workspaces/<uuid:workspace_id>/members/<uuid:member_id>/", WorkspaceMemberDetailApi.as_view(), name="workspace-member-detail"),

    path("skills/", SkillListApi.as_view(), name="skill-list"),
    path("workspaces/<uuid:workspace_id>/members/<uuid:member_id>/skills/", WorkspaceMemberSkillListCreateApi.as_view(), name="workspace-member-skill-list-create"),
    path("workspaces/<uuid:workspace_id>/members/<uuid:member_id>/skills/<uuid:skill_id>/", WorkspaceMemberSkillDeleteApi.as_view(), name="workspace-member-skill-delete"),

    path("workspaces/<uuid:workspace_id>/members/<uuid:member_id>/availability/", WorkspaceMemberAvailabilityApi.as_view(), name="workspace-member-availability"),
    path("workspaces/<uuid:workspace_id>/members/<uuid:member_id>/time-off/", WorkspaceMemberTimeOffListCreateApi.as_view(), name="workspace-member-time-off-list-create"),
    path("workspaces/<uuid:workspace_id>/members/<uuid:member_id>/time-off/<uuid:time_off_id>/", WorkspaceMemberTimeOffDeleteApi.as_view(), name="workspace-member-time-off-delete"),

    path("workspaces/<uuid:workspace_id>/capacity/", WorkspaceTeamCapacityApi.as_view(), name="workspace-team-capacity"),
    path("workspaces/<uuid:workspace_id>/members/<uuid:member_id>/capacity/", WorkspaceMemberCapacityApi.as_view(), name="workspace-member-capacity"),
]