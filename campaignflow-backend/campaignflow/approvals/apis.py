from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from campaignflow.approvals.permissions import TaskApprovalPermission
from campaignflow.approvals.selectors import TaskApprovalSelector
from campaignflow.approvals.services import TaskApprovalService
from campaignflow.core.apis import PrivateApi


class TaskApprovalOutputSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    task_id = serializers.UUIDField()
    requested_by_id = serializers.ReadOnlyField()
    reviewer_id = serializers.UUIDField()
    status = serializers.CharField()
    submission_message = serializers.CharField()
    decision_comment = serializers.CharField()
    decided_by_id = serializers.ReadOnlyField()
    created_at = serializers.DateTimeField()
    decided_at = serializers.DateTimeField(allow_null=True)
    cancelled_at = serializers.DateTimeField(allow_null=True)


class TaskApprovalPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class TaskApprovalListCreateApi(PrivateApi):
    class InputSerializer(serializers.Serializer):
        reviewer_id = serializers.UUIDField()
        submission_message = serializers.CharField(required=False, allow_blank=True, max_length=5000)

    def get(self, request, workspace_id, task_id, *args, **kwargs):
        membership = TaskApprovalPermission.get_membership(workspace_id=workspace_id, user=request.user)
        task = TaskApprovalSelector.get_task(
            workspace=membership.workspace, task_id=task_id, include_archived=True
        )
        if task is None:
            raise NotFound("Task not found.")

        approvals = TaskApprovalSelector.get_approvals(workspace=membership.workspace, task_id=task_id)
        paginator = TaskApprovalPagination()
        page = paginator.paginate_queryset(approvals, request, view=self)
        return paginator.get_paginated_response(TaskApprovalOutputSerializer(page, many=True).data)

    def post(self, request, workspace_id, task_id, *args, **kwargs):
        membership = TaskApprovalPermission.get_membership(workspace_id=workspace_id, user=request.user)
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        approval = TaskApprovalService.submit_for_review(
            workspace=membership.workspace, task_id=task_id,
            requested_by=request.user, membership=membership, **serializer.validated_data,
        )
        return Response(TaskApprovalOutputSerializer(approval).data, status=status.HTTP_201_CREATED)


class TaskApprovalDetailApi(PrivateApi):
    def get(self, request, workspace_id, task_id, approval_id, *args, **kwargs):
        membership = TaskApprovalPermission.get_membership(workspace_id=workspace_id, user=request.user)
        approval = TaskApprovalSelector.get_approval(
            workspace=membership.workspace, task_id=task_id, approval_id=approval_id
        )
        if approval is None:
            raise NotFound("Approval not found.")
        return Response(TaskApprovalOutputSerializer(approval).data)


class TaskApprovalApproveApi(PrivateApi):
    class InputSerializer(serializers.Serializer):
        decision_comment = serializers.CharField(required=False, allow_blank=True, max_length=5000)

    def post(self, request, workspace_id, task_id, approval_id, *args, **kwargs):
        membership = TaskApprovalPermission.get_membership(workspace_id=workspace_id, user=request.user)
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        approval = TaskApprovalService.approve(
            workspace=membership.workspace, task_id=task_id, approval_id=approval_id,
            user=request.user, membership=membership, **serializer.validated_data,
        )
        return Response(TaskApprovalOutputSerializer(approval).data)


class TaskApprovalRequestChangesApi(PrivateApi):
    class InputSerializer(serializers.Serializer):
        decision_comment = serializers.CharField(allow_blank=False, max_length=5000)

    def post(self, request, workspace_id, task_id, approval_id, *args, **kwargs):
        membership = TaskApprovalPermission.get_membership(workspace_id=workspace_id, user=request.user)
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        approval = TaskApprovalService.request_changes(
            workspace=membership.workspace, task_id=task_id, approval_id=approval_id,
            user=request.user, membership=membership, **serializer.validated_data,
        )
        return Response(TaskApprovalOutputSerializer(approval).data)


class TaskApprovalCancelApi(PrivateApi):
    class InputSerializer(serializers.Serializer):
        reason = serializers.CharField(required=False, allow_blank=True, max_length=5000)

    def post(self, request, workspace_id, task_id, approval_id, *args, **kwargs):
        membership = TaskApprovalPermission.get_membership(workspace_id=workspace_id, user=request.user)
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        approval = TaskApprovalService.cancel(
            workspace=membership.workspace, task_id=task_id, approval_id=approval_id,
            user=request.user, membership=membership, **serializer.validated_data,
        )
        return Response(TaskApprovalOutputSerializer(approval).data)


class TaskApprovalPendingApi(PrivateApi):
    def get(self, request, workspace_id, *args, **kwargs):
        membership = TaskApprovalPermission.get_membership(workspace_id=workspace_id, user=request.user)
        approvals = TaskApprovalSelector.get_pending_for_user(
            workspace=membership.workspace, user=request.user
        )
        paginator = TaskApprovalPagination()
        page = paginator.paginate_queryset(approvals, request, view=self)
        return paginator.get_paginated_response(TaskApprovalOutputSerializer(page, many=True).data)
