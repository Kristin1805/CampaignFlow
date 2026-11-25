from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q, F, Count
from django.utils import timezone

from campaignflow.campaigns.models import Campaign
from campaignflow.content.calendar import CalendarPeriod
from campaignflow.content.constants import CALENDAR_TERMINAL_STATUSES, POSTING_PLAN_ORDERING_FIELDS
from campaignflow.content.enums import ContentStatus, PostingPlanView
from campaignflow.content.models import ContentItem, ContentPlatform, ContentFormat, ContentStatusHistory
from campaignflow.organization.models import WorkspaceMember
from campaignflow.tasks.models import Task


class ContentSelector:
    ORDERING_FIELDS = {
        "publication_at", "-publication_at",
        "created_at", "-created_at",
        "updated_at", "-updated_at",
        "title", "-title",
        "status", "-status",
    }

    @staticmethod
    def get_campaign(*, workspace, campaign_id):
        return Campaign.objects.filter(
            id=campaign_id, workspace=workspace, is_archived=False,
        ).select_related("workspace").first()

    @staticmethod
    def get_base_queryset(*, workspace):
        return ContentItem.objects.filter(
            campaign__workspace=workspace, campaign__is_archived=False,
        ).select_related(
            "campaign", "campaign__workspace", "platform", "content_format",
            "assignee", "assignee__user", "related_task", "created_by", "updated_by",
        )

    @classmethod
    def get_by_id(cls, *, workspace, content_id, include_archived=False):
        queryset = cls.get_base_queryset(workspace=workspace).filter(id=content_id)

        if not include_archived:
            queryset = queryset.filter(is_archived=False)

        return queryset.first()

    @classmethod
    def get_content(cls, *, workspace, filters=None):
        filters = filters or {}
        queryset = cls.get_base_queryset(workspace=workspace)

        queryset = queryset.filter(is_archived=filters.get("is_archived", False))

        filter_fields = {
            "campaign_id": "campaign_id",
            "platform_id": "platform_id",
            "content_format_id": "content_format_id",
            "assignee_id": "assignee_id",
            "status": "status",
            "created_by": "created_by_id",
        }

        for key, field in filter_fields.items():
            if filters.get(key) is not None:
                queryset = queryset.filter(**{field: filters[key]})

        if filters.get("search"):
            search = filters["search"]

            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(topic__icontains=search)
                | Q(copy__icontains=search)
                | Q(description__icontains=search)
            )

        tz = ZoneInfo(workspace.timezone)

        if filters.get("date_from"):
            date_from = datetime.combine(filters["date_from"], time.min, tzinfo=tz)
            queryset = queryset.filter(publication_at__gte=date_from)

        if filters.get("date_to"):
            date_to = datetime.combine(
                filters["date_to"] + timedelta(days=1), time.min, tzinfo=tz,
            )
            queryset = queryset.filter(publication_at__lt=date_to)

        ordering = filters.get("ordering", "-created_at")

        if ordering not in cls.ORDERING_FIELDS:
            ordering = "-created_at"

        if ordering == "publication_at":
            return queryset.order_by(F("publication_at").asc(nulls_last=True), "id")

        if ordering == "-publication_at":
            return queryset.order_by(F("publication_at").desc(nulls_last=True), "id")

        return queryset.order_by(ordering, "id")

    @staticmethod
    def get_status_history(*, content_item):
        return ContentStatusHistory.objects.filter(
            content_item=content_item,
        ).select_related("changed_by").order_by("-created_at", "-id")

    @staticmethod
    def get_assignable_member(*, workspace, member_id):
        return WorkspaceMember.objects.filter(
            id=member_id, workspace=workspace, user__is_active=True,
        ).exclude(role=WorkspaceMember.Role.GUEST).select_related("user").first()

    @staticmethod
    def get_related_task(*, campaign, task_id):
        return Task.objects.filter(id=task_id, campaign=campaign).first()

    @staticmethod
    def get_locked_content(*, workspace, content_id, include_archived=False):
        queryset = ContentItem.objects.select_for_update().filter(
            id=content_id,
            campaign__workspace=workspace,
            campaign__is_archived=False,
        )

        if not include_archived:
            queryset = queryset.filter(is_archived=False)

        return queryset.first()


class ContentPlatformSelector:

    @staticmethod
    def get_platforms(*, workspace):
        return ContentPlatform.objects.filter(workspace=workspace).order_by("name", "id")

    @staticmethod
    def get_by_id(*, workspace, platform_id):
        return ContentPlatform.objects.filter(id=platform_id, workspace=workspace).first()


class ContentFormatSelector:

    @staticmethod
    def get_formats(*, workspace):
        return ContentFormat.objects.filter(workspace=workspace).order_by("name", "id")

    @staticmethod
    def get_by_id(*, workspace, format_id):
        return ContentFormat.objects.filter(id=format_id, workspace=workspace).first()

