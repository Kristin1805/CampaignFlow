from copy import deepcopy

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction, IntegrityError
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from campaignflow.content.constants import (
    DEFAULT_CONTENT_PLATFORMS, DEFAULT_CONTENT_FORMATS,
    CONTENT_STATUS_TRANSITIONS, EDITABLE_CONTENT_STATUSES,
    PUBLICATION_DATE_REQUIRED_STATUSES,
)
from campaignflow.content.enums import ContentStatus
from campaignflow.content.models import (
    ContentItem, ContentStatusHistory, ContentPlatform, ContentFormat,
)
from campaignflow.content.permissions import ContentPermission
from campaignflow.content.selectors import (
    ContentSelector, ContentPlatformSelector, ContentFormatSelector,
)


def validate_content_model(instance):
    try:
        instance.full_clean()
    except DjangoValidationError as exc:
        raise ValidationError(
            exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        ) from exc


class ContentDefaultsService:

    @staticmethod
    @transaction.atomic
    def initialize_workspace(*, workspace):
        for code, name in DEFAULT_CONTENT_PLATFORMS.items():
            ContentPlatform.objects.get_or_create(
                workspace=workspace, code=code,
                defaults={"name": name, "is_default": True},
            )

        for code, name in DEFAULT_CONTENT_FORMATS.items():
            ContentFormat.objects.get_or_create(
                workspace=workspace, code=code,
                defaults={"name": name, "is_default": True},
            )


