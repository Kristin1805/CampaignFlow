from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from campaignflow.campaigns.models import Campaign
from campaignflow.core.apis import PrivateApi
from campaignflow.organization.models import WorkspaceMember
from campaignflow.organization.selectors import WorkspaceSelector
from campaignflow.tasks.enums import TaskPriority, TaskStatus
from campaignflow.tasks.permissions import TaskDependencyPermission, TaskStatusPermission, TaskCommentPermission
from campaignflow.tasks.selectors import (
    TaskSelector, TaskDependencySelector, TaskStatusSelector,
    TaskCommentSelector, TaskActivitySelector,
)
from campaignflow.tasks.services import (
    TaskService, TaskDependencyService, TaskStatusService, TaskCommentService,
)


class TaskOutputSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    campaign_id = serializers.UUIDField()
    assignee_id = serializers.UUIDField(allow_null=True)
    required_skill_id = serializers.UUIDField(allow_null=True)
    required_skill_code = serializers.CharField(source="required_skill.code", read_only=True, allow_null=True)
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
    required_skill_id = serializers.UUIDField(required=False, allow_null=True)
    priority = serializers.ChoiceField(choices=TaskPriority.choices, required=False)
    estimated_hours = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    actual_hours = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False)
    planned_start = serializers.DateField(required=False, allow_null=True)
    planned_end = serializers.DateField(required=False, allow_null=True)
    due_at = serializers.DateTimeField(required=False, allow_null=True)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected an object.")

        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({
                field: "This field cannot be updated here." for field in sorted(unknown)
            })
        return super().to_internal_value(data)


class TaskListQuerySerializer(serializers.Serializer):
    skill = serializers.CharField(required=False, allow_blank=False, max_length=100)


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

        campaign = Campaign.objects.filter(id=campaign_id, workspace=membership.workspace).first()
        if campaign is None:
            raise NotFound("Campaign not found.")

        serializer = TaskListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        tasks = TaskSelector.get_campaign_tasks(workspace=membership.workspace, campaign_id=campaign_id)
        if "skill" in serializer.validated_data:
            tasks = tasks.filter(required_skill__code=serializer.validated_data["skill"])
        return Response(TaskOutputSerializer(tasks, many=True).data)

    def post(self, request, workspace_id, campaign_id, *args, **kwargs):
        membership = TaskApiPermission.get_membership(workspace_id=workspace_id, user=request.user)
        TaskApiPermission.require_management(membership)

        campaign = Campaign.objects.filter(
            id=campaign_id, workspace=membership.workspace, is_archived=False
        ).first()
        if campaign is None:
            raise NotFound("Campaign not found.")

        serializer = TaskInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not serializer.validated_data.get("title"):
            raise serializers.ValidationError({"title": "This field is required."})

        task = TaskService.create_task(
            workspace=membership.workspace, campaign=campaign,
            data=serializer.validated_data, actor=request.user,
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
            workspace=membership.workspace, task_id=task_id,
            data=serializer.validated_data, actor=request.user,
        )

        return Response(TaskOutputSerializer(task).data)

    def delete(self, request, workspace_id, task_id, *args, **kwargs):
        membership = TaskApiPermission.get_membership(workspace_id=workspace_id, user=request.user)
        TaskApiPermission.require_management(membership)

        TaskService.delete_task(workspace=membership.workspace, task_id=task_id, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskDependencyOutputSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    task_id = serializers.UUIDField()
    depends_on_task_id = serializers.UUIDField()
    lag_hours = serializers.DecimalField(max_digits=10, decimal_places=2)
    created_at = serializers.DateTimeField()


class TaskDependencyListCreateApi(PrivateApi):
    class InputSerializer(serializers.Serializer):
        depends_on_task_id = serializers.UUIDField()
        lag_hours = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, required=False, default=0)

    def get(self, request, workspace_id, task_id, *args, **kwargs):
        membership = TaskDependencyPermission.get_membership(workspace_id=workspace_id, user=request.user)
        task = TaskDependencySelector.get_task(workspace=membership.workspace, task_id=task_id)
        if task is None:
            raise NotFound("Task not found.")

        dependencies = TaskDependencySelector.get_dependencies(workspace=membership.workspace, task_id=task_id)
        dependents = TaskDependencySelector.get_dependents(workspace=membership.workspace, task_id=task_id)

        return Response({
            "task_id": str(task.id),
            "dependencies": TaskDependencyOutputSerializer(dependencies, many=True).data,
            "dependents": TaskDependencyOutputSerializer(dependents, many=True).data,
        })

    def post(self, request, workspace_id, task_id, *args, **kwargs):
        membership = TaskDependencyPermission.get_membership(workspace_id=workspace_id, user=request.user)
        TaskDependencyPermission.require_management(membership=membership)

        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dependency = TaskDependencyService.create_dependency(
            workspace=membership.workspace, task_id=task_id,
            actor=request.user, **serializer.validated_data,
        )
        return Response(TaskDependencyOutputSerializer(dependency).data, status=status.HTTP_201_CREATED)


