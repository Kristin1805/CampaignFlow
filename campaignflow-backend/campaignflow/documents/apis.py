from django.http import FileResponse, Http404
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from campaignflow.core.apis import PrivateApi
from campaignflow.documents.permissions import TaskAttachmentPermission
from campaignflow.documents.selectors import TaskAttachmentSelector
from campaignflow.documents.services import TaskAttachmentService


class TaskAttachmentOutputSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    task_id = serializers.UUIDField()
    uploaded_by_id = serializers.UUIDField()
    original_filename = serializers.CharField()
    mime_type = serializers.CharField()
    file_size = serializers.IntegerField()
    created_at = serializers.DateTimeField()


class TaskAttachmentPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class TaskAttachmentListCreateApi(PrivateApi):
    parser_classes = [MultiPartParser, FormParser]

    class InputSerializer(serializers.Serializer):
        file = serializers.FileField(allow_empty_file=False)

    def get(self, request, workspace_id, task_id, *args, **kwargs):
        membership = TaskAttachmentPermission.get_membership(workspace_id=workspace_id, user=request.user)
        task = TaskAttachmentSelector.get_task(
            workspace=membership.workspace, task_id=task_id, include_archived=True
        )
        if task is None:
            raise NotFound("Task not found.")

        attachments = TaskAttachmentSelector.get_attachments(workspace=membership.workspace, task_id=task_id)
        paginator = TaskAttachmentPagination()
        page = paginator.paginate_queryset(attachments, request, view=self)
        return paginator.get_paginated_response(TaskAttachmentOutputSerializer(page, many=True).data)

    def post(self, request, workspace_id, task_id, *args, **kwargs):
        membership = TaskAttachmentPermission.get_membership(workspace_id=workspace_id, user=request.user)
        TaskAttachmentPermission.require_upload(membership=membership)

        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        attachment = TaskAttachmentService.create_attachment(
            workspace=membership.workspace, task_id=task_id,
            uploaded_by=request.user, uploaded_file=serializer.validated_data["file"],
        )
        return Response(TaskAttachmentOutputSerializer(attachment).data, status=status.HTTP_201_CREATED)


class TaskAttachmentDetailApi(PrivateApi):
    def get(self, request, workspace_id, task_id, attachment_id, *args, **kwargs):
        membership = TaskAttachmentPermission.get_membership(workspace_id=workspace_id, user=request.user)
        attachment = TaskAttachmentSelector.get_attachment(workspace=membership.workspace, task_id=task_id, attachment_id=attachment_id)
        if attachment is None:
            raise NotFound("Attachment not found.")
        return Response(TaskAttachmentOutputSerializer(attachment).data)

    def delete(self, request, workspace_id, task_id, attachment_id, *args, **kwargs):
        membership = TaskAttachmentPermission.get_membership(workspace_id=workspace_id, user=request.user)
        TaskAttachmentService.delete_attachment(
            workspace=membership.workspace, task_id=task_id,
            attachment_id=attachment_id, user=request.user, membership=membership,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskAttachmentDownloadApi(PrivateApi):
    def get(self, request, workspace_id, task_id, attachment_id, *args, **kwargs):
        membership = TaskAttachmentPermission.get_membership(workspace_id=workspace_id, user=request.user)
        attachment = TaskAttachmentSelector.get_attachment(workspace=membership.workspace, task_id=task_id, attachment_id=attachment_id)
        if attachment is None:
            raise NotFound("Attachment not found.")

        try:
            file_handle = attachment.file.open("rb")
        except (FileNotFoundError, OSError):
            raise Http404("Attachment file not found.")

        return FileResponse(
            file_handle, as_attachment=True,
            filename=attachment.original_filename, content_type="application/octet-stream",
        )