class ContentService:
    EDITABLE_FIELDS = {
        "title", "topic", "description", "copy",
        "creative_instructions", "cta", "destination_url",
        "utm_url", "hashtags", "internal_notes", "publication_at",
        "platform_id", "content_format_id", "assignee_id", "related_task_id",
    }

    MEMBER_RESTRICTED_FIELDS = {
        "assignee_id", "related_task_id", "platform_id",
        "content_format_id", "publication_at",
    }

    DUPLICATE_FIELDS = {
        "topic", "description", "copy", "creative_instructions",
        "cta", "destination_url", "hashtags", "internal_notes",
        "platform_id", "content_format_id",
    }

    @staticmethod
    def get_membership(*, workspace_id, user):
        return ContentPermission.get_membership(workspace_id=workspace_id, user=user)

    @staticmethod
    def get_campaign(*, workspace, campaign_id):
        campaign = ContentSelector.get_campaign(workspace=workspace, campaign_id=campaign_id)

        if campaign is None:
            raise NotFound("Campaign not found.")

        return campaign

    @staticmethod
    def get_content_item(*, workspace, content_id, include_archived=False, lock=False):
        if lock:
            content_item = ContentSelector.get_locked_content(
                workspace=workspace, content_id=content_id,
                include_archived=include_archived,
            )
        else:
            content_item = ContentSelector.get_by_id(
                workspace=workspace, content_id=content_id,
                include_archived=include_archived,
            )

        if content_item is None:
            raise NotFound("Content item not found.")

        return content_item

    @classmethod
    def validate_fields(cls, *, data):
        unknown_fields = set(data) - cls.EDITABLE_FIELDS

        if unknown_fields:
            raise ValidationError({
                field: "This field cannot be modified."
                for field in sorted(unknown_fields)
            })

    @staticmethod
    def validate_references(*, workspace, campaign, data):
        cleaned_data = dict(data)
        errors = {}

        if "platform_id" in cleaned_data:
            platform = ContentPlatformSelector.get_by_id(
                workspace=workspace, platform_id=cleaned_data["platform_id"],
            )

            if platform is None:
                errors["platform_id"] = "Invalid workspace platform."

        if "content_format_id" in cleaned_data:
            content_format = ContentFormatSelector.get_by_id(
                workspace=workspace, format_id=cleaned_data["content_format_id"],
            )

            if content_format is None:
                errors["content_format_id"] = "Invalid workspace content format."

        if cleaned_data.get("assignee_id") is not None:
            member = ContentSelector.get_assignable_member(
                workspace=workspace, member_id=cleaned_data["assignee_id"],
            )

            if member is None:
                errors["assignee_id"] = "Invalid content assignee."

        if cleaned_data.get("related_task_id") is not None:
            task = ContentSelector.get_related_task(
                campaign=campaign, task_id=cleaned_data["related_task_id"],
            )

            if task is None:
                errors["related_task_id"] = "Task does not belong to the selected campaign."

        if errors:
            raise ValidationError(errors)

        return cleaned_data

    @staticmethod
    def create_status_history(*, content_item, previous_status, new_status, user, comment=""):
        return ContentStatusHistory.objects.create(
            content_item=content_item,
            previous_status=previous_status,
            new_status=new_status,
            changed_by=user,
            comment=comment,
        )

    @classmethod
    def get_list(cls, *, workspace_id, user, filters=None, campaign_id=None):
        membership = cls.get_membership(workspace_id=workspace_id, user=user)
        ContentPermission.require_view(membership=membership)

        filters = dict(filters or {})
        workspace = membership.workspace

        if campaign_id is not None:
            if filters.get("campaign_id") not in (None, campaign_id):
                raise ValidationError({"campaign_id": "Campaign filter conflicts with the requested campaign."})

            filters["campaign_id"] = campaign_id

        if filters.get("campaign_id") is not None:
            cls.get_campaign(workspace=workspace, campaign_id=filters["campaign_id"])

        if filters.get("is_archived"):
            ContentPermission.require_management(membership=membership)

        return ContentSelector.get_content(workspace=workspace, filters=filters)

    @classmethod
    def get_details(cls, *, workspace_id, content_id, user):
        membership = cls.get_membership(workspace_id=workspace_id, user=user)
        ContentPermission.require_view(membership=membership)

        return cls.get_content_item(
            workspace=membership.workspace, content_id=content_id,
            include_archived=ContentPermission.is_management(membership=membership),
        )

    @classmethod
    @transaction.atomic
    def create(cls, *, workspace_id, campaign_id, user, data):
        membership = cls.get_membership(workspace_id=workspace_id, user=user)
        ContentPermission.require_management(membership=membership)

        workspace = membership.workspace
        campaign = cls.get_campaign(workspace=workspace, campaign_id=campaign_id)

        data = dict(data)
        initial_status = data.pop("status", ContentStatus.DRAFT)

        if initial_status not in {ContentStatus.IDEA, ContentStatus.DRAFT}:
            raise ValidationError({"status": "Content must initially be an idea or draft."})

        cls.validate_fields(data=data)

        required_fields = {"title", "platform_id", "content_format_id"}
        missing_fields = required_fields - set(data)

        if missing_fields:
            raise ValidationError({
                field: "This field is required."
                for field in sorted(missing_fields)
            })

        data = cls.validate_references(workspace=workspace, campaign=campaign, data=data)

        content_item = ContentItem(
            campaign=campaign, created_by=user, updated_by=user,
            status=initial_status, **data,
        )

        validate_content_model(content_item)
        content_item.save()

        cls.create_status_history(
            content_item=content_item, previous_status="",
            new_status=initial_status, user=user,
        )

        return content_item

    @classmethod
    @transaction.atomic
    def update(cls, *, workspace_id, content_id, user, data):
        membership = cls.get_membership(workspace_id=workspace_id, user=user)

        content_item = cls.get_content_item(
            workspace=membership.workspace, content_id=content_id, lock=True,
        )

        ContentPermission.require_edit(membership=membership, content_item=content_item)

        if content_item.status not in EDITABLE_CONTENT_STATUSES:
            raise ValidationError({
                "status": "Move the content to an editable status before modifying it.",
            })

        cls.validate_fields(data=data)

        if not ContentPermission.is_management(membership=membership):
            restricted_fields = set(data) & cls.MEMBER_RESTRICTED_FIELDS

            if restricted_fields:
                raise PermissionDenied("You cannot modify content assignment or publication settings.")

        data = cls.validate_references(
            workspace=membership.workspace, campaign=content_item.campaign, data=data,
        )

        update_fields = []

        for field, value in data.items():
            if getattr(content_item, field) == value:
                continue

            setattr(content_item, field, value)
            update_fields.append(field)

        if not update_fields:
            return content_item

        content_item.updated_by = user

        validate_content_model(content_item)
        content_item.save(update_fields=[*update_fields, "updated_by", "updated_at"])

        return content_item

    @classmethod
    @transaction.atomic
    def change_status(cls, *, workspace_id, content_id, user, new_status, comment=""):
        membership = cls.get_membership(workspace_id=workspace_id, user=user)

        content_item = cls.get_content_item(
            workspace=membership.workspace, content_id=content_id, lock=True,
        )

        ContentPermission.require_status_change(
            membership=membership, content_item=content_item, new_status=new_status,
        )

        previous_status = content_item.status

        if previous_status == new_status:
            return content_item

        allowed_transitions = CONTENT_STATUS_TRANSITIONS.get(previous_status, set())

        if new_status not in allowed_transitions:
            raise ValidationError({
                "status": f"Transition from {previous_status} to {new_status} is not allowed.",
            })

        if new_status in PUBLICATION_DATE_REQUIRED_STATUSES and content_item.publication_at is None:
            raise ValidationError({
                "publication_at": "Publication date is required for this status.",
            })

        content_item.status = new_status
        content_item.updated_by = user

        update_fields = ["status", "updated_by", "updated_at"]

        if new_status == ContentStatus.PUBLISHED:
            content_item.published_at = timezone.now()
            update_fields.append("published_at")

        validate_content_model(content_item)
        content_item.save(update_fields=update_fields)

        cls.create_status_history(
            content_item=content_item, previous_status=previous_status,
            new_status=new_status, user=user, comment=comment,
        )

        return content_item

    @classmethod
    @transaction.atomic
    def archive(cls, *, workspace_id, content_id, user):
        membership = cls.get_membership(workspace_id=workspace_id, user=user)
        ContentPermission.require_management(membership=membership)

        content_item = cls.get_content_item(
            workspace=membership.workspace, content_id=content_id,
            include_archived=True, lock=True,
        )

        if content_item.is_archived:
            return content_item

        content_item.is_archived = True
        content_item.archived_at = timezone.now()
        content_item.updated_by = user

        content_item.save(update_fields=[
            "is_archived", "archived_at", "updated_by", "updated_at",
        ])

        return content_item

    @classmethod
    @transaction.atomic
    def duplicate(cls, *, workspace_id, content_id, user, title=None):
        membership = cls.get_membership(workspace_id=workspace_id, user=user)
        ContentPermission.require_management(membership=membership)

        original = cls.get_content_item(
            workspace=membership.workspace, content_id=content_id, lock=True,
        )

        data = {
            field: deepcopy(getattr(original, field))
            for field in cls.DUPLICATE_FIELDS
        }

        data["title"] = title or f"{original.title[:248]} (Copy)"
        data["status"] = ContentStatus.DRAFT

        return cls.create(
            workspace_id=workspace_id, campaign_id=original.campaign_id,
            user=user, data=data,
        )

    @classmethod
    def get_history(cls, *, workspace_id, content_id, user):
        content_item = cls.get_details(
            workspace_id=workspace_id, content_id=content_id, user=user,
        )

        return ContentSelector.get_status_history(content_item=content_item)

