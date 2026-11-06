
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from .models import Workspace, WorkspaceMember, Skill, WorkspaceMemberSkill
from .permissions import WorkspacePermission


class WorkspaceMemberService:

    def __init__(self, *, workspace: Workspace, acting_user):
        self.workspace = workspace
        self.acting_user = acting_user

    def authorize_admin(self):
        return WorkspacePermission.require_admin(user=self.acting_user,workspace=self.workspace,)

    @staticmethod
    def validate_role(role: str):
        if role not in WorkspaceMember.Role.values:
            raise ValidationError({
                "role": "Invalid workspace role."
            })

    @transaction.atomic
    def create_member(self, *, user, role: str):
        self.authorize_admin()
        self.validate_role(role)

        member = WorkspaceMember(workspace=self.workspace, user=user, role=role,)

        member.full_clean()
        member.save()

        return member

    @transaction.atomic
    def update_role(self, *, member: WorkspaceMember, role: str,) -> WorkspaceMember:
        self.authorize_admin()
        self.validate_role(role)

        member = (WorkspaceMember.objects.select_for_update().get(pk=member.pk, workspace=self.workspace,))

        if (member.role == WorkspaceMember.Role.ADMIN and role != WorkspaceMember.Role.ADMIN):
            self._ensure_another_admin(member=member)

        member.role = role
        member.full_clean()
        member.save(update_fields=["role"])

        return member

    @transaction.atomic
    def delete_member(self, *, member: WorkspaceMember):
        self.authorize_admin()

        member = (WorkspaceMember.objects.select_for_update().get(pk=member.pk, workspace=self.workspace,))

        if member.role == WorkspaceMember.Role.ADMIN:
            self._ensure_another_admin(member=member)

        member.delete()

    def _ensure_another_admin(self, *, member: WorkspaceMember):
        has_another_admin = (WorkspaceMember.objects
            .filter(workspace=self.workspace, role=WorkspaceMember.Role.ADMIN,)
            .exclude(pk=member.pk)
            .exists()
        )

        if not has_another_admin:
            raise PermissionDenied("The last workspace admin cannot be removed.")


@transaction.atomic
def workspace_create(*, created_by, name: str, **extra_fields):
    workspace = Workspace(name=name, created_by=created_by, **extra_fields,)

    workspace.full_clean()
    workspace.save()

    member = WorkspaceMember(workspace=workspace, user=created_by, role=WorkspaceMember.Role.ADMIN,)

    member.full_clean()
    member.save()

    return workspace


class WorkspaceMemberSkillService:

    def __init__(self, *, workspace, acting_user):
        self.workspace = workspace
        self.acting_user = acting_user

    @transaction.atomic
    def assign_skill(self, *, workspace_member: WorkspaceMember, skill: Skill,) -> WorkspaceMemberSkill:
        WorkspacePermission.require_admin(user=self.acting_user, workspace=self.workspace,)

        if workspace_member.workspace_id != self.workspace.id:
            raise ValidationError({
                "workspace_member": "Member does not belong to this workspace."
            })

        member_skill = WorkspaceMemberSkill(workspace_member=workspace_member, skill=skill,)

        member_skill.full_clean()
        member_skill.save()

        return member_skill

    @transaction.atomic
    def remove_skill(self, *, workspace_member: WorkspaceMember, skill: Skill,) -> None:
        WorkspacePermission.require_admin(user=self.acting_user, workspace=self.workspace,)

        if workspace_member.workspace_id != self.workspace.id:
            raise ValidationError({
                "workspace_member": "Member does not belong to this workspace."
            })

        WorkspaceMemberSkill.objects.filter(workspace_member=workspace_member, skill=skill,).delete()


class WorkspaceService:
    @staticmethod
    @transaction.atomic
    def create(*, user, name: str, timezone: str = "Europe/Sofia", working_days: list[int] | None = None, working_hours_per_day: int = 8,) -> Workspace:
        workspace = Workspace(
            name=name,
            created_by=user,
            timezone=timezone,
            working_days=(
                working_days
                if working_days is not None
                else [0, 1, 2, 3, 4]
            ),
            working_hours_per_day=working_hours_per_day,
        )

        workspace.full_clean()
        workspace.save()

        WorkspaceMember.objects.create(workspace=workspace, user=user, role=WorkspaceMember.Role.ADMIN,)

        return workspace

    @staticmethod
    @transaction.atomic
    def update(*, workspace: Workspace, acting_member: WorkspaceMember, data: dict,) -> Workspace:
        if acting_member.workspace_id != workspace.id:
            raise PermissionDenied("Member does not belong to workspace.")

        if acting_member.role != WorkspaceMember.Role.ADMIN:
            raise PermissionDenied("Only workspace admins can update settings.")

        allowed_fields = {
            "name",
            "timezone",
            "working_days",
            "working_hours_per_day",
        }

        update_fields = []

        for field, value in data.items():
            if field not in allowed_fields:
                continue

            setattr(workspace, field, value)
            update_fields.append(field)

        if update_fields:
            workspace.full_clean()
            workspace.save(update_fields=[*update_fields, "updated_at"])

        return workspace