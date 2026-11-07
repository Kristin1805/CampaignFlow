import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Campaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PLANNING = "planning", "Planning"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "organization.Workspace",
        on_delete=models.CASCADE,
        related_name="campaigns",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    goal = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    launch_at = models.DateTimeField(null=True, blank=True,)

    budget_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_campaigns",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "status"]),
            models.Index(fields=["workspace", "created_at"]),
            models.Index(fields=["workspace", "launch_at"], name="campaign_ws_launch_idx",),
        ]

    def clean(self):
        super().clean()

        errors = {}

        if (self.starts_on and self.ends_on and self.starts_on > self.ends_on):
            errors["ends_on"] = ("End date must be on or after start date.")

        if self.launch_at is not None:
            launch_date = (timezone.localtime(self.launch_at).date() if timezone.is_aware(self.launch_at) else self.launch_at.date())

            if self.starts_on and launch_date < self.starts_on:
                errors["launch_at"] = ("Launch date cannot be before campaign start date.")

            if self.ends_on and launch_date > self.ends_on:
                errors["launch_at"] = ("Launch date cannot be after campaign end date.")

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name