class ContentDefinitionService:
    MODEL_MAP = {
        "platform": ContentPlatform,
        "format": ContentFormat,
    }

    @classmethod
    def get_model(cls, *, definition_type):
        model = cls.MODEL_MAP.get(definition_type)

        if model is None:
            raise ValueError("Unknown content definition type.")

        return model

    @classmethod
    def get_definition(cls, *, workspace, definition_type, definition_id):
        model = cls.get_model(definition_type=definition_type)

        definition = model.objects.filter(id=definition_id, workspace=workspace).first()

        if definition is None:
            raise NotFound("Content definition not found.")

        return definition

    @classmethod
    def get_list(cls, *, workspace_id, user, definition_type):
        membership = ContentPermission.get_membership(workspace_id=workspace_id, user=user)
        ContentPermission.require_view(membership=membership)

        model = cls.get_model(definition_type=definition_type)

        return model.objects.filter(workspace=membership.workspace).order_by("name", "id")

    @classmethod
    @transaction.atomic
    def create(cls, *, workspace_id, user, definition_type, data):
        membership = ContentPermission.get_membership(workspace_id=workspace_id, user=user)
        ContentPermission.require_management(membership=membership)

        model = cls.get_model(definition_type=definition_type)

        definition = model(
            workspace=membership.workspace, code=data["code"].lower(),
            name=data["name"], is_default=False,
        )

        validate_content_model(definition)

        try:
            with transaction.atomic():
                definition.save()
        except IntegrityError as exc:
            raise ValidationError({"code": "This code already exists in the workspace."}) from exc

        return definition

    @classmethod
    @transaction.atomic
    def update(cls, *, workspace_id, user, definition_type, definition_id, data):
        membership = ContentPermission.get_membership(workspace_id=workspace_id, user=user)
        ContentPermission.require_management(membership=membership)

        definition = cls.get_definition(
            workspace=membership.workspace, definition_type=definition_type,
            definition_id=definition_id,
        )

        if definition.is_default:
            raise ValidationError({"definition": "Default definitions cannot be modified."})

        update_fields = []

        for field in ("name", "code"):
            if field not in data:
                continue

            value = data[field].lower() if field == "code" else data[field]

            if getattr(definition, field) != value:
                setattr(definition, field, value)
                update_fields.append(field)

        if not update_fields:
            return definition

        validate_content_model(definition)

        try:
            with transaction.atomic():
                definition.save(update_fields=[*update_fields, "updated_at"])
        except IntegrityError as exc:
            raise ValidationError({"code": "This code already exists in the workspace."}) from exc

        return definition

    @classmethod
    @transaction.atomic
    def delete(cls, *, workspace_id, user, definition_type, definition_id):
        membership = ContentPermission.get_membership(workspace_id=workspace_id, user=user)
        ContentPermission.require_management(membership=membership)

        definition = cls.get_definition(
            workspace=membership.workspace, definition_type=definition_type,
            definition_id=definition_id,
        )

        if definition.is_default:
            raise ValidationError({"definition": "Default definitions cannot be deleted."})

        try:
            with transaction.atomic():
                definition.delete()
        except ProtectedError as exc:
            raise ValidationError({
                "definition": "This definition is already used by existing content.",
            }) from exc