from django.http import FileResponse, Http404
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser
from campaignflow.documents.permissions import TaskAttachmentPermission
from campaignflow.documents.selectors import TaskAttachmentSelector
from campaignflow.documents.services import TaskAttachmentService
from rest_framework.response import Response

from campaignflow.core.apis import PrivateApi

from campaignflow.documents.constants import (
    TEMPLATE_SCHEMA_VERSION,
    MAX_TEMPLATE_SECTIONS,
    MAX_TABLE_COLUMNS,
    MAX_SECTION_FIELDS,
    MAX_SELECTION_OPTIONS,
    MAX_TEMPLATE_STRUCTURE_BYTES,
)
from campaignflow.documents.enums import (
    DocumentTemplateCategory,
    DocumentSectionType,
    DocumentFieldType,
    DocumentTemplateStatus,
)

from rest_framework import status
from rest_framework.response import Response

from campaignflow.documents.pagination import DocumentPagination
from campaignflow.documents.services import DocumentService

from campaignflow.documents.serializers import (
    DocumentGenerateSerializer,
    DocumentBlankSerializer,
    DocumentMetadataSerializer,
    DocumentDuplicateSerializer,
    DocumentStatusSerializer,
    DocumentEmptySerializer,
    DocumentListFilterSerializer,
    DocumentListOutputSerializer,
    DocumentOutputSerializer,
    DocumentGenerationPreviewSerializer,
)

from campaignflow.documents.pagination import DocumentTemplatePagination
from campaignflow.documents.placeholders import DocumentPlaceholderRegistry
from campaignflow.documents.serializers import (
    DocumentTemplateCreateSerializer,
    DocumentTemplateUpdateSerializer,
    DocumentTemplateDraftSerializer,
    DocumentTemplatePublishSerializer,
    DocumentTemplateVersionRestoreSerializer,
    DocumentTemplateDuplicateSerializer,
    DocumentTemplateFilterSerializer,
    DocumentTemplateListSerializer,
    DocumentTemplateDetailsSerializer,
    DocumentTemplateVersionSerializer,
    DocumentTemplateVersionListSerializer,
)
from campaignflow.documents.services import DocumentTemplateService


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

def template_response(template, membership, response_status=status.HTTP_200_OK):
    serializer = DocumentTemplateDetailsSerializer(
        template, context={"membership": membership},
    )

    return Response(serializer.data, status=response_status)


class DocumentTemplateListApi(PrivateApi):

    def get(self, request, workspace_id, *args, **kwargs):
        serializer = DocumentTemplateFilterSerializer(
            data=request.query_params.dict(),
        )
        serializer.is_valid(raise_exception=True)

        queryset, membership = DocumentTemplateService.get_list(
            workspace_id=workspace_id,
            user=request.user,
            filters=serializer.validated_data,
        )

        paginator = DocumentTemplatePagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        output = DocumentTemplateListSerializer(
            page, many=True, context={"membership": membership},
        )

        return paginator.get_paginated_response(output.data)

    def post(self, request, workspace_id, *args, **kwargs):
        serializer = DocumentTemplateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        template, membership = DocumentTemplateService.create(
            workspace_id=workspace_id,
            user=request.user,
            data=serializer.validated_data,
        )

        return template_response(template, membership, status.HTTP_201_CREATED)


class DocumentTemplateDetailsApi(PrivateApi):

    def get(self, request, workspace_id, template_id, *args, **kwargs):
        template, membership = DocumentTemplateService.get_details(
            workspace_id=workspace_id,
            template_id=template_id,
            user=request.user,
        )

        return template_response(template, membership)

    def patch(self, request, workspace_id, template_id, *args, **kwargs):
        serializer = DocumentTemplateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        template, membership = DocumentTemplateService.update_metadata(
            workspace_id=workspace_id,
            template_id=template_id,
            user=request.user,
            data=serializer.validated_data,
        )

        return template_response(template, membership)


class DocumentTemplateDraftApi(PrivateApi):

    def patch(self, request, workspace_id, template_id, *args, **kwargs):
        serializer = DocumentTemplateDraftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        template, membership = DocumentTemplateService.update_draft(
            workspace_id=workspace_id,
            template_id=template_id,
            user=request.user,
            **serializer.validated_data,
        )

        return template_response(template, membership)


