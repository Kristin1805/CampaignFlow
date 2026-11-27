import mimetypes
from pathlib import Path
from copy import deepcopy

from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from campaignflow.documents.models import TaskAttachment
from campaignflow.documents.permissions import TaskAttachmentPermission, DocumentPermission
from campaignflow.documents.selectors import TaskAttachmentSelector, DocumentSelector
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
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction

from campaignflow.documents.constants import DOCUMENT_STATUS_TRANSITIONS
from campaignflow.documents.enums import DocumentStatus, DocumentTemplateCategory
from campaignflow.documents.generators import DocumentGenerator
from campaignflow.documents.models import Document, default_template_structure
from campaignflow.documents.permissions import DocumentPermission
from campaignflow.documents.selectors import DocumentSelector

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

class DocumentService:

    EDITABLE_METADATA_FIELDS = {
        "title",
        "description",
        "category",
        "owner_id",
        "period_start",
        "period_end",
    }

    GENERATION_FIELDS = {
        "campaign_id",
        "template_id",
        "template_version_id",
        "title",
        "description",
        "owner_id",
        "period_start",
        "period_end",
        "populate_placeholders",
    }

    BLANK_FIELDS = {
        "campaign_id",
        "title",
        "description",
        "category",
        "owner_id",
        "period_start",
        "period_end",
    }

    @staticmethod
    def get_membership(*, workspace_id, user):
        return DocumentPermission.get_membership(
            workspace_id=workspace_id, user=user,
        )

    @staticmethod
    def validate_fields(*, data, allowed_fields):
        unknown_fields = set(data) - allowed_fields

        if unknown_fields:
            raise ValidationError({
                field: "This field is not supported."
                for field in sorted(unknown_fields)
            })

    @staticmethod
    def get_campaign(*, workspace, campaign_id, lock=False):
        campaign = DocumentSelector.get_campaign(
            workspace=workspace,
            campaign_id=campaign_id,
            lock=lock,
        )

        if campaign is None:
            raise NotFound("Campaign not found.")

        return campaign

    @staticmethod
    def resolve_owner(*, membership, owner_id):
        if owner_id is None or owner_id == membership.id:
            return membership

        DocumentPermission.require_management(membership=membership)

        owner = DocumentSelector.get_eligible_owner(
            workspace=membership.workspace,
            owner_id=owner_id,
        )

        if owner is None:
            raise ValidationError({
                "owner_id": "Invalid document owner.",
            })

        return owner

    @staticmethod
    def save_document(*, document, update_fields=None):
        validate_document_model(document)

        if update_fields is None:
            document.save()
        else:
            document.save(update_fields=update_fields)

        return document

    @classmethod
    def get_document(
        cls, *, membership, document_id,
        include_archived=False, lock=False,
    ):
        document = DocumentSelector.get_by_id(
            workspace=membership.workspace,
            document_id=document_id,
            include_archived=include_archived,
            lock=lock,
        )

        if document is None:
            raise NotFound("Document not found.")

        return document

    @classmethod
    def get_list(cls, *, workspace_id, user, filters=None, campaign_id=None):
        membership = cls.get_membership(
            workspace_id=workspace_id, user=user,
        )

        filters = dict(filters or {})

        if filters.get("is_archived"):
            DocumentPermission.require_management(membership=membership)

        if campaign_id is not None:
            if filters.get("campaign_id") not in {None, campaign_id}:
                raise ValidationError({
                    "campaign_id": "Campaign filter does not match the URL.",
                })

            filters["campaign_id"] = campaign_id

        if filters.get("campaign_id") is not None:
            cls.get_campaign(
                workspace=membership.workspace,
                campaign_id=filters["campaign_id"],
            )

        queryset = DocumentSelector.get_documents(
            workspace=membership.workspace,
            filters=filters,
        )

        return queryset, membership

    @classmethod
    def get_details(cls, *, workspace_id, document_id, user):
        membership = cls.get_membership(
            workspace_id=workspace_id, user=user,
        )

        document = cls.get_document(
            membership=membership,
            document_id=document_id,
            include_archived=DocumentPermission.is_management(
                membership=membership,
            ),
        )

        return document, membership

    @classmethod
    def prepare_generation(cls, *, membership, data, lock=False):
        data = dict(data)

        cls.validate_fields(
            data=data,
            allowed_fields=cls.GENERATION_FIELDS,
        )

        DocumentPermission.require_create(membership=membership)

        missing_fields = {"campaign_id", "template_id"} - set(data)

        if missing_fields:
            raise ValidationError({
                field: "This field is required."
                for field in missing_fields
            })

        campaign = cls.get_campaign(
            workspace=membership.workspace,
            campaign_id=data["campaign_id"],
            lock=lock,
        )

        version = DocumentSelector.get_published_version(
            workspace=membership.workspace,
            template_id=data["template_id"],
            version_id=data.get("template_version_id"),
            lock=lock,
        )

        if version is None:
            raise NotFound("Published document template version not found.")

        owner = cls.resolve_owner(
            membership=membership,
            owner_id=data.get("owner_id"),
        )

        generator = DocumentGenerator(
            campaign=campaign,
            populate_placeholders=data.get("populate_placeholders", True),
        )

        generated = generator.generate(structure=version.structure)

        return {
            "campaign": campaign,
            "version": version,
            "owner": owner,
            "title": data.get("title") or version.name,
            "description": data.get("description", version.description),
            "category": version.category,
            "period_start": data.get("period_start"),
            "period_end": data.get("period_end"),
            "generated": generated,
        }

    @staticmethod
    def build_document(*, prepared, user):
        return Document(
            campaign=prepared["campaign"],
            template_version=prepared.get("version"),
            title=prepared["title"],
            description=prepared["description"],
            category=prepared["category"],
            owner=prepared["owner"],
            period_start=prepared.get("period_start"),
            period_end=prepared.get("period_end"),
            structure_snapshot=deepcopy(
                prepared["generated"]["structure_snapshot"],
            ),
            content=deepcopy(prepared["generated"]["content"]),
            status=DocumentStatus.DRAFT,
            created_by=user,
            updated_by=user,
        )

    @classmethod
    def preview(cls, *, workspace_id, user, data):
        membership = cls.get_membership(
            workspace_id=workspace_id, user=user,
        )

        prepared = cls.prepare_generation(
            membership=membership,
            data=data,
        )

        document = cls.build_document(
            prepared=prepared,
            user=user,
        )

        validate_document_model(document)

        version = prepared["version"]

        return {
            "workspace_id": str(membership.workspace_id),
            "campaign_id": str(document.campaign_id),
            "template_id": str(version.template_id),
            "template_version_id": str(version.id),
            "template_version": version.version,
            "title": document.title,
            "description": document.description,
            "category": document.category,
            "owner_id": str(document.owner_id),
            "period_start": document.period_start,
            "period_end": document.period_end,
            "status": DocumentStatus.DRAFT,
            **prepared["generated"],
        }

    @classmethod
    @transaction.atomic
    def generate(cls, *, workspace_id, user, data):
        membership = cls.get_membership(
            workspace_id=workspace_id, user=user,
        )

        prepared = cls.prepare_generation(
            membership=membership,
            data=data,
            lock=True,
        )

        document = cls.build_document(
            prepared=prepared,
            user=user,
        )

        cls.save_document(document=document)

        return document, membership

    @classmethod
    @transaction.atomic
    def create_blank(cls, *, workspace_id, user, data):
        membership = cls.get_membership(
            workspace_id=workspace_id, user=user,
        )

        DocumentPermission.require_create(membership=membership)

        data = dict(data)

        cls.validate_fields(
            data=data,
            allowed_fields=cls.BLANK_FIELDS,
        )

        missing_fields = {"campaign_id", "title"} - set(data)

        if missing_fields:
            raise ValidationError({
                field: "This field is required."
                for field in missing_fields
            })

        campaign = cls.get_campaign(
            workspace=membership.workspace,
            campaign_id=data["campaign_id"],
            lock=True,
        )

        owner = cls.resolve_owner(
            membership=membership,
            owner_id=data.get("owner_id"),
        )

        generator = DocumentGenerator(
            campaign=campaign,
            populate_placeholders=False,
        )

        generated = generator.generate(
            structure=default_template_structure(),
        )

        document = cls.build_document(
            prepared={
                "campaign": campaign,
                "version": None,
                "owner": owner,
                "title": data["title"],
                "description": data.get("description", ""),
                "category": data.get(
                    "category", DocumentTemplateCategory.CUSTOM,
                ),
                "period_start": data.get("period_start"),
                "period_end": data.get("period_end"),
                "generated": generated,
            },
            user=user,
        )

        cls.save_document(document=document)

        return document, membership

    @classmethod
    @transaction.atomic
    def update_metadata(cls, *, workspace_id, document_id, user, data):
        membership = cls.get_membership(
            workspace_id=workspace_id, user=user,
        )

        document = cls.get_document(
            membership=membership,
            document_id=document_id,
            lock=True,
        )

        DocumentPermission.require_edit(
            membership=membership,
            document=document,
        )

        data = dict(data)

        cls.validate_fields(
            data=data,
            allowed_fields=cls.EDITABLE_METADATA_FIELDS,
        )

        if "owner_id" in data:
            DocumentPermission.require_management(membership=membership)

            owner = cls.resolve_owner(
                membership=membership,
                owner_id=data.pop("owner_id"),
            )

            data["owner"] = owner

        changed_fields = []

        for field, value in data.items():
            if getattr(document, field) != value:
                setattr(document, field, value)
                changed_fields.append(field)

        if changed_fields:
            document.updated_by = user

            cls.save_document(
                document=document,
                update_fields=[
                    *changed_fields,
                    "updated_by",
                    "updated_at",
                ],
            )

        return document, membership

    @classmethod
    @transaction.atomic
    def duplicate(cls, *, workspace_id, document_id, user, data=None):
        membership = cls.get_membership(
            workspace_id=workspace_id, user=user,
        )

        DocumentPermission.require_create(membership=membership)

        original = cls.get_document(
            membership=membership,
            document_id=document_id,
            lock=True,
        )

        data = dict(data or {})

        cls.validate_fields(
            data=data,
            allowed_fields={"title"},
        )

        document = Document(
            campaign=original.campaign,
            template_version=original.template_version,
            title=data.get("title") or f"{original.title[:248]} (Copy)",
            description=original.description,
            category=original.category,
            owner=membership,
            structure_snapshot=deepcopy(original.structure_snapshot),
            content=deepcopy(original.content),
            period_start=original.period_start,
            period_end=original.period_end,
            status=DocumentStatus.DRAFT,
            created_by=user,
            updated_by=user,
        )

        cls.save_document(document=document)

        return document, membership

    @classmethod
    @transaction.atomic
    def change_status(cls, *, workspace_id, document_id, user, status):
        membership = cls.get_membership(
            workspace_id=workspace_id, user=user,
        )

        document = cls.get_document(
            membership=membership,
            document_id=document_id,
            lock=True,
        )

        DocumentPermission.require_edit(
            membership=membership,
            document=document,
        )

        if status == document.status:
            return document, membership

        allowed = DOCUMENT_STATUS_TRANSITIONS.get(
            document.status, set(),
        )

        if status not in allowed:
            raise ValidationError({
                "status": (
                    f"Invalid transition from {document.status} to {status}."
                ),
            })

        document.status = status
        document.updated_by = user

        cls.save_document(
            document=document,
            update_fields=["status", "updated_by", "updated_at"],
        )

        return document, membership

    @classmethod
    @transaction.atomic
    def archive(cls, *, workspace_id, document_id, user):
        membership = cls.get_membership(
            workspace_id=workspace_id, user=user,
        )

        DocumentPermission.require_management(membership=membership)

        document = cls.get_document(
            membership=membership,
            document_id=document_id,
            include_archived=True,
            lock=True,
        )

        if not document.is_archived:
            document.is_archived = True
            document.archived_at = timezone.now()
            document.updated_by = user

            cls.save_document(
                document=document,
                update_fields=[
                    "is_archived",
                    "archived_at",
                    "updated_by",
                    "updated_at",
                ],
            )

        return document, membership

    @classmethod
    @transaction.atomic
    def restore(cls, *, workspace_id, document_id, user):
        membership = cls.get_membership(
            workspace_id=workspace_id, user=user,
        )

        DocumentPermission.require_management(membership=membership)

        document = cls.get_document(
            membership=membership,
            document_id=document_id,
            include_archived=True,
            lock=True,
        )

        if document.is_archived:
            document.is_archived = False
            document.archived_at = None
            document.updated_by = user

            cls.save_document(
                document=document,
                update_fields=[
                    "is_archived",
                    "archived_at",
                    "updated_by",
                    "updated_at",
                ],
            )

        return document, membership