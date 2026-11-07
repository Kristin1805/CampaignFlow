import hashlib

from attrs import asdict, define
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db.models import QuerySet, Prefetch

from .models import Workspace, WorkspaceMember, Skill, WorkspaceMemberSkill, WorkspaceInvitation, \
    WorkspaceMemberTimeOff, WorkspaceMemberAvailability

User = get_user_model()


class WorkspaceMemberSelector:

    @staticmethod
    def get_by_user_and_workspace(*, user: User, workspace: Workspace) -> WorkspaceMember | None:
        return WorkspaceMember.objects.filter(user=user, workspace=workspace).first()

    @staticmethod
    def get_by_id(*, workspace: Workspace, member_id: UUID) -> WorkspaceMember | None:
        return WorkspaceMember.objects.filter(id=member_id, workspace=workspace).select_related("workspace").first()

    @staticmethod
    def get_workspace_members(*, workspace: Workspace) -> QuerySet[WorkspaceMember]:
        return WorkspaceMember.objects.filter(workspace=workspace).select_related("user", "workspace").order_by("user__email")

    @staticmethod
    def get_user_workspaces(*, user: User) -> QuerySet[Workspace]:
        return Workspace.objects.filter(members__user=user).distinct().order_by("name")

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
    def get_user_workspaces(*, user: User) -> QuerySet[WorkspaceMember]:
        return WorkspaceMember.objects.filter(user=user).select_related("workspace").order_by("workspace__name")

    @staticmethod
    def get_membership(*, workspace_id: UUID, user: User) -> WorkspaceMember | None:
        return WorkspaceMember.objects.filter(workspace_id=workspace_id, user=user).select_related("workspace").first()

    @staticmethod
    def get_workspace_for_user(*, workspace_id: UUID, user: User) -> Workspace | None:
        return Workspace.objects.filter(id=workspace_id, members__user=user).first()

    @staticmethod
    def serialize_workspace(*, workspace: Workspace, role: str) -> WorkspaceResult:
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
    def get_workspace_invitations(*, workspace: Workspace) -> QuerySet[WorkspaceInvitation]:
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


class SkillSelector:
    @staticmethod
    def get_all_skills() -> QuerySet[Skill]:
        return Skill.objects.all().order_by("name")

    @staticmethod
    def get_by_code(*, code: str) -> Skill | None:
        return Skill.objects.filter(code=code).first()

    @staticmethod
    def get_member_skills(*, workspace_member: WorkspaceMember) -> QuerySet[WorkspaceMemberSkill]:
        return WorkspaceMemberSkill.objects.filter(workspace_member=workspace_member).select_related("skill").order_by("skill__name")

    @staticmethod
    def get_members_by_skill(*, workspace: Workspace, skill: Skill) -> QuerySet[WorkspaceMember]:
        return WorkspaceMember.objects.filter(workspace=workspace, member_skills__skill=skill).select_related("user").distinct()

    @staticmethod
    def get_members_by_skill_code(*, workspace: Workspace, skill_code: str) -> QuerySet[WorkspaceMember]:
        return WorkspaceMember.objects.filter(workspace=workspace, member_skills__skill__code=skill_code).select_related("user").distinct()

    @staticmethod
    def get_member_skill_data(member_skill: WorkspaceMemberSkill) -> dict:
        return {
            "id": str(member_skill.id),
            "workspace_member_id": str(member_skill.workspace_member_id),
            "skill_id": str(member_skill.skill_id),
            "skill_code": member_skill.skill.code,
            "skill_name": member_skill.skill.name,
            "created_at": member_skill.created_at,
        }


class WorkspaceMemberAvailabilitySelector:
    @staticmethod
    def get_by_member(*, workspace_member: WorkspaceMember) -> WorkspaceMemberAvailability | None:
        return WorkspaceMemberAvailability.objects.filter(workspace_member=workspace_member).first()

    @staticmethod
    def get_effective_availability(*, workspace_member: WorkspaceMember) -> dict:
        availability = WorkspaceMemberAvailabilitySelector.get_by_member(workspace_member=workspace_member)
        workspace = workspace_member.workspace

        return {
            "workspace_member_id": workspace_member.id,
            "working_days": availability.working_days if availability and availability.working_days is not None else workspace.working_days,
            "working_hours_per_day": availability.working_hours_per_day if availability and availability.working_hours_per_day is not None else workspace.working_hours_per_day,
            "custom_working_days": availability.working_days if availability else None,
            "custom_working_hours_per_day": availability.working_hours_per_day if availability else None,
        }


class WorkspaceMemberTimeOffSelector:
    @staticmethod
    def get_member_time_off(*, workspace_member: WorkspaceMember) -> QuerySet[WorkspaceMemberTimeOff]:
        return WorkspaceMemberTimeOff.objects.filter(workspace_member=workspace_member).order_by("start_date", "end_date")

    @staticmethod
    def get_by_id(*, workspace_member: WorkspaceMember, time_off_id: UUID) -> WorkspaceMemberTimeOff | None:
        return WorkspaceMemberTimeOff.objects.filter(id=time_off_id, workspace_member=workspace_member).first()

    @staticmethod
    def has_overlapping_period(*, workspace_member: WorkspaceMember, start_date, end_date) -> bool:
        return WorkspaceMemberTimeOff.objects.filter(
            workspace_member=workspace_member, start_date__lte=end_date, end_date__gte=start_date,
        ).exists()

    @staticmethod
    def get_time_off_data(time_off: WorkspaceMemberTimeOff) -> dict:
        return {
            "id": time_off.id,
            "workspace_member_id": time_off.workspace_member_id,
            "start_date": time_off.start_date,
            "end_date": time_off.end_date,
            "reason": time_off.reason,
            "created_at": time_off.created_at,
        }

    @staticmethod
    def get_member_time_off_for_period(*, workspace_member: WorkspaceMember, start_date, end_date) -> QuerySet[WorkspaceMemberTimeOff]:
        return WorkspaceMemberTimeOff.objects.filter(
            workspace_member=workspace_member, start_date__lte=end_date, end_date__gte=start_date,
        ).order_by("start_date")


class WorkspaceCapacitySelector:
    @staticmethod
    def get_workspace_members(*, workspace: Workspace, start_date, end_date) -> QuerySet[WorkspaceMember]:
        time_off_queryset = WorkspaceMemberTimeOff.objects.filter(start_date__lte=end_date, end_date__gte=start_date,).order_by("start_date", "end_date")

        return WorkspaceMember.objects.filter(workspace=workspace).select_related("user", "workspace", "availability",).prefetch_related(
            Prefetch("time_off_periods", queryset=time_off_queryset, to_attr="capacity_time_off"),).order_by("user__email")

    @staticmethod
    def get_member(*, workspace: Workspace, member_id: UUID, start_date, end_date) -> WorkspaceMember | None:
        return WorkspaceCapacitySelector.get_workspace_members(workspace=workspace, start_date=start_date, end_date=end_date,).filter(id=member_id).first()
