from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from campaignflow.tasks.enums import TaskStatus
from campaignflow.tasks.models import (
    Task,
    TaskActivity,
    TaskComment,
    TaskDependency,
    TaskStatusHistory,
)


class TaskSelector:
    @staticmethod
    def get_by_id(*, workspace, task_id):
        return (
            Task.objects.filter(
                id=task_id,
                campaign__workspace=workspace,
                campaign__is_archived=False,
            )
            .select_related(
                "campaign",
                "assignee",
                "assignee__user",
                "required_skill",
            )
            .first()
        )

    @staticmethod
    def get_campaign_tasks(*, workspace, campaign_id):
        return (
            Task.objects.filter(
                campaign_id=campaign_id,
                campaign__workspace=workspace,
                campaign__is_archived=False,
            )
            .select_related(
                "campaign",
                "assignee",
                "assignee__user",
                "required_skill",
            )
            .order_by("created_at", "id")
        )

    @staticmethod
    def get_workspace_tasks(*, workspace):
        return (
            Task.objects.filter(
                campaign__workspace=workspace,
                campaign__is_archived=False,
            )
            .select_related(
                "campaign",
                "assignee",
                "assignee__user",
                "required_skill",
            )
            .order_by("created_at", "id")
        )


class TaskWorkloadSelector:
    EXCLUDED_STATUSES = (
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
    )

    @classmethod
    def get_active_tasks_queryset(
        cls,
        *,
        workspace,
        start_date: date,
        end_date: date,
        member_ids=None,
    ):
        queryset = Task.objects.filter(
            campaign__workspace=workspace,
            campaign__is_archived=False,
            assignee__isnull=False,
            planned_start__date__gte=start_date,
            planned_start__date__lte=end_date,
        ).exclude(
            status__in=cls.EXCLUDED_STATUSES
        )

        if member_ids is not None:
            queryset = queryset.filter(
                assignee_id__in=member_ids
            )

        return queryset

    @classmethod
    def get_workspace_task_totals(
        cls,
        *,
        workspace,
        start_date: date,
        end_date: date,
        member_ids=None,
    ):
        queryset = cls.get_active_tasks_queryset(
            workspace=workspace,
            start_date=start_date,
            end_date=end_date,
            member_ids=member_ids,
        )

        rows = (
            queryset.values("assignee_id")
            .annotate(
                assigned_hours=Coalesce(
                    Sum("estimated_hours"),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(
                        max_digits=12,
                        decimal_places=2,
                    ),
                ),
                active_tasks_count=Count("id"),
            )
        )

        return {
            row["assignee_id"]: {
                "assigned_hours": row["assigned_hours"],
                "active_tasks_count": row["active_tasks_count"],
            }
            for row in rows
        }

    @classmethod
    def get_optimizer_busy_hours(
        cls,
        *,
        workspace,
        campaign,
        start_date: date,
        end_date: date,
        member_ids=None,
    ):
        """
        Estimate the workload already assigned to workspace members
        in other campaigns during the optimization period.

        Completed and cancelled tasks are excluded.

        The optimization period is evaluated using the workspace
        timezone.

        A task is included when its planned interval overlaps
        the requested period.

        Busy hours are based on estimated_hours and do not
        represent exact calendar bookings.
        """
        if start_date > end_date:
            raise ValueError(
                "Start date must be on or before end date."
            )

        workspace_timezone = ZoneInfo(workspace.timezone)

        period_start = datetime.combine(
            start_date,
            time.min,
            tzinfo=workspace_timezone,
        )

        period_end = datetime.combine(
            end_date + timedelta(days=1),
            time.min,
            tzinfo=workspace_timezone,
        )

        queryset = (
            Task.objects.filter(
                campaign__workspace=workspace,
                campaign__is_archived=False,
                assignee__isnull=False,
                planned_start__isnull=False,
                planned_end__isnull=False,
                planned_start__lt=period_end,
                planned_end__gt=period_start,
            )
            .exclude(status__in=cls.EXCLUDED_STATUSES,)
            .exclude(campaign=campaign,)
        )

        if member_ids is not None:
            queryset = queryset.filter(assignee_id__in=member_ids)

        rows = (
            queryset.order_by()
            .values("assignee_id")
            .annotate(
                busy_hours=Coalesce(
                    Sum("estimated_hours"),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(
                        max_digits=12,
                        decimal_places=2,
                    ),
                )
            )
        )

        return {
            row["assignee_id"]: row["busy_hours"]
            for row in rows
        }


