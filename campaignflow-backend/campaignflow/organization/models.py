import uuid

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

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