class TaskDependencyDeleteApi(PrivateApi):
    def delete(self, request, workspace_id, task_id, dependency_id, *args, **kwargs):
        membership = TaskDependencyPermission.get_membership(workspace_id=workspace_id, user=request.user)
        TaskDependencyPermission.require_management(membership=membership)

        TaskDependencyService.delete_dependency(
            workspace=membership.workspace, task_id=task_id,
            dependency_id=dependency_id, actor=request.user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskStatusHistoryOutputSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    task_id = serializers.UUIDField()
    previous_status = serializers.CharField()
    new_status = serializers.CharField()
    changed_by_id = serializers.UUIDField()
    created_at = serializers.DateTimeField()


class TaskStatusUpdateApi(PrivateApi):
    class InputSerializer(serializers.Serializer):
        status = serializers.ChoiceField(choices=TaskStatus.choices)

    def patch(self, request, workspace_id, task_id, *args, **kwargs):
        membership = TaskStatusPermission.get_membership(workspace_id=workspace_id, user=request.user)
        TaskStatusPermission.require_status_update(membership=membership)

        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        task = TaskStatusService.change_status(workspace=membership.workspace, task_id=task_id, new_status=serializer.validated_data["status"], changed_by=request.user,)

        return Response({
            "id": str(task.id),
            "status": task.status,
            "updated_at": task.updated_at,
        }, status=status.HTTP_200_OK)


class TaskStatusHistoryApi(PrivateApi):
    def get(self, request, workspace_id, task_id, *args, **kwargs):
        membership = TaskStatusPermission.get_membership(workspace_id=workspace_id, user=request.user)
        task = TaskStatusSelector.get_task(workspace=membership.workspace, task_id=task_id)
        if task is None:
            raise NotFound("Task not found.")

        history = TaskStatusSelector.get_status_history(workspace=membership.workspace, task_id=task_id)
        return Response({
            "task_id": str(task.id),
            "history": TaskStatusHistoryOutputSerializer(history, many=True).data,
        }, status=status.HTTP_200_OK)


class TaskCommentOutputSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    task_id = serializers.UUIDField()
    author_id = serializers.UUIDField()
    content = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class TaskActivityOutputSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    task_id = serializers.UUIDField()
    actor_id = serializers.UUIDField()
    action = serializers.CharField()
    metadata = serializers.JSONField()
    created_at = serializers.DateTimeField()


class TaskCommentPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class TaskCommentListCreateApi(PrivateApi):
    class InputSerializer(serializers.Serializer):
        content = serializers.CharField(max_length=5000, allow_blank=False, trim_whitespace=True)

    def get(self, request, workspace_id, task_id, *args, **kwargs):
        membership = TaskCommentPermission.get_membership(workspace_id=workspace_id, user=request.user)
        task = TaskCommentSelector.get_task(
            workspace=membership.workspace, task_id=task_id, include_archived=True
        )
        if task is None:
            raise NotFound("Task not found.")

        comments = TaskCommentSelector.get_comments(workspace=membership.workspace, task_id=task_id)
        paginator = TaskCommentPagination()
        page = paginator.paginate_queryset(comments, request, view=self)
        return paginator.get_paginated_response(TaskCommentOutputSerializer(page, many=True).data)

    def post(self, request, workspace_id, task_id, *args, **kwargs):
        membership = TaskCommentPermission.get_membership(workspace_id=workspace_id, user=request.user)
        TaskCommentPermission.require_comment_access(membership=membership)

        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        comment = TaskCommentService.create_comment(
            workspace=membership.workspace, task_id=task_id,
            author=request.user, content=serializer.validated_data["content"],
        )
        return Response(TaskCommentOutputSerializer(comment).data, status=status.HTTP_201_CREATED)


class TaskCommentDetailApi(PrivateApi):
    class InputSerializer(serializers.Serializer):
        content = serializers.CharField(max_length=5000, allow_blank=False, trim_whitespace=True)

    def patch(self, request, workspace_id, task_id, comment_id, *args, **kwargs):
        membership = TaskCommentPermission.get_membership(workspace_id=workspace_id, user=request.user)
        TaskCommentPermission.require_comment_access(membership=membership)

        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        comment = TaskCommentService.update_comment(
            workspace=membership.workspace, task_id=task_id, comment_id=comment_id,
            user=request.user, membership=membership, content=serializer.validated_data["content"],
        )
        return Response(TaskCommentOutputSerializer(comment).data)

    def delete(self, request, workspace_id, task_id, comment_id, *args, **kwargs):
        membership = TaskCommentPermission.get_membership(workspace_id=workspace_id, user=request.user)
        TaskCommentPermission.require_comment_access(membership=membership)

        TaskCommentService.delete_comment(
            workspace=membership.workspace, task_id=task_id,
            comment_id=comment_id, user=request.user, membership=membership,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskActivityListApi(PrivateApi):
    def get(self, request, workspace_id, task_id, *args, **kwargs):
        membership = TaskCommentPermission.get_membership(workspace_id=workspace_id, user=request.user)
        task = TaskCommentSelector.get_task(
            workspace=membership.workspace, task_id=task_id, include_archived=True
        )
        if task is None:
            raise NotFound("Task not found.")

        activities = TaskActivitySelector.get_activities(workspace=membership.workspace, task_id=task_id)
        paginator = TaskCommentPagination()
        page = paginator.paginate_queryset(activities, request, view=self)
        return paginator.get_paginated_response(TaskActivityOutputSerializer(page, many=True).data)
