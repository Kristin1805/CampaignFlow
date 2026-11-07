import hashlib
from datetime import timedelta
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError, ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework.exceptions import (PermissionDenied, ValidationError as DRFValidationError, NotFound, )

from .models import Workspace, WorkspaceMember, Skill, WorkspaceMemberSkill, WorkspaceInvitation
from .permissions import WorkspacePermission
from .tasks import send_workspace_invitation_email

def validate_workspace_model(workspace: Workspace) -> None:
    try:
        workspace.full_clean()
    except DjangoValidationError as exc:
        if hasattr(exc, "message_dict"):
            raise DRFValidationError(exc.message_dict) from exc

        raise DRFValidationError(exc.messages) from exc


class WorkspaceMemberService:

    def __init__(self, *, workspace: Workspace, acting_user):
        self.workspace = workspace
        self.acting_user = acting_user

    def authorize_admin(self) -> WorkspaceMember:
        return WorkspacePermission.require_admin(user=self.acting_user, workspace=self.workspace)

    @staticmethod
    def validate_role(role: str) -> None:
        if role not in WorkspaceMember.Role.values:
            raise DRFValidationError({"role": "Invalid workspace role."})

    @transaction.atomic
    def create_member(self, *, user, role: str) -> WorkspaceMember:
        self.authorize_admin()
        self.validate_role(role)

        member = WorkspaceMember(workspace=self.workspace, user=user, role=role)
        member.full_clean()
        member.save()

        return member

    @transaction.atomic
    def update_role(self, *, member: WorkspaceMember, role: str) -> WorkspaceMember:
        Workspace.objects.select_for_update().get(pk=self.workspace.pk)

        self.authorize_admin()
        self.validate_role(role)

        member = WorkspaceMember.objects.select_for_update().get(pk=member.pk, workspace=self.workspace)

        if member.role == WorkspaceMember.Role.ADMIN and role != WorkspaceMember.Role.ADMIN:
            self._ensure_another_admin(member=member)

        member.role = role
        member.full_clean()
        member.save(update_fields=["role"])

        return member

    @transaction.atomic
    def delete_member(self, *, member: WorkspaceMember) -> None:
        Workspace.objects.select_for_update().get(pk=self.workspace.pk)

        self.authorize_admin()

        member = WorkspaceMember.objects.select_for_update().get(pk=member.pk, workspace=self.workspace)

        if member.role == WorkspaceMember.Role.ADMIN:
            self._ensure_another_admin(member=member)

        member.delete()

    def _ensure_another_admin(self, *, member: WorkspaceMember) -> None:
        has_another_admin = WorkspaceMember.objects.filter(
            workspace=self.workspace, role=WorkspaceMember.Role.ADMIN,
        ).exclude(pk=member.pk).exists()

        if not has_another_admin:
            raise PermissionDenied("The last workspace admin cannot be removed.")


@transaction.atomic
def workspace_create(*, created_by, name: str, **extra_fields) -> Workspace:
    workspace = Workspace(name=name, created_by=created_by, **extra_fields)
    validate_workspace_model(workspace)
    workspace.save()

    member = WorkspaceMember(workspace=workspace, user=created_by, role=WorkspaceMember.Role.ADMIN)
    member.full_clean()
    member.save()

    return workspace


class WorkspaceMemberSkillService:
    def __init__(self, *, workspace: Workspace, acting_user):
        self.workspace = workspace
        self.acting_user = acting_user

    @transaction.atomic
    def assign_skill(self, *, workspace_member: WorkspaceMember, skill: Skill) -> WorkspaceMemberSkill:
        WorkspacePermission.require_admin(user=self.acting_user, workspace=self.workspace)

        if workspace_member.workspace_id != self.workspace.id:
            raise DRFValidationError({"workspace_member": "Member does not belong to this workspace."})

        member_skill = WorkspaceMemberSkill(workspace_member=workspace_member, skill=skill)
        member_skill.full_clean()
        member_skill.save()

        return member_skill

    @transaction.atomic
    def remove_skill(self, *, workspace_member: WorkspaceMember, skill: Skill) -> None:
        WorkspacePermission.require_admin(user=self.acting_user, workspace=self.workspace)

        if workspace_member.workspace_id != self.workspace.id:
            raise DRFValidationError({"workspace_member": "Member does not belong to this workspace."})

        WorkspaceMemberSkill.objects.filter(workspace_member=workspace_member, skill=skill).delete()