class TaskDependencySelector:
    @staticmethod
    def get_task(*, workspace, task_id):
        return Task.objects.filter(
            id=task_id,
            campaign__workspace=workspace,
            campaign__is_archived=False,
        ).first()

    @staticmethod
    def get_dependencies(*, workspace, task_id):
        return (
            TaskDependency.objects.filter(
                task_id=task_id,
                task__campaign__workspace=workspace,
                task__campaign__is_archived=False,
            )
            .select_related(
                "task",
                "depends_on_task",
            )
            .order_by("created_at", "id")
        )

    @staticmethod
    def get_dependents(*, workspace, task_id):
        return (
            TaskDependency.objects.filter(
                depends_on_task_id=task_id,
                depends_on_task__campaign__workspace=workspace,
                depends_on_task__campaign__is_archived=False,
            )
            .select_related(
                "task",
                "depends_on_task",
            )
            .order_by("created_at", "id")
        )

    @staticmethod
    def get_dependency(*, workspace, dependency_id):
        return (
            TaskDependency.objects.filter(
                id=dependency_id,
                task__campaign__workspace=workspace,
                task__campaign__is_archived=False,
            )
            .select_related(
                "task",
                "depends_on_task",
            )
            .first()
        )

    @staticmethod
    def get_campaign_graph(*, workspace, campaign_id):
        return (
            TaskDependency.objects.filter(
                task__campaign_id=campaign_id,
                task__campaign__workspace=workspace,
                task__campaign__is_archived=False,
            )
            .select_related(
                "task",
                "depends_on_task",
            )
            .order_by("created_at", "id")
        )


class TaskStatusSelector:
    @staticmethod
    def get_task(*, workspace, task_id, for_update=False):
        queryset = Task.objects.filter(
            id=task_id,
            campaign__workspace=workspace,
            campaign__is_archived=False,
        )

        if for_update:
            queryset = queryset.select_for_update(of=("self",))

        return queryset.first()

    @staticmethod
    def get_status_history(*, workspace, task_id):
        return (
            TaskStatusHistory.objects.filter(
                task_id=task_id,
                task__campaign__workspace=workspace,
            )
            .select_related("changed_by")
            .order_by("created_at", "id")
        )

    @staticmethod
    def get_incomplete_dependencies(*, task):
        return (
            TaskDependency.objects.filter(
                task=task,
            )
            .exclude(
                depends_on_task__status=TaskStatus.COMPLETED
            )
            .select_related("depends_on_task")
            .order_by("created_at", "id")
        )


class TaskCommentSelector:
    @staticmethod
    def get_task(*, workspace, task_id):
        return (
            Task.objects.filter(
                id=task_id,
                campaign__workspace=workspace,
                campaign__is_archived=False,
            )
            .first()
        )

    @staticmethod
    def get_comments(*, task):
        return (
            TaskComment.objects.filter(task=task)
            .select_related("author")
            .order_by("created_at", "id")
        )

    @staticmethod
    def get_comment(*, task, comment_id):
        return (
            TaskComment.objects.filter(
                task=task,
                comment_id=comment_id,
            )
            .select_related("author")
            .first()
        )


class TaskActivitySelector:
    @staticmethod
    def get_activities(*, task):
        return (
            TaskActivity.objects.filter(task=task)
            .select_related("actor")
            .order_by("-created_at", "-id")
        )
