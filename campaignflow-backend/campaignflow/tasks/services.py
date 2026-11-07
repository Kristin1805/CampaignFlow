
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from campaignflow.campaigns.models import Campaign
from campaignflow.organization.models import WorkspaceMember
from campaignflow.tasks.models import Task, TaskDependency
from campaignflow.tasks.selectors import TaskSelector, TaskDependencySelector


class TaskService:
    @staticmethod
    def validate_assignee(*, workspace, assignee_id):
        if assignee_id is None:
            return None

        member = WorkspaceMember.objects.filter(id=assignee_id, workspace=workspace,).first()

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
        task = Task.objects.select_for_update().filter(id=task_id, campaign__workspace=workspace,).first()

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
        task = Task.objects.select_for_update().filter(id=task_id, campaign__workspace=workspace,).first()

        if task is None:
            raise NotFound("Task not found.")

        task.delete()


class TaskDependencyService:
    @staticmethod
    def creates_cycle(*, graph, task_id, depends_on_task_id):
        adjacency = {}
        for source, target in graph:
            adjacency.setdefault(source, set()).add(target)

        stack = [depends_on_task_id]
        visited = set()

        while stack:
            current = stack.pop()
            if current == task_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            stack.extend(adjacency.get(current, set()) - visited)

        return False

    @classmethod
    @transaction.atomic
    def create_dependency(cls, *, workspace, task_id, depends_on_task_id, lag_hours=0):
        task = TaskDependencySelector.get_task(workspace=workspace, task_id=task_id)
        if task is None:
            raise NotFound("Task not found.")

        if task_id == depends_on_task_id:
            raise ValidationError({"depends_on_task_id": "A task cannot depend on itself."})

        depends_on_task = TaskDependencySelector.get_task(workspace=workspace, task_id=depends_on_task_id)
        if depends_on_task is None:
            raise NotFound("Dependency task not found.")
        if task.campaign_id != depends_on_task.campaign_id:
            raise ValidationError({"depends_on_task_id": "Tasks must belong to the same campaign."})

        Campaign.objects.select_for_update().get(
            id=task.campaign_id, workspace=workspace, is_archived=False
        )

        if TaskDependency.objects.filter(task_id=task_id, depends_on_task_id=depends_on_task_id).exists():
            raise ValidationError({"depends_on_task_id": "This dependency already exists."})

        graph = TaskDependencySelector.get_campaign_graph(campaign_id=task.campaign_id)
        if cls.creates_cycle(graph=graph, task_id=task_id, depends_on_task_id=depends_on_task_id):
            raise ValidationError({"depends_on_task_id": "Circular dependency detected."})

        dependency = TaskDependency(task=task, depends_on_task=depends_on_task, lag_hours=lag_hours)
        try:
            dependency.full_clean()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)

        dependency.save()
        return dependency

    @staticmethod
    @transaction.atomic
    def delete_dependency(*, workspace, task_id, dependency_id):
        dependency = TaskDependencySelector.get_dependency(workspace=workspace, task_id=task_id, dependency_id=dependency_id)
        if dependency is None:
            raise NotFound("Dependency not found.")

        Campaign.objects.select_for_update().get(id=dependency.task.campaign_id, workspace=workspace, is_archived=False)
        dependency.delete()
