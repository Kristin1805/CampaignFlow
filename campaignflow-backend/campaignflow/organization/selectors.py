import hashlib

from attrs import asdict, define
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db.models import QuerySet

from .models import Workspace, WorkspaceMember, Skill, WorkspaceMemberSkill, WorkspaceInvitation

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
    def get_user_workspaces(*, user: User,) -> QuerySet[WorkspaceMember]:
        return (WorkspaceMember.objects.filter(user=user).select_related("workspace").order_by("workspace__name"))

    @staticmethod
    def get_membership(*, workspace_id: UUID, user: User,) -> WorkspaceMember | None:
        return (WorkspaceMember.objects.filter(workspace_id=workspace_id, user=user,).select_related("workspace").first())

    @staticmethod
    def serialize_workspace(*,workspace: Workspace, role: str,) -> WorkspaceResult:
        return WorkspaceResult(
            id=workspace.id,
            name=workspace.name,
            timezone=workspace.timezone,
            working_days=workspace.working_days,
            working_hours_per_day=workspace.working_hours_per_day,
            role=role,
        )


@define
class WorkspaceInvitationResult:
    id: UUID
    workspace_id: UUID
    email: str
    role: str
    status: str
    expires_at: object
    created_at: object

    def serialize(self):
        return asdict(self)


class WorkspaceInvitationSelector:
    @staticmethod
    def get_workspace_invitations(*, workspace: Workspace):
        return WorkspaceInvitation.objects.filter(workspace=workspace).select_related("invited_by").order_by("-created_at")

    @staticmethod
    def get_by_token(*, token: str) -> WorkspaceInvitation | None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return WorkspaceInvitation.objects.filter(token_hash=token_hash).select_related("workspace").first()

    @staticmethod
    def get_by_id(*, workspace: Workspace, invitation_id: UUID) -> WorkspaceInvitation | None:
        return WorkspaceInvitation.objects.filter(id=invitation_id, workspace=workspace).first()

    @staticmethod
    def serialize_invitation(*, invitation: WorkspaceInvitation) -> WorkspaceInvitationResult:
        return WorkspaceInvitationResult(
            id=invitation.id,
            workspace_id=invitation.workspace_id,
            email=invitation.email,
            role=invitation.role,
            status=invitation.status,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
        )
