import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from campaignflow.organization.validators import validate_timezone, validate_working_days

def default_working_days():
    return [0, 1, 2, 3, 4]

class WorkspaceMember(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MANAGER = "manager", "Manager"
        MEMBER = "member", "Member"
        GUEST = "guest", "Guest"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    workspace = models.ForeignKey("organization.Workspace",on_delete=models.CASCADE,related_name="members",)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workspace_memberships",)

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER, )

    created_at = models.DateTimeField(auto_now_add=True,)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "user"],
                name="unique_workspace_user_membership",
            ),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.workspace.name} ({self.role})"


class Workspace(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(max_length=150,)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_workspaces",
    )

    timezone = models.CharField(
        max_length=64,
        default="Europe/Sofia",
        validators=[validate_timezone],
    )

    working_days = models.JSONField(
        default=default_working_days,
        validators=[validate_working_days],
    )

    working_hours_per_day = models.PositiveSmallIntegerField(
        default=8,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(24),
        ],
    )

    created_at = models.DateTimeField(auto_now_add=True,)

    updated_at = models.DateTimeField(auto_now=True, )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name



class Skill(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,)

    code = models.SlugField(max_length=100, unique=True,)

    name = models.CharField(max_length=150,)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class WorkspaceMemberSkill(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,)

    workspace_member = models.ForeignKey("organization.WorkspaceMember", on_delete=models.CASCADE, related_name="member_skills",)

    skill = models.ForeignKey("organization.Skill", on_delete=models.PROTECT, related_name="member_skills",)

    created_at = models.DateTimeField(auto_now_add=True,)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["workspace_member", "skill"],
                name="unique_workspace_member_skill",
            ),
        ]

    def __str__(self):
        return f"{self.workspace_member.user.email} - {self.skill.name}"



def default_invitation_expiration():
    return timezone.now() + timedelta(days=7)


class WorkspaceInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REVOKED = "revoked", "Revoked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("organization.Workspace", on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField(max_length=254)
    role = models.CharField(max_length=20, choices=WorkspaceMember.Role.choices, default=WorkspaceMember.Role.MEMBER)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sent_workspace_invitations")
    accepted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="accepted_workspace_invitations")
    expires_at = models.DateTimeField(default=default_invitation_expiration)
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "email"], condition=models.Q(status="pending"), name="unique_pending_workspace_invitation"),
        ]
        indexes = [
            models.Index(fields=["workspace", "status"]),
            models.Index(fields=["email", "status"]),
        ]

    @staticmethod
    def generate_token():
        token = secrets.token_urlsafe(32)
        return token, hashlib.sha256(token.encode("utf-8")).hexdigest()

    def __str__(self):
        return f"{self.email} - {self.workspace.name} ({self.status})"



class WorkspaceMemberAvailability(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_member = models.OneToOneField("organization.WorkspaceMember", on_delete=models.CASCADE, related_name="availability")
    working_days = models.JSONField(null=True, blank=True, default=None, validators=[validate_working_days])
    working_hours_per_day = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(24)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Availability for {self.workspace_member_id}"


class WorkspaceMemberTimeOff(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_member = models.ForeignKey("organization.WorkspaceMember", on_delete=models.CASCADE, related_name="time_off_periods")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_date", "end_date"]
        constraints = [
            models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="workspace_time_off_valid_date_range"),
        ]

    def clean(self):
        super().clean()

        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({"end_date": "End date must be on or after start date."})

    def __str__(self):
        return f"{self.workspace_member_id}: {self.start_date} - {self.end_date}"
