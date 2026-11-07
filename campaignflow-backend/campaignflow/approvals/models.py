import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class ApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    CHANGES_REQUESTED = "changes_requested", "Changes Requested"
    CANCELLED = "cancelled", "Cancelled"


class TaskApproval(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey("tasks.Task", on_delete=models.CASCADE, related_name="approvals")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requested_task_approvals")
    reviewer = models.ForeignKey("organization.WorkspaceMember", on_delete=models.PROTECT, related_name="assigned_task_approvals")
    status = models.CharField(max_length=30, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    submission_message = models.TextField(blank=True, default="")
    decision_comment = models.TextField(blank=True, default="")
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="decided_task_approvals")
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["task", "created_at"]),
            models.Index(fields=["reviewer", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["task"], condition=Q(status="pending"),
                name="unique_pending_approval_per_task",
            ),
        ]

    def __str__(self):
        return f"{self.task_id} - {self.status}"
