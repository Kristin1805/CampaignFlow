
from datetime import date
from decimal import Decimal

from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from campaignflow.tasks.enums import TaskStatus
from campaignflow.tasks.models import Task, TaskDependency, TaskStatusHistory, TaskComment, TaskActivity


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


class TaskDependencySelector:
    @staticmethod
    def get_task(*, workspace, task_id):
        return Task.objects.select_related("campaign").filter(
            id=task_id, campaign__workspace=workspace, campaign__is_archived=False
        ).first()

    @staticmethod
    def get_dependencies(*, workspace, task_id):
        return TaskDependency.objects.filter(task_id=task_id, task__campaign__workspace=workspace, task__campaign__is_archived=False
        ).select_related("task", "depends_on_task").order_by("created_at", "id")

    @staticmethod
    def get_dependents(*, workspace, task_id):
        return TaskDependency.objects.filter(
            depends_on_task_id=task_id, task__campaign__workspace=workspace,
            task__campaign__is_archived=False
        ).select_related("task", "depends_on_task").order_by("created_at", "id")

    @staticmethod
    def get_dependency(*, workspace, task_id, dependency_id):
        return TaskDependency.objects.filter(
            id=dependency_id, task_id=task_id,
            task__campaign__workspace=workspace, task__campaign__is_archived=False
        ).select_related("task").first()

    @staticmethod
    def get_campaign_graph(*, campaign_id):
        return list(TaskDependency.objects.filter(task__campaign_id=campaign_id).values_list("task_id", "depends_on_task_id"))


class TaskStatusSelector:
    @staticmethod
    def get_task(*, workspace, task_id, for_update=False):
        queryset = Task.objects.filter(id=task_id, campaign__workspace=workspace, campaign__is_archived=False
        ).select_related("campaign", "assignee")

        if for_update:
            queryset = queryset.select_for_update()

        return queryset.first()

    @staticmethod
    def get_status_history(*, workspace, task_id):
        return TaskStatusHistory.objects.filter(task_id=task_id, task__campaign__workspace=workspace).select_related("changed_by").order_by("created_at", "id")

    @staticmethod
    def get_incomplete_dependencies(*, task):
        return TaskDependency.objects.filter(task=task).exclude(depends_on_task__status=TaskStatus.COMPLETED).select_related("depends_on_task").order_by("created_at", "id")



class TaskCommentSelector:
    @staticmethod
    def get_task(*, workspace, task_id, include_archived=False):
        queryset = Task.objects.filter(id=task_id, campaign__workspace=workspace)
        if not include_archived:
            queryset = queryset.filter(campaign__is_archived=False)
        return queryset.select_related("campaign").first()

    @staticmethod
    def get_comments(*, workspace, task_id):
        return TaskComment.objects.filter(
            task_id=task_id, task__campaign__workspace=workspace, is_deleted=False
        ).select_related("author").order_by("created_at", "id")

    @staticmethod
    def get_comment(*, workspace, task_id, comment_id, for_update=False):
        queryset = TaskComment.objects.filter(
            id=comment_id, task_id=task_id, task__campaign__workspace=workspace, is_deleted=False
        ).select_related("task", "author")
        if for_update:
            queryset = queryset.select_for_update()
        return queryset.first()


class TaskActivitySelector:
    @staticmethod
    def get_activities(*, workspace, task_id):
        return TaskActivity.objects.filter(
            task_id=task_id, task__campaign__workspace=workspace
        ).select_related("actor").order_by("created_at", "id")
