from attrs import asdict, define
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db.models import QuerySet

from .models import Workspace, WorkspaceMember, Skill, WorkspaceMemberSkill

User = get_user_model()



class SkillSelector:

    @staticmethod
    def get_all_skills():
        return Skill.objects.all().order_by("name")

    @staticmethod
    def get_by_code(*, code: str) -> Skill | None:
        return Skill.objects.filter(code=code).first()

    @staticmethod
    def get_member_skills(*, workspace_member: WorkspaceMember):
        return (Skill.objects.filter(member_skills__workspace_member=workspace_member).order_by("name"))

    @staticmethod
    def get_members_by_skill(*, workspace, skill: Skill):
        return (
            WorkspaceMember.objects
            .filter(workspace=workspace, member_skills__skill=skill,)
            .select_related("user", "workspace")
            .distinct()
            .order_by("user__email")
        )

    @staticmethod
    def get_members_by_skill_code(*, workspace, skill_code: str):
        return (
            WorkspaceMember.objects
            .filter(workspace=workspace, member_skills__skill__code=skill_code,)
            .select_related("user", "workspace")
            .distinct()
            .order_by("user__email")
        )

    @staticmethod
    def get_member_skill_data(member_skill: WorkspaceMemberSkill) -> dict:
        return {
            "id": str(member_skill.id),
            "workspace_member_id": str(member_skill.workspace_member_id),
            "skill_id": str(member_skill.skill_id),
            "skill_code": member_skill.skill.code,
            "skill_name": member_skill.skill.name,
        }


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



@define
class WorkspaceResult:
    id: UUID
    name: str
    timezone: str
    working_days: list[int]
    working_hours_per_day: int
    role: str

    def serialize(self):
        return asdict(self)


class WorkspaceSelector:
    @staticmethod
    def get_user_workspaces(user) -> QuerySet[WorkspaceMember]:
        return (WorkspaceMember.objects.filter(user=user).select_related("workspace").order_by("workspace__name"))

    @staticmethod
    def get_workspace_for_user(workspace_id: UUID, user,) -> Workspace | None:
        return (Workspace.objects.filter(id=workspace_id, members__user=user).distinct().first())

    @staticmethod
    def serialize_workspace(workspace: Workspace, role: str,) -> WorkspaceResult:
        return WorkspaceResult(
            id=workspace.id,
            name=workspace.name,
            timezone=workspace.timezone,
            working_days=workspace.working_days,
            working_hours_per_day=workspace.working_hours_per_day,
            role=role,
        )

