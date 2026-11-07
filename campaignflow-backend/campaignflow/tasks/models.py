import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from campaignflow.tasks.enums import TaskPriority, TaskStatus


class Task(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey("campaigns.Campaign", on_delete=models.CASCADE, related_name="tasks")
    assignee = models.ForeignKey(
        "organization.WorkspaceMember",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=TaskStatus.choices, default=TaskStatus.BACKLOG)
    priority = models.CharField(max_length=20, choices=TaskPriority.choices, default=TaskPriority.MEDIUM)
    estimated_hours = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    actual_hours = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    planned_start = models.DateField(null=True, blank=True)
    planned_end = models.DateField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["campaign", "status"]),
            models.Index(fields=["assignee", "status"]),
            models.Index(fields=["planned_start", "planned_end"]),
        ]

    def clean(self):
        super().clean()

        if self.planned_start and self.planned_end and self.planned_start > self.planned_end:
            raise ValidationError({"planned_end": "End date must be on or after start date."})

        if self.assignee_id and self.campaign_id:
            if self.assignee.workspace_id != self.campaign.workspace_id:
                raise ValidationError({"assignee": "Assignee must belong to the campaign workspace."})

    def __str__(self):
        return self.title
