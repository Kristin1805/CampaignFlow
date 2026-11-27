import mimetypes
from pathlib import Path
from copy import deepcopy

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from campaignflow.documents.models import TaskAttachment
from campaignflow.documents.permissions import TaskAttachmentPermission
from campaignflow.documents.selectors import TaskAttachmentSelector
from campaignflow.tasks.models import TaskActivityType
from campaignflow.tasks.services import TaskActivityService

from campaignflow.documents.default_templates import (
    DEFAULT_DOCUMENT_TEMPLATES,
    SYSTEM_TEMPLATE_CODES,
)
from campaignflow.documents.exceptions import DocumentTemplateConflict
from campaignflow.documents.models import DocumentTemplate, DocumentTemplateVersion
from campaignflow.documents.permissions import DocumentTemplatePermission
from campaignflow.documents.selectors import DocumentTemplateSelector
from campaignflow.documents.validators import DocumentTemplateValidator


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



def validate_document_model(instance):
    try:
        instance.full_clean()
    except DjangoValidationError as exc:
        errors = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        raise ValidationError(errors)


def validate_structure(structure, require_sections=False):
    try:
        DocumentTemplateValidator.validate(
            structure, require_sections=require_sections,
        )
    except DjangoValidationError as exc:
        raise ValidationError({"structure": exc.messages})


class DocumentTemplateDefaultsService:

    @staticmethod
    @transaction.atomic
    def initialize_workspace(*, workspace):
        created_count = 0

        for definition in DEFAULT_DOCUMENT_TEMPLATES:
            definition = deepcopy(definition)
            code = definition.pop("code")

            validate_structure(
                definition["draft_structure"], require_sections=True,
            )

            template, created = DocumentTemplate.objects.get_or_create(
                workspace=workspace,
                code=code,
                defaults={
                    **definition,
                    "is_system": True,
                    "latest_version": 1,
                    "created_by": workspace.created_by,
                    "updated_by": workspace.created_by,
                },
            )

            if not created:
                if not template.is_system:
                    raise DocumentTemplateConflict(
                        f"System template code '{code}' is already in use.",
                    )

                continue

            DocumentTemplateVersion.objects.create(
                template=template,
                version=1,
                name=template.name,
                description=template.description,
                category=template.category,
                structure=deepcopy(template.draft_structure),
                change_summary="Initial system template.",
                published_by=workspace.created_by,
            )

            created_count += 1

        return created_count


