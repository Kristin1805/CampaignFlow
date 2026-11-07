
from campaignflow.documents.models import TaskAttachment
from campaignflow.tasks.models import Task


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
