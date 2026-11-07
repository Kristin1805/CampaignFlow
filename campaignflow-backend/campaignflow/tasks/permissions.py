from rest_framework.exceptions import NotFound, PermissionDenied

from campaignflow.organization.models import WorkspaceMember
from campaignflow.organization.selectors import WorkspaceSelector


class TaskDependencyPermission:
    @staticmethod
    def get_membership(*, workspace_id, user):
        membership = WorkspaceSelector.get_membership(workspace_id=workspace_id, user=user)
        if membership is None:
            raise NotFound("Workspace not found.")
        return membership

    @staticmethod
    def require_management(*, membership):
        if membership.role not in (WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.MANAGER):
            raise PermissionDenied("You do not have permission to manage task dependencies.")