class DocumentTemplateService:
    EDITABLE_METADATA_FIELDS = {
        "name", "code", "description", "category",
    }

    @staticmethod
    def get_membership(*, workspace_id, user):
        membership = DocumentTemplatePermission.get_membership(
            workspace_id=workspace_id, user=user,
        )

        DocumentTemplatePermission.require_view(membership=membership)

        return membership

    @staticmethod
    def validate_fields(*, data, allowed_fields):
        unknown_fields = set(data) - set(allowed_fields)

        if unknown_fields:
            raise ValidationError({
                field: "This field cannot be modified."
                for field in sorted(unknown_fields)
            })

    @staticmethod
    def validate_code(*, workspace, code, template_id=None):
        if code in SYSTEM_TEMPLATE_CODES:
            raise ValidationError({
                "code": "This code is reserved for a system template.",
            })

        queryset = DocumentTemplate.objects.filter(
            workspace=workspace, code=code,
        )

        if template_id is not None:
            queryset = queryset.exclude(id=template_id)

        if queryset.exists():
            raise ValidationError({
                "code": "A template with this code already exists.",
            })

    @staticmethod
    def save_template(*, template, update_fields=None):
        validate_document_model(template)

        try:
            with transaction.atomic():
                if update_fields is None:
                    template.save()
                else:
                    template.save(update_fields=update_fields)

        except IntegrityError as exc:
            raise DocumentTemplateConflict(
                "The template could not be saved due to a database conflict.",
            ) from exc

        return template

    @classmethod
    def get_list(cls, *, workspace_id, user, filters=None):
        membership = cls.get_membership(workspace_id=workspace_id, user=user)
        is_management = DocumentTemplatePermission.is_management(membership=membership)

        if not is_management and (
            (filters or {}).get("is_archived")
            or (filters or {}).get("status") in {"archived", "draft"}
        ):
            raise PermissionDenied("You cannot view draft or archived templates.")

        queryset = DocumentTemplateSelector.get_templates(
            workspace=membership.workspace,
            filters=filters,
            is_management=is_management,
        )

        return queryset, membership

    @classmethod
    def get_details(cls, *, workspace_id, template_id, user):
        membership = cls.get_membership(workspace_id=workspace_id, user=user)
        is_management = DocumentTemplatePermission.is_management(membership=membership)

        template = DocumentTemplateSelector.get_by_id(
            workspace=membership.workspace,
            template_id=template_id,
            include_archived=is_management,
        )

        if not is_management and template.latest_version == 0:
            raise NotFound("Document template not found.")

        return template, membership

    @classmethod
    def get_locked_template(cls, *, workspace_id, template_id, user, allow_archived=False):
        membership = cls.get_membership(workspace_id=workspace_id, user=user)

        DocumentTemplatePermission.require_management(membership=membership)

        template = DocumentTemplateSelector.get_by_id(
            workspace=membership.workspace,
            template_id=template_id,
            include_archived=allow_archived,
            lock=True,
        )

        return template, membership

    @classmethod
    @transaction.atomic
    def create(cls, *, workspace_id, user, data):
        membership = cls.get_membership(workspace_id=workspace_id, user=user)

        DocumentTemplatePermission.require_management(membership=membership)

        data = dict(data)

        cls.validate_fields(
            data=data,
            allowed_fields=cls.EDITABLE_METADATA_FIELDS | {"draft_structure"},
        )

        missing_fields = {"name", "code"} - set(data)

        if missing_fields:
            raise ValidationError({
                field: "This field is required." for field in missing_fields
            })

        data["code"] = data["code"].lower()

        cls.validate_code(workspace=membership.workspace, code=data["code"])

        template = DocumentTemplate(
            workspace=membership.workspace,
            created_by=user,
            updated_by=user,
            **data,
        )

        cls.save_template(template=template)

        return template, membership

    @classmethod
    @transaction.atomic
    def update_metadata(cls, *, workspace_id, template_id, user, data):
        template, membership = cls.get_locked_template(
            workspace_id=workspace_id, template_id=template_id, user=user,
        )

        DocumentTemplatePermission.require_edit(
            membership=membership, template=template,
        )

        data = dict(data)

        cls.validate_fields(data=data, allowed_fields=cls.EDITABLE_METADATA_FIELDS)

        if "code" in data:
            data["code"] = data["code"].lower()

            cls.validate_code(
                workspace=membership.workspace,
                code=data["code"],
                template_id=template.id,
            )

        changed_fields = []

        for field, value in data.items():
            if getattr(template, field) != value:
                setattr(template, field, value)
                changed_fields.append(field)

        if changed_fields:
            template.updated_by = user

            cls.save_template(
                template=template,
                update_fields=[*changed_fields, "updated_by", "updated_at"],
            )

        return template, membership

    @classmethod
    @transaction.atomic
    def update_draft(cls, *, workspace_id, template_id, user, structure, expected_updated_at):
        template, membership = cls.get_locked_template(
            workspace_id=workspace_id, template_id=template_id, user=user,
        )

        DocumentTemplatePermission.require_edit(
            membership=membership, template=template,
        )

        if template.updated_at != expected_updated_at:
            raise DocumentTemplateConflict({
                "message": "The template has been modified by another user.",
                "updated_at": template.updated_at.isoformat(),
            })

        validate_structure(structure)

        if template.draft_structure == structure:
            return template, membership

        template.draft_structure = deepcopy(structure)
        template.updated_by = user

        cls.save_template(
            template=template,
            update_fields=["draft_structure", "updated_by", "updated_at"],
        )

        return template, membership

    @classmethod
    @transaction.atomic
    def publish(cls, *, workspace_id, template_id, user, expected_updated_at, change_summary=""):
        template, membership = cls.get_locked_template(
            workspace_id=workspace_id, template_id=template_id, user=user,
        )

        DocumentTemplatePermission.require_edit(
            membership=membership, template=template,
        )

        if template.updated_at != expected_updated_at:
            raise DocumentTemplateConflict({
                "message": "The template has been modified by another user.",
                "updated_at": template.updated_at.isoformat(),
            })

        validate_structure(template.draft_structure, require_sections=True)

        latest_version = DocumentTemplateSelector.get_latest_version(template=template)

        if latest_version is not None:
            has_changes = any([
                latest_version.structure != template.draft_structure,
                latest_version.name != template.name,
                latest_version.description != template.description,
                latest_version.category != template.category,
            ])

            if not has_changes:
                raise DocumentTemplateConflict("There are no unpublished changes.")

        version_number = template.latest_version + 1

        version = DocumentTemplateVersion(
            template=template,
            version=version_number,
            name=template.name,
            description=template.description,
            category=template.category,
            structure=deepcopy(template.draft_structure),
            change_summary=change_summary,
            published_by=user,
        )

        validate_document_model(version)
        version.save()

        template.latest_version = version_number
        template.updated_by = user

        template.save(
            update_fields=["latest_version", "updated_by", "updated_at"],
        )

        return version, membership

    @classmethod
    def get_versions(cls, *, workspace_id, template_id, user):
        template, membership = cls.get_details(
            workspace_id=workspace_id, template_id=template_id, user=user,
        )

        return DocumentTemplateSelector.get_versions(template=template), membership

    @classmethod
    def get_version(cls, *, workspace_id, template_id, version_id, user):
        template, membership = cls.get_details(
            workspace_id=workspace_id, template_id=template_id, user=user,
        )

        version = DocumentTemplateSelector.get_version(
            template=template, version_id=version_id,
        )

        return version, membership

    @classmethod
    @transaction.atomic
    def restore_version(cls, *, workspace_id, template_id, version_id, user, expected_updated_at):
        template, membership = cls.get_locked_template(
            workspace_id=workspace_id, template_id=template_id, user=user,
        )

        DocumentTemplatePermission.require_edit(
            membership=membership, template=template,
        )

        if template.updated_at != expected_updated_at:
            raise DocumentTemplateConflict({
                "message": "The template has been modified by another user.",
                "updated_at": template.updated_at.isoformat(),
            })

        version = DocumentTemplateSelector.get_version(
            template=template, version_id=version_id,
        )

        template.draft_structure = deepcopy(version.structure)
        template.name = version.name
        template.description = version.description
        template.category = version.category
        template.updated_by = user

        cls.save_template(
            template=template,
            update_fields=[
                "draft_structure", "name", "description",
                "category", "updated_by", "updated_at",
            ],
        )

        return template, membership

    @classmethod
    @transaction.atomic
    def duplicate(cls, *, workspace_id, template_id, user, data):
        original, membership = cls.get_locked_template(
            workspace_id=workspace_id, template_id=template_id, user=user,
        )

        data = dict(data)

        cls.validate_fields(
            data=data,
            allowed_fields={"name", "code", "version_id"},
        )

        if not data.get("code"):
            raise ValidationError({"code": "This field is required."})

        version_id = data.pop("version_id", None)

        if version_id is not None:
            source = DocumentTemplateSelector.get_version(
                template=original, version_id=version_id,
            )

            source_structure = source.structure

        else:
            source = original
            source_structure = original.draft_structure

        duplicate_data = {
            "name": data.get("name") or f"{source.name[:248]} (Copy)",
            "code": data["code"],
            "category": source.category,
            "description": source.description,
            "draft_structure": deepcopy(source_structure),
        }

        return cls.create(
            workspace_id=workspace_id, user=user, data=duplicate_data,
        )

    @classmethod
    @transaction.atomic
    def archive(cls, *, workspace_id, template_id, user):
        template, membership = cls.get_locked_template(
            workspace_id=workspace_id, template_id=template_id,
            user=user, allow_archived=True,
        )

        DocumentTemplatePermission.require_edit(
            membership=membership, template=template, allow_archived=True,
        )

        if not template.is_archived:
            template.is_archived = True
            template.archived_at = timezone.now()
            template.updated_by = user

            cls.save_template(
                template=template,
                update_fields=[
                    "is_archived", "archived_at", "updated_by", "updated_at",
                ],
            )

        return template, membership

    @classmethod
    @transaction.atomic
    def restore(cls, *, workspace_id, template_id, user):
        template, membership = cls.get_locked_template(
            workspace_id=workspace_id, template_id=template_id,
            user=user, allow_archived=True,
        )

        DocumentTemplatePermission.require_edit(
            membership=membership, template=template, allow_archived=True,
        )

        if template.is_archived:
            template.is_archived = False
            template.archived_at = None
            template.updated_by = user

            cls.save_template(
                template=template,
                update_fields=[
                    "is_archived", "archived_at", "updated_by", "updated_at",
                ],
            )

        return template, membership