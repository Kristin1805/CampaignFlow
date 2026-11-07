from rest_framework.exceptions import NotFound, PermissionDenied

from campaignflow.organization.models import WorkspaceMember
from campaignflow.organization.selectors import WorkspaceSelector


class TaskAttachmentPermission:
    @staticmethod
    def get_membership(*, workspace_id, user):
        membership = WorkspaceSelector.get_membership(workspace_id=workspace_id, user=user)
        if membership is None:
            raise NotFound("Workspace not found.")
        return membership

    @staticmethod
    def require_upload(*, membership):
        if membership.role not in (WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.MANAGER, WorkspaceMember.Role.MEMBER):
            raise PermissionDenied("You do not have permission to upload attachments.")

    @staticmethod
    def require_delete(*, membership, attachment, user):
        if membership.role in (WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.MANAGER):
            return
        if membership.role == WorkspaceMember.Role.MEMBER and attachment.uploaded_by_id == user.id:
            return
        raise PermissionDenied("You do not have permission to delete this attachment.")
