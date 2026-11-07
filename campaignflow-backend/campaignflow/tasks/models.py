import uuid

from django.conf import settings
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
    required_skill = models.ForeignKey(
        "organization.Skill",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=TaskStatus.choices, default=TaskStatus.BACKLOG)
    priority = models.CharField(max_length=20, choices=TaskPriority.choices, default=TaskPriority.MEDIUM)
    estimated_hours = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    actual_hours = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    planned_start = models.DateTimeField(null=True, blank=True)
    planned_end = models.DateTimeField(null=True, blank=True)
    latest_start_at = models.DateTimeField(null=True, blank=True)
    is_critical = models.BooleanField(default=False)
    slack_hours = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["campaign", "status"]),
            models.Index(fields=["assignee", "status"]),
            models.Index(fields=["required_skill", "status"]),
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


class TaskDependency(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey("tasks.Task", on_delete=models.CASCADE, related_name="dependencies")
    depends_on_task = models.ForeignKey("tasks.Task", on_delete=models.CASCADE, related_name="dependents")
    lag_hours = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["task", "depends_on_task"], name="unique_task_dependency"),
            models.CheckConstraint(
                condition=~models.Q(task_id=models.F("depends_on_task_id")),
                name="prevent_task_self_dependency",
            ),
        ]

    def clean(self):
        super().clean()
        if self.task_id == self.depends_on_task_id:
            raise ValidationError({"depends_on_task": "A task cannot depend on itself."})
        if self.task_id and self.depends_on_task_id:
            if self.task.campaign_id != self.depends_on_task.campaign_id:
                raise ValidationError({"depends_on_task": "Both tasks must belong to the same campaign."})

    def __str__(self):
        return f"{self.task_id} depends on {self.depends_on_task_id}"


class TaskStatusHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey("tasks.Task", on_delete=models.CASCADE, related_name="status_history")
    previous_status = models.CharField(max_length=30, choices=TaskStatus.choices)
    new_status = models.CharField(max_length=30, choices=TaskStatus.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="task_status_changes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["task", "created_at"])]

    def __str__(self):
        return f"{self.task_id}: {self.previous_status} -> {self.new_status}"


class TaskActivityType(models.TextChoices):
    CREATED = "task_created", "Task Created"
    UPDATED = "task_updated", "Task Updated"
    ASSIGNED = "task_assigned", "Task Assigned"
    STATUS_CHANGED = "status_changed", "Status Changed"

    DEPENDENCY_ADDED = "dependency_added", "Dependency Added"
    DEPENDENCY_REMOVED = "dependency_removed", "Dependency Removed"

    COMMENT_ADDED = "comment_added", "Comment Added"
    COMMENT_UPDATED = "comment_updated", "Comment Updated"
    COMMENT_DELETED = "comment_deleted", "Comment Deleted"

    ATTACHMENT_UPLOADED = "attachment_uploaded", "Attachment Uploaded"
    ATTACHMENT_DELETED = "attachment_deleted", "Attachment Deleted"

    APPROVAL_REQUESTED = "approval_requested", "Approval Requested"
    APPROVAL_APPROVED = "approval_approved", "Approval Approved"
    APPROVAL_CHANGES_REQUESTED = "approval_changes_requested", "Approval Changes Requested"
    APPROVAL_CANCELLED = "approval_cancelled", "Approval Cancelled"

class TaskComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey("tasks.Task", on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="task_comments")
    content = models.TextField(max_length=5000)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["task", "created_at"])]

    def __str__(self):
        return f"Comment {self.id} on task {self.task_id}"


class TaskActivity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey("tasks.Task", on_delete=models.CASCADE, related_name="activities")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="task_activities")
    action = models.CharField(max_length=40, choices=TaskActivityType.choices)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["task", "created_at"])]

    def __str__(self):
        return f"{self.action} on task {self.task_id}"

