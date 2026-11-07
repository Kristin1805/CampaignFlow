
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from campaignflow.organization.models import WorkspaceMember
from campaignflow.tasks.models import Task
from campaignflow.tasks.selectors import TaskSelector


class TaskService:
    @staticmethod
    def validate_assignee(*, workspace, assignee_id):
        if assignee_id is None:
            return None

        member = WorkspaceMember.objects.filter(
            id=assignee_id, workspace=workspace,
        ).first()

        if member is None:
            raise ValidationError({"assignee_id": "Workspace member not found."})

        return member

    @staticmethod
    def validate_task(task):
        try:
            task.full_clean()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)

    @classmethod
    @transaction.atomic
    def create_task(cls, *, workspace, campaign, data):
        if campaign.workspace_id != workspace.id:
            raise NotFound("Campaign not found.")

        data = data.copy()
        assignee_id = data.pop("assignee_id", None)
        assignee = cls.validate_assignee(workspace=workspace, assignee_id=assignee_id)

        task = Task(campaign=campaign, assignee=assignee, **data)
        cls.validate_task(task)
        task.save()

        return task

    @classmethod
    @transaction.atomic
    def update_task(cls, *, workspace, task_id, data):
        task = Task.objects.select_for_update().filter(
            id=task_id, campaign__workspace=workspace,
        ).first()

        if task is None:
            raise NotFound("Task not found.")

        data = data.copy()

        if "assignee_id" in data:
            assignee_id = data.pop("assignee_id")
            task.assignee = cls.validate_assignee(workspace=workspace, assignee_id=assignee_id)

        for field, value in data.items():
            setattr(task, field, value)

        cls.validate_task(task)
        task.save()

        return task

    @staticmethod
    @transaction.atomic
    def delete_task(*, workspace, task_id):
        task = Task.objects.select_for_update().filter(
            id=task_id, campaign__workspace=workspace,
        ).first()

        if task is None:
            raise NotFound("Task not found.")

        task.delete()
