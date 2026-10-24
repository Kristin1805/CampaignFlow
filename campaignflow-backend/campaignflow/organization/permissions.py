
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
