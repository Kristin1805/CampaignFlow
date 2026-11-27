from zoneinfo import ZoneInfo

from rest_framework.exceptions import ValidationError

from campaignflow.content.models import ContentItem
from campaignflow.documents.constants import MAX_DOCUMENT_TABLE_ROWS
from campaignflow.documents.placeholders import DocumentPlaceholderRegistry
from campaignflow.organization.models import WorkspaceMember
from campaignflow.tasks.models import Task


class DocumentPlaceholderResolver:

    def __init__(self, *, campaign):
        self.campaign = campaign
        self.workspace = campaign.workspace
        self.timezone = ZoneInfo(self.workspace.timezone)
        self.cache = {}

        self.resolvers = {
            "workspace.name": lambda: self.workspace.name,
            "campaign.name": lambda: self.campaign.name,
            "campaign.description": lambda: self.campaign.description,
            "campaign.objectives": lambda: self.campaign.goal,
            "campaign.start_date": self.get_start_date,
            "campaign.launch_date": self.get_launch_date,
            "campaign.team_members": self.get_team_members,
            "campaign.tasks": self.get_tasks,
            "campaign.publications": self.get_publications,
        }

    @staticmethod
    def serialize_date(value):
        return value.isoformat() if value is not None else None

    def serialize_datetime(self, value):
        if value is None:
            return None

        return value.astimezone(self.timezone).isoformat()

    @staticmethod
    def get_member_name(member):
        if member is None:
            return None

        return member.user.get_full_name() or member.user.email

    @staticmethod
    def get_limited_items(queryset):
        items = list(queryset[:MAX_DOCUMENT_TABLE_ROWS + 1])

        if len(items) > MAX_DOCUMENT_TABLE_ROWS:
            raise ValidationError({
                "content": "Collection exceeds the maximum allowed table rows.",
            })

        return items

    def get_start_date(self):
        return self.serialize_date(self.campaign.starts_on)

    def get_launch_date(self):
        if self.campaign.launch_at is None:
            return None

        return self.campaign.launch_at.astimezone(
            self.timezone,
        ).date().isoformat()

    def get_team_members(self):
        member_ids = Task.objects.filter(
            campaign=self.campaign,
            assignee_id__isnull=False,
        ).values_list("assignee_id", flat=True)

        queryset = WorkspaceMember.objects.filter(
            workspace=self.workspace,
            id__in=member_ids,
            user__is_active=True,
        ).exclude(
            role=WorkspaceMember.Role.GUEST,
        ).select_related("user").order_by("user__email", "id")

        return [
            {
                "id": str(member.id),
                "name": self.get_member_name(member),
                "email": member.user.email,
                "role": member.role,
                "member": self.get_member_name(member),
                "member_id": str(member.id),
            }
            for member in self.get_limited_items(queryset)
        ]

    def get_tasks(self):
        queryset = Task.objects.filter(
            campaign=self.campaign,
        ).select_related(
            "assignee", "assignee__user", "required_skill",
        ).order_by("created_at", "id")

        return [
            {
                "id": str(task.id),
                "task_id": str(task.id),
                "task": task.title,
                "title": task.title,
                "name": task.title,
                "description": task.description,
                "status": task.status,
                "priority": task.priority,
                "assignee": self.get_member_name(task.assignee),
                "assignee_id": str(task.assignee_id) if task.assignee_id else None,
                "estimated_hours": float(task.estimated_hours),
                "actual_hours": float(task.actual_hours),
                "planned_start": self.serialize_datetime(task.planned_start),
                "planned_end": self.serialize_datetime(task.planned_end),
                "due_at": self.serialize_datetime(task.due_at),
                "deadline": (
                    task.due_at.astimezone(self.timezone).date().isoformat()
                    if task.due_at else None
                ),
                "is_critical": task.is_critical,
                "required_skill": (
                    task.required_skill.name if task.required_skill else None
                ),
            }
            for task in self.get_limited_items(queryset)
        ]

    def get_publications(self):
        queryset = ContentItem.objects.filter(
            campaign=self.campaign,
            is_archived=False,
        ).select_related(
            "platform", "content_format", "assignee", "assignee__user",
        ).order_by("publication_at", "id")

        return [
            {
                "id": str(item.id),
                "content_id": str(item.id),
                "title": item.title,
                "topic": item.topic,
                "description": item.description,
                "platform": item.platform.name,
                "format": item.content_format.name,
                "content_format": item.content_format.name,
                "status": item.status,
                "copy": item.copy,
                "caption": item.copy,
                "cta": item.cta,
                "destination_url": item.destination_url,
                "creative_instructions": item.creative_instructions,
                "publication_at": self.serialize_datetime(item.publication_at),
                "publication_date": (
                    item.publication_at.astimezone(self.timezone).date().isoformat()
                    if item.publication_at else None
                ),
                "published_at": self.serialize_datetime(item.published_at),
                "assignee": self.get_member_name(item.assignee),
                "assignee_id": str(item.assignee_id) if item.assignee_id else None,
            }
            for item in self.get_limited_items(queryset)
        ]

    def resolve(self, *, key):
        if not DocumentPlaceholderRegistry.exists(key=key):
            raise ValidationError({
                "placeholder": f"Unsupported placeholder: {key}",
            })

        if key not in self.resolvers:
            raise ValidationError({
                "placeholder": f"Missing resolver for: {key}",
            })

        if key not in self.cache:
            self.cache[key] = self.resolvers[key]()

        return self.cache[key]