class DocumentTemplatePublishApi(PrivateApi):

    def post(self, request, workspace_id, template_id, *args, **kwargs):
        serializer = DocumentTemplatePublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        version, _ = DocumentTemplateService.publish(
            workspace_id=workspace_id,
            template_id=template_id,
            user=request.user,
            **serializer.validated_data,
        )

        return Response(
            DocumentTemplateVersionSerializer(version).data,
            status=status.HTTP_201_CREATED,
        )


class DocumentTemplateVersionListApi(PrivateApi):

    def get(self, request, workspace_id, template_id, *args, **kwargs):
        queryset, _ = DocumentTemplateService.get_versions(
            workspace_id=workspace_id,
            template_id=template_id,
            user=request.user,
        )

        paginator = DocumentTemplatePagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        output = DocumentTemplateVersionListSerializer(page, many=True)

        return paginator.get_paginated_response(output.data)


class DocumentTemplateVersionDetailsApi(PrivateApi):

    def get(self, request, workspace_id, template_id, version_id, *args, **kwargs):
        version, _ = DocumentTemplateService.get_version(
            workspace_id=workspace_id,
            template_id=template_id,
            version_id=version_id,
            user=request.user,
        )

        return Response(DocumentTemplateVersionSerializer(version).data)


class DocumentTemplateVersionRestoreApi(PrivateApi):

    def post(self, request, workspace_id, template_id, version_id, *args, **kwargs):
        serializer = DocumentTemplateVersionRestoreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        template, membership = DocumentTemplateService.restore_version(
            workspace_id=workspace_id,
            template_id=template_id,
            version_id=version_id,
            user=request.user,
            **serializer.validated_data,
        )

        return template_response(template, membership)


class DocumentTemplateDuplicateApi(PrivateApi):

    def post(self, request, workspace_id, template_id, *args, **kwargs):
        serializer = DocumentTemplateDuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        template, membership = DocumentTemplateService.duplicate(
            workspace_id=workspace_id,
            template_id=template_id,
            user=request.user,
            data=serializer.validated_data,
        )

        return template_response(template, membership, status.HTTP_201_CREATED)


class DocumentTemplateArchiveApi(PrivateApi):

    def post(self, request, workspace_id, template_id, *args, **kwargs):
        template, membership = DocumentTemplateService.archive(
            workspace_id=workspace_id,
            template_id=template_id,
            user=request.user,
        )

        return template_response(template, membership)


class DocumentTemplateRestoreApi(PrivateApi):

    def post(self, request, workspace_id, template_id, *args, **kwargs):
        template, membership = DocumentTemplateService.restore(
            workspace_id=workspace_id,
            template_id=template_id,
            user=request.user,
        )

        return template_response(template, membership)


class DocumentTemplateCategoriesApi(PrivateApi):

    def get(self, request, workspace_id, *args, **kwargs):
        DocumentTemplateService.get_membership(
            workspace_id=workspace_id, user=request.user,
        )

        return Response([
            {"value": value, "label": label}
            for value, label in DocumentTemplateCategory.choices
        ])


class DocumentTemplatePlaceholdersApi(PrivateApi):

    def get(self, request, workspace_id, *args, **kwargs):
        DocumentTemplateService.get_membership(
            workspace_id=workspace_id, user=request.user,
        )

        return Response(DocumentPlaceholderRegistry.get_all())


class DocumentTemplateSchemaApi(PrivateApi):

    def get(self, request, workspace_id, *args, **kwargs):
        DocumentTemplateService.get_membership(
            workspace_id=workspace_id, user=request.user,
        )

        return Response({
            "schema_version": TEMPLATE_SCHEMA_VERSION,

            "section_types": [
                {"value": value, "label": label}
                for value, label in DocumentSectionType.choices
            ],

            "field_types": [
                {"value": value, "label": label}
                for value, label in DocumentFieldType.choices
            ],

            "statuses": [
                {"value": value, "label": label}
                for value, label in DocumentTemplateStatus.choices
            ],

            "limits": {
                "max_sections": MAX_TEMPLATE_SECTIONS,
                "max_table_columns": MAX_TABLE_COLUMNS,
                "max_section_fields": MAX_SECTION_FIELDS,
                "max_selection_options": MAX_SELECTION_OPTIONS,
                "max_structure_bytes": MAX_TEMPLATE_STRUCTURE_BYTES,
            },
        })

