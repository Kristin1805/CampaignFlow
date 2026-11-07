
from datetime import date
from decimal import Decimal

from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from campaignflow.tasks.enums import TaskStatus
from campaignflow.tasks.models import Task


class TaskSelector:
    @staticmethod
    def get_by_id(*, workspace, task_id):
        return Task.objects.select_related("campaign", "assignee", "assignee__user").filter(
            id=task_id, campaign__workspace=workspace,
        ).first()

    @staticmethod
    def get_campaign_tasks(*, workspace, campaign_id):
        return Task.objects.select_related("campaign", "assignee", "assignee__user").filter(
            campaign_id=campaign_id, campaign__workspace=workspace,
        ).order_by("created_at")

    @staticmethod
    def get_workspace_tasks(*, workspace):
        return Task.objects.select_related("campaign", "assignee", "assignee__user").filter(
            campaign__workspace=workspace,
        ).order_by("created_at")


class TaskWorkloadSelector:
    EXCLUDED_STATUSES = (TaskStatus.COMPLETED, TaskStatus.CANCELLED)

    @classmethod
    def get_active_tasks_queryset(cls, *, workspace, start_date: date, end_date: date, member_ids=None):
        queryset = Task.objects.filter(
            campaign__workspace=workspace,
            assignee__isnull=False,
            planned_start__gte=start_date,
            planned_start__lte=end_date,
        ).exclude(status__in=cls.EXCLUDED_STATUSES)

        if member_ids is not None:
            queryset = queryset.filter(assignee_id__in=member_ids)

        return queryset

    @classmethod
    def get_workspace_task_totals(cls, *, workspace, start_date: date, end_date: date, member_ids=None):
        queryset = cls.get_active_tasks_queryset(
            workspace=workspace,
            start_date=start_date,
            end_date=end_date,
            member_ids=member_ids,
        )

        rows = queryset.values("assignee_id").annotate(
            assigned_hours=Coalesce(
                Sum("estimated_hours"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
            active_tasks_count=Count("id"),
        )

        return {
            row["assignee_id"]: {
                "assigned_hours": row["assigned_hours"],
                "active_tasks_count": row["active_tasks_count"],
            }
            for row in rows
        }
