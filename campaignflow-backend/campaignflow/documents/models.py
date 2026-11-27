import uuid

from django.conf import settings
from django.db import models

from campaignflow.documents.storage import task_attachment_storage, task_attachment_upload_to
from campaignflow.documents.validators import validate_template_structure
from django.core.exceptions import ValidationError

from campaignflow.documents.enums import (
    DocumentTemplateCategory,
    DocumentTemplateStatus,
    DocumentStatus,
)

class TaskAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey("tasks.Task", on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="task_attachments")
    file = models.FileField(storage=task_attachment_storage, upload_to=task_attachment_upload_to, max_length=500)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=150)
    file_size = models.PositiveBigIntegerField()
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["task", "is_deleted", "created_at"]),
            models.Index(fields=["uploaded_by", "created_at"]),
        ]

    def __str__(self):
        return self.original_filename


def default_template_structure():
    return {
        "schema_version": 1,
        "sections": [],
    }


class DocumentTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    workspace = models.ForeignKey(
        "organization.Workspace", on_delete=models.CASCADE,
        related_name="document_templates",
    )

    name = models.CharField(max_length=255)
    code = models.SlugField(max_length=100)
    description = models.TextField(blank=True, default="")

    category = models.CharField(
        max_length=30, choices=DocumentTemplateCategory.choices,
        default=DocumentTemplateCategory.CUSTOM,
    )

    is_system = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)

    draft_structure = models.JSONField(
        default=default_template_structure,
        validators=[validate_template_structure],
    )

    latest_version = models.PositiveIntegerField(default=0)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="created_document_templates",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="updated_document_templates",
    )

    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]

        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "code"],
                name="unique_workspace_template_code",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_archived=True, archived_at__isnull=False)
                    | models.Q(is_archived=False, archived_at__isnull=True)
                ),
                name="document_template_archive_check",
            ),
        ]

        indexes = [
            models.Index(
                fields=["workspace", "is_archived", "category"],
                name="doc_template_category_idx",
            ),
            models.Index(
                fields=["workspace", "is_system"],
                name="doc_template_system_idx",
            ),
        ]

    @property
    def status(self):
        if self.is_archived:
            return DocumentTemplateStatus.ARCHIVED

        if self.latest_version > 0:
            return DocumentTemplateStatus.PUBLISHED

        return DocumentTemplateStatus.DRAFT

    def __str__(self):
        return self.name


class DocumentTemplateVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    template = models.ForeignKey(
        DocumentTemplate, on_delete=models.PROTECT,
        related_name="versions",
    )

    version = models.PositiveIntegerField()

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    category = models.CharField(
        max_length=30, choices=DocumentTemplateCategory.choices,
    )

    structure = models.JSONField(validators=[validate_template_structure])
    change_summary = models.TextField(blank=True, default="")

    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="published_document_template_versions",
    )

    published_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]

        constraints = [
            models.UniqueConstraint(
                fields=["template", "version"],
                name="unique_document_template_version",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1),
                name="positive_document_template_version",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Published template versions cannot be modified.")

        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Published template versions cannot be deleted.")

    def __str__(self):
        return f"{self.template_id} v{self.version}"

class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.CASCADE,
        related_name="documents",
    )

    template_version = models.ForeignKey(
        DocumentTemplateVersion, on_delete=models.PROTECT,
        null=True, blank=True, related_name="documents",
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")

    category = models.CharField(
        max_length=30, choices=DocumentTemplateCategory.choices,
        default=DocumentTemplateCategory.CUSTOM,
    )

    structure_snapshot = models.JSONField(
        default=default_template_structure,
        validators=[validate_template_structure],
    )

    content = models.JSONField(default=dict, blank=True)

    owner = models.ForeignKey(
        "organization.WorkspaceMember", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="owned_documents",
    )

    status = models.CharField(
        max_length=30, choices=DocumentStatus.choices,
        default=DocumentStatus.DRAFT,
    )

    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="created_documents",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="updated_documents",
    )

    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

        indexes = [
            models.Index(
                fields=["campaign", "is_archived", "status"],
                name="document_campaign_status_idx",
            ),
            models.Index(
                fields=["campaign", "category"],
                name="document_campaign_cat_idx",
            ),
            models.Index(
                fields=["owner", "status"],
                name="document_owner_status_idx",
            ),
            models.Index(
                fields=["campaign", "created_at"],
                name="document_campaign_created_idx",
            ),
        ]

        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(is_archived=True, archived_at__isnull=False)
                    | models.Q(is_archived=False, archived_at__isnull=True)
                ),
                name="document_archive_consistency",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(period_start__isnull=True, period_end__isnull=True)
                    | models.Q(
                        period_start__isnull=False,
                        period_end__isnull=False,
                        period_end__gte=models.F("period_start"),
                    )
                ),
                name="document_valid_period",
            ),
        ]

    @property
    def workspace(self):
        return self.campaign.workspace

    def clean(self):
        super().clean()

        from campaignflow.documents.validators import validate_document_content

        errors = {}

        if bool(self.period_start) != bool(self.period_end):
            errors["period_end"] = "Both reporting period dates are required."

        elif self.period_start and self.period_end:
            if self.period_start > self.period_end:
                errors["period_end"] = "End date cannot be before start date."

        if self.campaign_id:
            campaign = self.campaign
            workspace_id = campaign.workspace_id

            if self.template_version_id:
                if self.template_version.template.workspace_id != workspace_id:
                    errors["template_version"] = (
                        "Template version does not belong to this workspace."
                    )

            if self.owner_id:
                if self.owner.workspace_id != workspace_id:
                    errors["owner"] = "Owner does not belong to this workspace."

                elif self.owner.role == "guest":
                    errors["owner"] = "Guests cannot own documents."

        try:
            validate_document_content(
                structure=self.structure_snapshot,
                content=self.content,
            )
        except ValidationError as exc:
            errors["content"] = exc.messages

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.title