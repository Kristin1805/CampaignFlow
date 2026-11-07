from rest_framework.exceptions import NotFound, PermissionDenied

from campaignflow.organization.models import WorkspaceMember
from campaignflow.organization.selectors import WorkspaceSelector


class TaskApprovalPermission:
    @staticmethod
    def get_membership(*, workspace_id, user):
        membership = WorkspaceSelector.get_membership(workspace_id=workspace_id, user=user)
        if membership is None:
            raise NotFound("Workspace not found.")
        return membership

    @staticmethod
    def require_submit(*, membership, task):
        if membership.role in (WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.MANAGER):
            return
        if membership.role == WorkspaceMember.Role.MEMBER and task.assignee_id == membership.id:
            return
        raise PermissionDenied("You cannot submit this task for approval.")

    @staticmethod
    def require_decision(*, membership, approval, user):
        if approval.task.assignee_id == membership.id:
            raise PermissionDenied("You cannot approve your own assigned task.")
        if membership.role == WorkspaceMember.Role.ADMIN:
            return
        if membership.role != WorkspaceMember.Role.GUEST and approval.reviewer_id == membership.id:
            return
        raise PermissionDenied("You are not authorized to review this task.")

    @staticmethod
    def require_cancel(*, membership, approval, user):
        if membership.role in (WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.MANAGER):
            return
        if membership.role == WorkspaceMember.Role.MEMBER and approval.requested_by_id == user.id:
            return
        raise PermissionDenied("You cannot cancel this approval.")
