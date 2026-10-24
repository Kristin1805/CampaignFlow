
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from .models import Workspace, WorkspaceMember
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