class WorkspaceService:

    @staticmethod
    def create(
        *,
        user,
        name: str,
        timezone: str = "Europe/Sofia",
        working_days: list[int] | None = None,
        working_hours_per_day: int = 8,
    ) -> Workspace:
        return workspace_create(
            created_by=user,
            name=name,
            timezone=timezone,
            working_days=working_days if working_days is not None else [0, 1, 2, 3, 4],
            working_hours_per_day=working_hours_per_day,
        )

    @staticmethod
    @transaction.atomic
    def update(*, workspace: Workspace, acting_member: WorkspaceMember, data: dict) -> Workspace:
        if acting_member.workspace_id != workspace.id:
            raise PermissionDenied("Workspace access denied.")

        WorkspacePermission.require_admin(user=acting_member.user, workspace=workspace)

        allowed_fields = {"name", "timezone", "working_days", "working_hours_per_day"}
        update_fields = []

        for field, value in data.items():
            if field not in allowed_fields:
                continue

            setattr(workspace, field, value)
            update_fields.append(field)

        if update_fields:
            validate_workspace_model(workspace)
            workspace.save(update_fields=[*update_fields, "updated_at"])

        return workspace



class WorkspaceInvitationService:
    def __init__(self, *, workspace: Workspace, acting_user):
        self.workspace = workspace
        self.acting_user = acting_user

    @transaction.atomic
    def create_invitation(self, *, email: str, role: str = WorkspaceMember.Role.MEMBER) -> tuple[WorkspaceInvitation, str]:
        WorkspacePermission.require_admin(user=self.acting_user, workspace=self.workspace)

        email = email.strip().lower()

        if role not in WorkspaceMember.Role.values:
            raise DRFValidationError({"role": "Invalid workspace role."})

        if WorkspaceMember.objects.filter(workspace=self.workspace, user__email__iexact=email).exists():
            raise DRFValidationError({"email": "User is already a workspace member."})

        now = timezone.now()

        WorkspaceInvitation.objects.filter(
            workspace=self.workspace, email=email, status=WorkspaceInvitation.Status.PENDING, expires_at__lte=now,
        ).update(status=WorkspaceInvitation.Status.REVOKED, revoked_at=now)

        if WorkspaceInvitation.objects.filter(workspace=self.workspace, email=email, status=WorkspaceInvitation.Status.PENDING).exists():
            raise DRFValidationError({"email": "An active invitation already exists."})

        token, token_hash = WorkspaceInvitation.generate_token()

        invitation = WorkspaceInvitation(
            workspace=self.workspace, email=email, role=role, token_hash=token_hash,
            invited_by=self.acting_user, expires_at=now + timedelta(days=7),
        )

        try:
            with transaction.atomic():
                invitation.full_clean()
                invitation.save()
        except (DjangoValidationError, IntegrityError) as exc:
            raise DRFValidationError({"email": "Unable to create invitation. Check for an existing pending invitation."}) from exc

        transaction.on_commit(
            lambda: send_workspace_invitation_email.delay(
                email=invitation.email, workspace_name=self.workspace.name, token=token,
            )
        )

        return invitation, token

    @staticmethod
    @transaction.atomic
    def accept_invitation(*, token: str, user) -> WorkspaceMember:
        if not user or not user.is_authenticated:
            raise PermissionDenied("Authentication required.")

        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        invitation = WorkspaceInvitation.objects.select_for_update().select_related("workspace").filter(token_hash=token_hash).first()

        if invitation is None:
            raise NotFound("Invitation not found.")

        if invitation.status != WorkspaceInvitation.Status.PENDING:
            raise DRFValidationError({"invitation": "Invitation is no longer active."})

        if invitation.expires_at <= timezone.now():
            raise DRFValidationError({"invitation": "Invitation has expired."})

        if user.email.strip().lower() != invitation.email.strip().lower():
            raise PermissionDenied("This invitation belongs to another email address.")

        if WorkspaceMember.objects.filter(workspace=invitation.workspace, user=user).exists():
            raise DRFValidationError({"invitation": "You are already a workspace member."})

        member = WorkspaceMember(workspace=invitation.workspace, user=user, role=invitation.role)

        try:
            with transaction.atomic():
                member.full_clean()
                member.save()
        except (DjangoValidationError, IntegrityError) as exc:
            raise DRFValidationError({"invitation": "Unable to accept invitation or membership already exists."}) from exc

        invitation.status = WorkspaceInvitation.Status.ACCEPTED
        invitation.accepted_by = user
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["status", "accepted_by", "accepted_at"])

        return member

    @transaction.atomic
    def revoke_invitation(self, *, invitation_id: UUID) -> None:
        WorkspacePermission.require_admin(user=self.acting_user, workspace=self.workspace)

        invitation = WorkspaceInvitation.objects.select_for_update().filter(id=invitation_id, workspace=self.workspace).first()

        if invitation is None:
            raise NotFound("Invitation not found.")

        if invitation.status != WorkspaceInvitation.Status.PENDING:
            raise DRFValidationError({"invitation": "Only pending invitations can be revoked."})

        invitation.status = WorkspaceInvitation.Status.REVOKED
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["status", "revoked_at"])