class ContentCalendarSelector:
    FILTER_FIELDS = {
        "campaign_ids": "campaign_id__in",
        "platform_ids": "platform_id__in",
        "format_ids": "content_format_id__in",
        "assignee_ids": "assignee_id__in",
        "statuses": "status__in",
    }

    @classmethod
    def get_filtered_queryset(cls, *, workspace, filters=None):
        filters = filters or {}

        queryset = ContentSelector.get_base_queryset(workspace=workspace).filter(is_archived=False,)

        for key, field in cls.FILTER_FIELDS.items():
            values = filters.get(key)

            if values:
                queryset = queryset.filter(**{field: values})

        search = filters.get("search")

        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(topic__icontains=search)
                | Q(copy__icontains=search)
                | Q(description__icontains=search)
            )

        if filters.get("unassigned_only"):
            queryset = queryset.filter(assignee_id__isnull=True)

        return queryset

    @classmethod
    def get_calendar_events(cls, *, workspace, period, filters=None):
        return cls.get_filtered_queryset(workspace=workspace, filters=filters,).filter(publication_at__gte=period["start_at"], publication_at__lt=period["end_at"],).order_by("publication_at", "id")

    @classmethod
    def get_unscheduled_content(cls, *, workspace, filters=None):
        return cls.get_filtered_queryset(workspace=workspace, filters=filters).filter(publication_at__isnull=True).exclude(status__in=CALENDAR_TERMINAL_STATUSES).order_by("-created_at", "-id")

    @classmethod
    def get_unscheduled_count(cls, *, workspace, filters=None):
        return cls.get_unscheduled_content(workspace=workspace, filters=filters,).count()

    @classmethod
    def get_conflict_candidates(cls, *, workspace, period):
        return cls.get_calendar_events(
            workspace=workspace, period=period,
        ).exclude(status__in=CALENDAR_TERMINAL_STATUSES)

    @staticmethod
    def get_locked_content_items(*, workspace, content_ids):
        return list(
            ContentItem.objects.select_for_update()
            .filter(
                id__in=content_ids,
                campaign__workspace=workspace,
                campaign__is_archived=False,
                is_archived=False,
            )
            .order_by("id")
        )

class PostingPlanSelector:

    @classmethod
    def get_queryset(cls, *, workspace, filters=None):
        filters = filters or {}
        queryset = ContentCalendarSelector.get_filtered_queryset(
            workspace=workspace, filters=filters,
        )

        view = filters.get("view", PostingPlanView.ALL)

        if view == PostingPlanView.UNSCHEDULED:
            queryset = queryset.filter(publication_at__isnull=True)

        elif view != PostingPlanView.ALL:
            period = CalendarPeriod.resolve(
                workspace=workspace,
                view=view,
                reference_date=filters.get("reference_date"),
                date_from=filters.get("date_from"),
                date_to=filters.get("date_to"),
            )

            date_filter = Q(
                publication_at__gte=period["start_at"],
                publication_at__lt=period["end_at"],
            )

            if filters.get("include_unscheduled"):
                date_filter |= Q(publication_at__isnull=True)

            queryset = queryset.filter(date_filter)

        scheduled = filters.get("scheduled")

        if scheduled is not None:
            queryset = queryset.filter(publication_at__isnull=not scheduled)

        published = filters.get("published")

        if published is True:
            queryset = queryset.filter(status=ContentStatus.PUBLISHED)
        elif published is False:
            queryset = queryset.exclude(status=ContentStatus.PUBLISHED)

        if filters.get("overdue_only"):
            queryset = queryset.filter(
                publication_at__lt=timezone.now(),
            ).exclude(status__in=CALENDAR_TERMINAL_STATUSES)

        ordering = filters.get("ordering", "publication_at")
        descending = ordering.startswith("-")
        field = POSTING_PLAN_ORDERING_FIELDS.get(ordering.lstrip("-"), "publication_at")

        expression = F(field).desc(nulls_last=True) if descending else F(field).asc(nulls_last=True)

        return queryset.order_by(expression, "id")

    @staticmethod
    def get_summary(*, queryset):
        now = timezone.now()

        summary = queryset.aggregate(
            total_publications=Count("id"),
            scheduled=Count("id", filter=Q(publication_at__isnull=False)),
            unscheduled=Count("id", filter=Q(publication_at__isnull=True)),
            published=Count("id", filter=Q(status=ContentStatus.PUBLISHED)),
            draft=Count("id", filter=Q(status=ContentStatus.DRAFT)),
            approved=Count("id", filter=Q(status=ContentStatus.APPROVED)),
            in_review=Count("id", filter=Q(status=ContentStatus.IN_REVIEW)),
            unassigned=Count("id", filter=Q(assignee_id__isnull=True)),
            overdue=Count(
                "id",
                filter=Q(publication_at__lt=now)
                & ~Q(status__in=CALENDAR_TERMINAL_STATUSES),
            ),
        )

        summary["by_platform"] = list(
            queryset.order_by().values(
                "platform_id", "platform__name",
            ).annotate(total=Count("id")).order_by("-total", "platform_id")
        )

        summary["by_campaign"] = list(
            queryset.order_by().values(
                "campaign_id", "campaign__name",
            ).annotate(total=Count("id")).order_by("-total", "campaign_id")
        )

        summary["by_status"] = list(
            queryset.order_by().values("status")
            .annotate(total=Count("id")).order_by("-total", "status")
        )

        summary["by_assignee"] = list(
            queryset.order_by().values(
                "assignee_id", "assignee__user__email",
            ).annotate(total=Count("id")).order_by("-total", "assignee_id")
        )

        return summary