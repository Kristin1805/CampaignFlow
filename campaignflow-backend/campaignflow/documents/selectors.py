from campaignflow.documents.models import TaskAttachment
from campaignflow.tasks.models import Task
from django.db.models import Q
from rest_framework.exceptions import NotFound

from campaignflow.documents.constants import TEMPLATE_ORDERING_FIELDS
from campaignflow.documents.enums import DocumentTemplateStatus
from campaignflow.campaigns.models import Campaign
from campaignflow.documents.models import (
    Document,
    DocumentTemplate,
    DocumentTemplateVersion,
)
from campaignflow.organization.models import WorkspaceMember


class TaskAttachmentSelector:
    @staticmethod
    def get_task(*, workspace, task_id, include_archived=False):
        queryset = Task.objects.filter(id=task_id, campaign__workspace=workspace)
        if not include_archived:
            queryset = queryset.filter(campaign__is_archived=False)
        return queryset.select_related("campaign").first()

    @staticmethod
    def get_attachments(*, workspace, task_id):
        return TaskAttachment.objects.filter(
            task_id=task_id, task__campaign__workspace=workspace, is_deleted=False
        ).select_related("uploaded_by").order_by("-created_at", "-id")

    @staticmethod
    def get_attachment(*, workspace, task_id, attachment_id, for_update=False):
        queryset = TaskAttachment.objects.filter(
            id=attachment_id, task_id=task_id, task__campaign__workspace=workspace, is_deleted=False
        ).select_related("task__campaign", "uploaded_by")
        if for_update:
            queryset = queryset.select_for_update()
        return queryset.first()


class DocumentTemplateSelector:

    @staticmethod
    def get_base_queryset(*, workspace):
        return DocumentTemplate.objects.filter(workspace=workspace)

    @classmethod
    def get_templates(cls, *, workspace, filters=None, is_management=False):
        filters = filters or {}
        queryset = cls.get_base_queryset(workspace=workspace)

        if not is_management:
            queryset = queryset.filter(is_archived=False, latest_version__gt=0)

        else:
            queryset = queryset.filter(
                is_archived=filters.get("is_archived", False),
            )

        if filters.get("category"):
            queryset = queryset.filter(category=filters["category"])

        if filters.get("is_system") is not None:
            queryset = queryset.filter(is_system=filters["is_system"])

        status = filters.get("status")

        if status == DocumentTemplateStatus.DRAFT:
            queryset = queryset.filter(is_archived=False, latest_version=0)

        elif status == DocumentTemplateStatus.PUBLISHED:
            queryset = queryset.filter(is_archived=False, latest_version__gt=0)

        elif status == DocumentTemplateStatus.ARCHIVED:
            queryset = queryset.filter(is_archived=True)

        search = filters.get("search")

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(code__icontains=search)
            )

        ordering = filters.get("ordering", "name")

        if ordering not in TEMPLATE_ORDERING_FIELDS:
            ordering = "name"

        return queryset.defer("draft_structure").order_by(ordering, "id")

    @classmethod
    def get_by_id(cls, *, workspace, template_id, include_archived=False, lock=False):
        queryset = cls.get_base_queryset(workspace=workspace)

        if lock:
            queryset = queryset.select_for_update()

        if not include_archived:
            queryset = queryset.filter(is_archived=False)

        template = queryset.filter(id=template_id).first()

        if template is None:
            raise NotFound("Document template not found.")

        return template

    @staticmethod
    def get_versions(*, template):
        return DocumentTemplateVersion.objects.filter(
            template=template,
        ).select_related("published_by").defer("structure").order_by("-version")

    @staticmethod
    def get_version(*, template, version_id):
        version = DocumentTemplateVersion.objects.filter(
            template=template, id=version_id,
        ).select_related("published_by").first()

        if version is None:
            raise NotFound("Document template version not found.")

        return version

    @staticmethod
    def get_latest_version(*, template):
        return DocumentTemplateVersion.objects.filter(
            template=template, version=template.latest_version,
        ).select_related("published_by").first()


class DocumentSelector:

    ORDERING_FIELDS = {
        "title", "-title",
        "created_at", "-created_at",
        "updated_at", "-updated_at",
        "status", "-status",
        "category", "-category",
    }

    @staticmethod
    def get_campaign(*, workspace, campaign_id, lock=False):
        queryset = Campaign.objects.filter(
            id=campaign_id,
            workspace=workspace,
            is_archived=False,
        )

        if lock:
            queryset = queryset.select_for_update()

        return queryset.select_related("workspace").first()

    @staticmethod
    def get_base_queryset(*, workspace):
        return Document.objects.filter(
            campaign__workspace=workspace,
            campaign__is_archived=False,
        ).select_related(
            "campaign",
            "campaign__workspace",
            "template_version",
            "template_version__template",
            "owner",
            "owner__user",
            "created_by",
            "updated_by",
        )

    @classmethod
    def get_by_id(cls, *, workspace, document_id, include_archived=False, lock=False):
        queryset = cls.get_base_queryset(workspace=workspace).filter(
            id=document_id,
        )

        if not include_archived:
            queryset = queryset.filter(is_archived=False)

        if lock:
            queryset = queryset.select_for_update(of=("self",))

        return queryset.first()

    @classmethod
    def get_documents(cls, *, workspace, filters=None):
        filters = filters or {}

        queryset = cls.get_base_queryset(workspace=workspace).filter(
            is_archived=filters.get("is_archived", False),
        )

        filter_fields = {
            "campaign_id": "campaign_id",
            "template_id": "template_version__template_id",
            "category": "category",
            "status": "status",
            "owner_id": "owner_id",
        }

        for key, field in filter_fields.items():
            if filters.get(key) is not None:
                queryset = queryset.filter(**{field: filters[key]})

        if filters.get("search"):
            search = filters["search"]

            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
            )

        if filters.get("period_start"):
            queryset = queryset.filter(
                period_end__gte=filters["period_start"],
            )

        if filters.get("period_end"):
            queryset = queryset.filter(
                period_start__lte=filters["period_end"],
            )

        if filters.get("created_from"):
            queryset = queryset.filter(
                created_at__date__gte=filters["created_from"],
            )

        if filters.get("created_to"):
            queryset = queryset.filter(
                created_at__date__lte=filters["created_to"],
            )

        ordering = filters.get("ordering", "-created_at")

        if ordering not in cls.ORDERING_FIELDS:
            ordering = "-created_at"

        return queryset.order_by(ordering, "id")

    @staticmethod
    def get_published_version(
        *, workspace, template_id, version_id=None, lock=False,
    ):
        templates = DocumentTemplate.objects.filter(
            id=template_id,
            workspace=workspace,
            is_archived=False,
            latest_version__gt=0,
        )

        if lock:
            templates = templates.select_for_update()

        template = templates.first()

        if template is None:
            return None

        versions = DocumentTemplateVersion.objects.filter(
            template=template,
        ).select_related("template")

        if version_id is not None:
            return versions.filter(id=version_id).first()

        return versions.filter(version=template.latest_version).first()

    @staticmethod
    def get_eligible_owner(*, workspace, owner_id):
        return WorkspaceMember.objects.filter(
            id=owner_id,
            workspace=workspace,
            user__is_active=True,
        ).exclude(
            role=WorkspaceMember.Role.GUEST,
        ).select_related("user").first()