from rest_framework.exceptions import NotFound, PermissionDenied

from campaignflow.content.constants import EDITABLE_CONTENT_STATUSES, MEMBER_CONTENT_TRANSITIONS, \
    CALENDAR_RESCHEDULABLE_STATUSES
from campaignflow.organization.models import WorkspaceMember
from campaignflow.organization.selectors import WorkspaceSelector


class ContentPermission:
    MANAGEMENT_ROLES = {
        WorkspaceMember.Role.ADMIN,
        WorkspaceMember.Role.MANAGER,
    }

    @staticmethod
    def get_membership(*, workspace_id, user):
        if not user or not user.is_authenticated or not user.is_active:
            raise PermissionDenied("Authentication required.")

        membership = WorkspaceSelector.get_membership(workspace_id=workspace_id, user=user)

        if membership is None:
            raise NotFound("Workspace not found.")

        return membership

    @classmethod
    def is_management(cls, *, membership):
        return membership.role in cls.MANAGEMENT_ROLES

    @classmethod
    def require_management(cls, *, membership):
        if not cls.is_management(membership=membership):
            raise PermissionDenied("You cannot manage workspace content.")

    @staticmethod
    def require_view(cls=None, *, membership):
        if membership.role == WorkspaceMember.Role.GUEST:
            raise PermissionDenied("You cannot view workspace content.")

    @classmethod
    def require_edit(cls, *, membership, content_item):
        if cls.is_management(membership=membership):
            return

        if membership.role != WorkspaceMember.Role.MEMBER:
            raise PermissionDenied("You cannot edit this content.")

        if content_item.assignee_id != membership.id:
            raise PermissionDenied("This content is not assigned to you.")

        if content_item.status not in EDITABLE_CONTENT_STATUSES:
            raise PermissionDenied("Content cannot be edited in its current status.")

    @classmethod
    def require_status_change(cls, *, membership, content_item, new_status):
        if cls.is_management(membership=membership):
            return

        cls.require_edit(membership=membership, content_item=content_item)

        if new_status not in MEMBER_CONTENT_TRANSITIONS:
            raise PermissionDenied("You cannot perform this status transition.")


    @classmethod
    def can_reschedule(cls, *, membership, content_item):
        return (
            cls.is_management(membership=membership)
            and not content_item.is_archived
            and not content_item.campaign.is_archived
            and content_item.status in CALENDAR_RESCHEDULABLE_STATUSES
        )

    @classmethod
    def require_reschedule(cls, *, membership, content_item):
        cls.require_management(membership=membership)

        if not cls.can_reschedule(membership=membership, content_item=content_item):
            raise PermissionDenied("Content cannot be rescheduled in its current state.")

    @classmethod
    def get_calendar_actions(cls, *, membership, content_item):
        can_edit = (
            not content_item.is_archived
            and not content_item.campaign.is_archived
            and content_item.status in EDITABLE_CONTENT_STATUSES
            and (
                cls.is_management(membership=membership)
                or (membership.role == WorkspaceMember.Role.MEMBER and content_item.assignee_id == membership.id)
            )
        )

        can_reschedule = cls.can_reschedule(membership=membership, content_item=content_item,)

        return {
            "can_view": membership.role != WorkspaceMember.Role.GUEST,
            "can_edit": can_edit,
            "can_reschedule": can_reschedule,
            "can_unschedule": can_reschedule and content_item.publication_at is not None,
            "can_archive": (
                cls.is_management(membership=membership)
                and not content_item.is_archived
                and not content_item.campaign.is_archived
            ),
        }
