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

from rest_framework.exceptions import NotFound, PermissionDenied

from campaignflow.organization.models import WorkspaceMember
from campaignflow.organization.selectors import WorkspaceSelector


class DocumentTemplatePermission:
    MANAGEMENT_ROLES = {
        WorkspaceMember.Role.ADMIN,
        WorkspaceMember.Role.MANAGER,
    }

    @staticmethod
    def get_membership(*, workspace_id, user):
        if not user or not user.is_authenticated or not user.is_active:
            raise PermissionDenied("Authentication required.")

        membership = WorkspaceSelector.get_membership(
            workspace_id=workspace_id, user=user,
        )

        if membership is None:
            raise NotFound("Workspace not found.")

        return membership

    @classmethod
    def is_management(cls, *, membership):
        return membership.role in cls.MANAGEMENT_ROLES

    @staticmethod
    def require_view(*, membership):
        if membership.role == WorkspaceMember.Role.GUEST:
            raise PermissionDenied("You cannot view document templates.")

    @classmethod
    def require_management(cls, *, membership):
        if not cls.is_management(membership=membership):
            raise PermissionDenied("You cannot manage document templates.")

    @classmethod
    def require_edit(cls, *, membership, template, allow_archived=False):
        cls.require_management(membership=membership)

        if template.is_system:
            raise PermissionDenied("System templates cannot be modified. Duplicate the template instead.")

        if template.is_archived and not allow_archived:
            raise PermissionDenied("Archived templates cannot be modified.")

    @classmethod
    def get_actions(cls, *, membership, template):
        is_management = cls.is_management(membership=membership)
        can_edit = is_management and not template.is_system and not template.is_archived

        return {
            "can_view": membership.role != WorkspaceMember.Role.GUEST,
            "can_edit": can_edit,
            "can_publish": can_edit,
            "can_duplicate": is_management and not template.is_archived,
            "can_archive": can_edit,
            "can_restore": is_management and not template.is_system and template.is_archived,
            "can_view_draft": is_management,
            "can_restore_version": can_edit,
        }