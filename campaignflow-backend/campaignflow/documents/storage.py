import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateTaskAttachmentStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("location", getattr(settings, "PRIVATE_MEDIA_ROOT", Path(settings.BASE_DIR) / "private_media"))
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)

    def url(self, name):
        raise ValueError("Private attachments do not have public URLs.")


task_attachment_storage = PrivateTaskAttachmentStorage()


def task_attachment_upload_to(instance, filename):
    extension = Path(filename).suffix.lower()
    return f"task_attachments/{instance.task_id}/{uuid.uuid4().hex}{extension}"
