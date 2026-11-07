
from rest_framework.exceptions import PermissionDenied

from .models import Workspace, WorkspaceMember
from .selectors import WorkspaceMemberSelector


class WorkspacePermission:

    @staticmethod
    def get_member_or_raise(*, user, workspace: Workspace,) -> WorkspaceMember:
        if not user or not user.is_authenticated:
            raise PermissionDenied("Workspace access denied.")

        member = WorkspaceMemberSelector.get_by_user_and_workspace(user=user, workspace=workspace,)

        if member is None:
            raise PermissionDenied("Workspace access denied.")

        return member

    @classmethod
    def require_roles(cls,*, user, workspace: Workspace, allowed_roles,) -> WorkspaceMember:
        member = cls.get_member_or_raise(user=user,workspace=workspace,)

        if member.role not in allowed_roles:
            raise PermissionDenied("You do not have permission to perform this action.")

        return member

    @classmethod
    def require_admin(cls, *, user, workspace: Workspace,) -> WorkspaceMember:
        return cls.require_roles(user=user, workspace=workspace, allowed_roles=[WorkspaceMember.Role.ADMIN],)

    @classmethod
    def require_manager(cls, *, user, workspace: Workspace,) -> WorkspaceMember:
        return cls.require_roles(user=user, workspace=workspace, allowed_roles=[WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.MANAGER,],)



class WorkspaceAvailabilityPermission:
    @staticmethod
    def require_view(*, user, workspace: Workspace) -> WorkspaceMember:
        return WorkspacePermission.get_member_or_raise(user=user, workspace=workspace)

    @staticmethod
    def require_manage(*, user, workspace: Workspace, target_member: WorkspaceMember) -> WorkspaceMember:
        acting_member = WorkspacePermission.get_member_or_raise(user=user, workspace=workspace)

        if target_member.workspace_id != workspace.id:
            raise PermissionDenied("Member does not belong to this workspace.")

        if acting_member.role in [WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.MANAGER]:
            return acting_member

        if acting_member.role == WorkspaceMember.Role.MEMBER and acting_member.id == target_member.id:
            return acting_member

        raise PermissionDenied("You do not have permission to manage this availability.")
