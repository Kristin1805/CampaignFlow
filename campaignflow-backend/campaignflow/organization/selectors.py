from django.contrib.auth import get_user_model

from .models import Workspace, WorkspaceMember

User = get_user_model()


class WorkspaceMemberSelector:

    @staticmethod
    def get_by_user_and_workspace(
        *,
        user: User,
        workspace: Workspace,
    ) -> WorkspaceMember | None:
        return (
            WorkspaceMember.objects
            .filter(user=user, workspace=workspace)
            .first()
        )

    @staticmethod
    def get_workspace_members(
        *,
        workspace: Workspace,
    ):
        return (
            WorkspaceMember.objects
            .filter(workspace=workspace)
            .select_related("user", "workspace")
            .order_by("user__email")
        )

    @staticmethod
    def get_user_workspaces(*, user: User):
        return (
            Workspace.objects
            .filter(members__user=user)
            .distinct()
            .order_by("name")
        )

    @staticmethod
    def get_member_data(member: WorkspaceMember) -> dict:
        return {
            "id": str(member.id),
            "workspace_id": str(member.workspace_id),
            "user_id": str(member.user_id),
            "role": member.role,
            "created_at": member.created_at,
        }
