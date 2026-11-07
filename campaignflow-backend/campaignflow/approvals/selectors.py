from campaignflow.approvals.models import TaskApproval, ApprovalStatus
from campaignflow.tasks.models import Task


class TaskApprovalSelector:
    @staticmethod
    def get_task(*, workspace, task_id, include_archived=False, for_update=False):
        queryset = Task.objects.filter(id=task_id, campaign__workspace=workspace)
        if not include_archived:
            queryset = queryset.filter(campaign__is_archived=False)
        if for_update:
            queryset = queryset.select_for_update()
        return queryset.first()

    @staticmethod
    def get_approvals(*, workspace, task_id):
        return TaskApproval.objects.filter(task_id=task_id, task__campaign__workspace=workspace
        ).select_related("requested_by", "reviewer__user", "decided_by").order_by("-created_at", "-id")

    @staticmethod
    def get_approval(*, workspace, task_id, approval_id):
        return TaskApproval.objects.filter(id=approval_id, task_id=task_id, task__campaign__workspace=workspace
        ).select_related("requested_by", "reviewer__user", "decided_by").first()

    @staticmethod
    def get_pending_approval(*, task):
        return TaskApproval.objects.filter(task=task, status=ApprovalStatus.PENDING).first()

    @staticmethod
    def get_pending_for_user(*, workspace, user, all_reviews=False):
        queryset = TaskApproval.objects.filter(
            task__campaign__workspace=workspace,
            task__campaign__is_archived=False,
            status=ApprovalStatus.PENDING,
        )
        if not all_reviews:
            queryset = queryset.filter(reviewer__user=user)
        return queryset.select_related(
            "task", "requested_by", "reviewer__user"
        ).order_by("-created_at", "-id")
