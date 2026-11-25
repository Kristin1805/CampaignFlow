import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from campaignflow.content.constants import PUBLICATION_DATE_REQUIRED_STATUSES
from campaignflow.content.enums import ContentStatus


class ContentPlatform(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("organization.Workspace", on_delete=models.CASCADE, related_name="content_platforms")
    code = models.SlugField(max_length=100)
    name = models.CharField(max_length=150)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "code"], name="unique_workspace_content_platform"),
        ]

    def __str__(self):
        return self.name


class ContentFormat(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("organization.Workspace", on_delete=models.CASCADE, related_name="content_formats")
    code = models.SlugField(max_length=100)
    name = models.CharField(max_length=150)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "code"], name="unique_workspace_content_format"),
        ]

    def __str__(self):
        return self.name


class ContentItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey("campaigns.Campaign", on_delete=models.CASCADE, related_name="content_items")
    platform = models.ForeignKey(ContentPlatform, on_delete=models.PROTECT, related_name="content_items")
    content_format = models.ForeignKey(ContentFormat, on_delete=models.PROTECT, related_name="content_items")

    assignee = models.ForeignKey(
        "organization.WorkspaceMember", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="assigned_content_items",
    )
    related_task = models.ForeignKey(
        "tasks.Task", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="content_items",
    )

    title = models.CharField(max_length=255)
    topic = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    copy = models.TextField(blank=True, default="")
    creative_instructions = models.TextField(blank=True, default="")
    cta = models.CharField(max_length=255, blank=True, default="")
    destination_url = models.URLField(max_length=2048, blank=True, default="")
    utm_url = models.URLField(max_length=2048, blank=True, default="")
    hashtags = models.JSONField(default=list, blank=True)
    internal_notes = models.TextField(blank=True, default="")

    publication_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=ContentStatus.choices, default=ContentStatus.DRAFT)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_content_items",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_content_items",
    )

    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["campaign", "is_archived", "publication_at"], name="content_campaign_date_idx"),
            models.Index(fields=["campaign", "status"], name="content_campaign_status_idx"),
            models.Index(fields=["assignee", "publication_at"], name="content_assignee_date_idx"),
            models.Index(fields=["platform", "publication_at"], name="content_platform_date_idx"),
            models.Index(fields=["content_format", "status"], name="content_format_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(status__in=PUBLICATION_DATE_REQUIRED_STATUSES)
                    | models.Q(publication_at__isnull=False)
                ),
                name="content_publication_date_required",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_archived=True, archived_at__isnull=False)
                    | models.Q(is_archived=False, archived_at__isnull=True)
                ),
                name="content_archive_consistency",
            ),
        ]

    @property
    def workspace(self):
        return self.campaign.workspace

    def clean(self):
        super().clean()

        if not self.campaign_id:
            return

        errors = {}
        workspace_id = self.campaign.workspace_id

        if self.platform_id and self.platform.workspace_id != workspace_id:
            errors["platform"] = "Platform does not belong to this workspace."

        if self.content_format_id and self.content_format.workspace_id != workspace_id:
            errors["content_format"] = "Content format does not belong to this workspace."

        if self.assignee_id:
            if self.assignee.workspace_id != workspace_id:
                errors["assignee"] = "Assignee does not belong to this workspace."
            elif self.assignee.role == "guest" or not self.assignee.user.is_active:
                errors["assignee"] = "Assignee is not eligible for content assignment."

        if self.related_task_id and self.related_task.campaign_id != self.campaign_id:
            errors["related_task"] = "Related task does not belong to this campaign."

        if self.status in PUBLICATION_DATE_REQUIRED_STATUSES and self.publication_at is None:
            errors["publication_at"] = "Publication date is required for this status."

        if not isinstance(self.hashtags, list) or any(
            not isinstance(tag, str) or not tag.strip() or len(tag) > 100
            for tag in self.hashtags
        ):
            errors["hashtags"] = "Hashtags must be a list of non-empty strings."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.title


class ContentStatusHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content_item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="status_history")
    previous_status = models.CharField(max_length=30, choices=ContentStatus.choices, blank=True, default="")
    new_status = models.CharField(max_length=30, choices=ContentStatus.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="content_status_changes",
    )
    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["content_item", "-created_at"], name="content_status_history_idx"),
        ]

    def __str__(self):
        return f"{self.previous_status} -> {self.new_status}"


class PostingPlanPreference(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey("organization.Workspace", on_delete=models.CASCADE, related_name="posting_plan_preferences")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="posting_plan_preferences")

    visible_columns = models.JSONField(default=list, blank=True)
    column_order = models.JSONField(default=list, blank=True)
    column_widths = models.JSONField(default=dict, blank=True)

    default_ordering = models.CharField(max_length=100, default="publication_at")
    default_grouping = models.CharField(max_length=50, default="none")
    default_filters = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "user"],
                name="unique_posting_plan_preference",
            ),
        ]

    def __str__(self):
        return f"{self.workspace_id} - {self.user_id}"