class DocumentBaseApi(PrivateApi):

    @staticmethod
    def document_response(*, document, membership, status_code=status.HTTP_200_OK):
        serializer = DocumentOutputSerializer(
            document,
            context={"membership": membership},
        )

        return Response(serializer.data, status=status_code)


class DocumentListApi(DocumentBaseApi):

    def get(self, request, workspace_id, campaign_id=None):
        serializer = DocumentListFilterSerializer(
            data=request.query_params.dict(),
        )
        serializer.is_valid(raise_exception=True)

        queryset, membership = DocumentService.get_list(
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            user=request.user,
            filters=serializer.validated_data,
        )

        queryset = queryset.defer(
            "content",
            "structure_snapshot",
            "template_version__structure",
            "template_version__template__draft_structure",
        )

        paginator = DocumentPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        output = DocumentListOutputSerializer(
            page,
            many=True,
            context={"membership": membership},
        )

        return paginator.get_paginated_response(output.data)


class DocumentDetailsApi(DocumentBaseApi):

    def get(self, request, workspace_id, document_id):
        document, membership = DocumentService.get_details(
            workspace_id=workspace_id,
            document_id=document_id,
            user=request.user,
        )

        return self.document_response(
            document=document,
            membership=membership,
        )

    def patch(self, request, workspace_id, document_id):
        serializer = DocumentMetadataSerializer(
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        document, membership = DocumentService.update_metadata(
            workspace_id=workspace_id,
            document_id=document_id,
            user=request.user,
            data=serializer.validated_data,
        )

        return self.document_response(
            document=document,
            membership=membership,
        )


class DocumentGenerateApi(DocumentBaseApi):

    def post(self, request, workspace_id):
        serializer = DocumentGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        document, membership = DocumentService.generate(
            workspace_id=workspace_id,
            user=request.user,
            data=serializer.validated_data,
        )

        return self.document_response(
            document=document,
            membership=membership,
            status_code=status.HTTP_201_CREATED,
        )


class DocumentGenerationPreviewApi(DocumentBaseApi):

    def post(self, request, workspace_id):
        serializer = DocumentGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        preview = DocumentService.preview(
            workspace_id=workspace_id,
            user=request.user,
            data=serializer.validated_data,
        )

        output = DocumentGenerationPreviewSerializer(preview)

        return Response(output.data)


class DocumentBlankApi(DocumentBaseApi):

    def post(self, request, workspace_id):
        serializer = DocumentBlankSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        document, membership = DocumentService.create_blank(
            workspace_id=workspace_id,
            user=request.user,
            data=serializer.validated_data,
        )

        return self.document_response(
            document=document,
            membership=membership,
            status_code=status.HTTP_201_CREATED,
        )


class DocumentDuplicateApi(DocumentBaseApi):

    def post(self, request, workspace_id, document_id):
        serializer = DocumentDuplicateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        document, membership = DocumentService.duplicate(
            workspace_id=workspace_id,
            document_id=document_id,
            user=request.user,
            data=serializer.validated_data,
        )

        return self.document_response(
            document=document,
            membership=membership,
            status_code=status.HTTP_201_CREATED,
        )


class DocumentStatusApi(DocumentBaseApi):

    def post(self, request, workspace_id, document_id):
        serializer = DocumentStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        document, membership = DocumentService.change_status(
            workspace_id=workspace_id,
            document_id=document_id,
            user=request.user,
            status=serializer.validated_data["status"],
        )

        return self.document_response(
            document=document,
            membership=membership,
        )


class DocumentArchiveApi(DocumentBaseApi):

    def post(self, request, workspace_id, document_id):
        serializer = DocumentEmptySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        document, membership = DocumentService.archive(
            workspace_id=workspace_id,
            document_id=document_id,
            user=request.user,
        )

        return self.document_response(
            document=document,
            membership=membership,
        )


class DocumentRestoreApi(DocumentBaseApi):

    def post(self, request, workspace_id, document_id):
        serializer = DocumentEmptySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        document, membership = DocumentService.restore(
            workspace_id=workspace_id,
            document_id=document_id,
            user=request.user,
        )

        return self.document_response(
            document=document,
            membership=membership,
        )