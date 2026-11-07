import uuid

from django.conf import settings
from django.db import models

from campaignflow.documents.storage import task_attachment_storage, task_attachment_upload_to


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
