import mimetypes
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from campaignflow.documents.models import TaskAttachment
from campaignflow.documents.permissions import TaskAttachmentPermission
from campaignflow.documents.selectors import TaskAttachmentSelector
from campaignflow.tasks.models import TaskActivityType
from campaignflow.tasks.services import TaskActivityService


class TaskAttachmentService:
    MAX_FILE_SIZE = 20 * 1024 * 1024
    ALLOWED_TYPES = {
        ".pdf": {"application/pdf"},
        ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        ".png": {"image/png"},
        ".jpg": {"image/jpeg"},
        ".jpeg": {"image/jpeg"},
        ".txt": {"text/plain"},
        ".csv": {"text/csv", "text/plain", "application/csv", "application/vnd.ms-excel"},
    }

    @classmethod
    def validate_file(cls, uploaded_file):
        if uploaded_file is None:
            raise ValidationError({"file": "File is required."})

        filename = Path(uploaded_file.name.replace("\\", "/")).name
        extension = Path(filename).suffix.lower()

        if not filename or len(filename) > 255:
            raise ValidationError({"file": "Invalid filename."})
        if extension not in cls.ALLOWED_TYPES:
            raise ValidationError({"file": "Unsupported file extension."})
        if uploaded_file.size == 0:
            raise ValidationError({"file": "File cannot be empty."})
        if uploaded_file.size > cls.MAX_FILE_SIZE:
            raise ValidationError({"file": "File cannot exceed 20 MB."})

        declared_mime = (getattr(uploaded_file, "content_type", "") or "").lower().split(";")[0].strip()
        if declared_mime and declared_mime not in cls.ALLOWED_TYPES[extension]:
            raise ValidationError({"file": "File MIME type does not match its extension."})

        uploaded_file.seek(0)
        header = uploaded_file.read(16)
        uploaded_file.seek(0)

        if extension == ".pdf" and not header.startswith(b"%PDF-"):
            raise ValidationError({"file": "Invalid PDF signature."})
        if extension == ".png" and not header.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValidationError({"file": "Invalid PNG signature."})
        if extension in (".jpg", ".jpeg") and not header.startswith(b"\xff\xd8\xff"):
            raise ValidationError({"file": "Invalid JPEG signature."})
        if extension in (".docx", ".xlsx") and not header.startswith(b"PK\x03\x04"):
            raise ValidationError({"file": "Invalid Office document signature."})

        if extension in (".txt", ".csv"):
            sample = uploaded_file.read(4096)
            uploaded_file.seek(0)
            if b"\x00" in sample:
                raise ValidationError({"file": "Text files cannot contain binary null bytes."})
            try:
                sample.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise ValidationError({"file": "Text files must use UTF-8 encoding."})

        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return filename, mime_type

    @classmethod
    def create_attachment(cls, *, workspace, task_id, uploaded_by, uploaded_file):
        filename, mime_type = cls.validate_file(uploaded_file)

        with transaction.atomic():
            task = TaskAttachmentSelector.get_task(workspace=workspace, task_id=task_id)
            if task is None:
                raise NotFound("Task not found.")

            attachment = TaskAttachment(
                task=task, uploaded_by=uploaded_by, original_filename=filename,
                mime_type=mime_type, file_size=uploaded_file.size,
            )

            try:
                attachment.file.save(filename, uploaded_file, save=False)
                attachment.save()
                TaskActivityService.record(
                    task=task, actor=uploaded_by, action=TaskActivityType.ATTACHMENT_UPLOADED,
                    metadata={
                        "attachment_id": str(attachment.id),
                        "filename": filename,
                        "file_size": attachment.file_size,
                    },
                )
            except Exception:
                if attachment.file.name:
                    attachment.file.storage.delete(attachment.file.name)
                raise

            return attachment

    @staticmethod
    @transaction.atomic
    def delete_attachment(*, workspace, task_id, attachment_id, user, membership):
        attachment = TaskAttachmentSelector.get_attachment(workspace=workspace, task_id=task_id, attachment_id=attachment_id, for_update=True)
        if attachment is None:
            raise NotFound("Attachment not found.")
        if attachment.task.campaign.is_archived:
            raise ValidationError({"attachment": "Archived campaign attachments cannot be deleted."})

        TaskAttachmentPermission.require_delete(membership=membership, attachment=attachment, user=user)

        attachment.is_deleted = True
        attachment.deleted_at = timezone.now()
        attachment.save(update_fields=["is_deleted", "deleted_at"])

        TaskActivityService.record(
            task=attachment.task, actor=user, action=TaskActivityType.ATTACHMENT_DELETED,
            metadata={"attachment_id": str(attachment.id), "filename": attachment.original_filename},
        )
        return attachment
