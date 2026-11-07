
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from campaignflow.core.apis import PrivateApi
from campaignflow.organization.models import WorkspaceMember
from campaignflow.organization.selectors import WorkspaceSelector
from campaignflow.tasks.enums import TaskPriority, TaskStatus
from campaignflow.tasks.selectors import TaskSelector
from campaignflow.tasks.services import TaskService


class TaskOutputSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    campaign_id = serializers.UUIDField()
    assignee_id = serializers.UUIDField(allow_null=True)
    title = serializers.CharField()
    description = serializers.CharField()
    status = serializers.CharField()
    priority = serializers.CharField()
    estimated_hours = serializers.DecimalField(max_digits=10, decimal_places=2)
    actual_hours = serializers.DecimalField(max_digits=10, decimal_places=2)
    planned_start = serializers.DateField(allow_null=True)
    planned_end = serializers.DateField(allow_null=True)
    due_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class TaskInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    assignee_id = serializers.UUIDField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=TaskStatus.choices, required=False)
    priority = serializers.ChoiceField(choices=TaskPriority.choices, required=False)
    estimated_hours = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    actual_hours = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    planned_start = serializers.DateField(required=False, allow_null=True)
    planned_end = serializers.DateField(required=False, allow_null=True)
    due_at = serializers.DateTimeField(required=False, allow_null=True)


class TaskApiPermission:
    @staticmethod
    def get_membership(*, workspace_id, user):
        membership = WorkspaceSelector.get_membership(workspace_id=workspace_id, user=user)

        if membership is None:
            raise NotFound("Workspace not found.")

        return membership

    @staticmethod
    def require_management(membership):
        if membership.role not in (WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.MANAGER):
            raise PermissionDenied("You cannot manage workspace tasks.")


class CampaignTasksApi(PrivateApi):
    def get(self, request, workspace_id, campaign_id, *args, **kwargs):
        membership = TaskApiPermission.get_membership(workspace_id=workspace_id, user=request.user)

        tasks = TaskSelector.get_campaign_tasks(
            workspace=membership.workspace, campaign_id=campaign_id,
        )

        return Response(TaskOutputSerializer(tasks, many=True).data)

    def post(self, request, workspace_id, campaign_id, *args, **kwargs):
        membership = TaskApiPermission.get_membership(workspace_id=workspace_id, user=request.user)
        TaskApiPermission.require_management(membership)

        from campaignflow.campaigns.models import Campaign

        campaign = Campaign.objects.filter(
            id=campaign_id, workspace=membership.workspace,
        ).first()

        if campaign is None:
            raise NotFound("Campaign not found.")

        serializer = TaskInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not serializer.validated_data.get("title"):
            raise serializers.ValidationError({"title": "This field is required."})

        task = TaskService.create_task(
            workspace=membership.workspace,
            campaign=campaign,
            data=serializer.validated_data,
        )

        return Response(TaskOutputSerializer(task).data, status=status.HTTP_201_CREATED)


class TaskDetailApi(PrivateApi):
    def get(self, request, workspace_id, task_id, *args, **kwargs):
        membership = TaskApiPermission.get_membership(workspace_id=workspace_id, user=request.user)
        task = TaskSelector.get_by_id(workspace=membership.workspace, task_id=task_id)

        if task is None:
            raise NotFound("Task not found.")

        return Response(TaskOutputSerializer(task).data)

    def patch(self, request, workspace_id, task_id, *args, **kwargs):
        membership = TaskApiPermission.get_membership(workspace_id=workspace_id, user=request.user)
        TaskApiPermission.require_management(membership)

        serializer = TaskInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        task = TaskService.update_task(
            workspace=membership.workspace,
            task_id=task_id,
            data=serializer.validated_data,
        )

        return Response(TaskOutputSerializer(task).data)

    def delete(self, request, workspace_id, task_id, *args, **kwargs):
        membership = TaskApiPermission.get_membership(workspace_id=workspace_id, user=request.user)
        TaskApiPermission.require_management(membership)

        TaskService.delete_task(workspace=membership.workspace, task_id=task_id)

        return Response(status=status.HTTP_204_NO_CONTENT)
