from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from campaignflow.core.apis import PrivateApi
from campaignflow.content.pagination import ContentPagination
from campaignflow.content.services import ContentService, ContentDefinitionService, ContentCalendarService
from campaignflow.content.serializers import (
    ContentCreateSerializer, ContentUpdateSerializer, ContentOutputSerializer,
    ContentListFilterSerializer, ContentStatusInputSerializer,
    ContentStatusHistoryOutputSerializer, ContentDuplicateInputSerializer,
    ContentDefinitionInputSerializer, ContentPlatformOutputSerializer,
    ContentFormatOutputSerializer, BulkRescheduleOutputSerializer, BulkRescheduleInputSerializer,
    CalendarEventSerializer, CalendarConflictsOutputSerializer, ContentRescheduleInputSerializer,
    CalendarFilterSerializer,
)


class ContentListApi(PrivateApi):

    def get(self, request, workspace_id, *args, **kwargs):
        filters = ContentListFilterSerializer(data=request.query_params.dict())
        filters.is_valid(raise_exception=True)

        queryset = ContentService.get_list(
            workspace_id=workspace_id, user=request.user,
            filters=filters.validated_data,
        )

        paginator = ContentPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        serializer = ContentOutputSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


class CampaignContentApi(PrivateApi):

    def get(self, request, workspace_id, campaign_id, *args, **kwargs):
        filters = ContentListFilterSerializer(data=request.query_params.dict())
        filters.is_valid(raise_exception=True)

        queryset = ContentService.get_list(
            workspace_id=workspace_id, campaign_id=campaign_id,
            user=request.user, filters=filters.validated_data,
        )

        paginator = ContentPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        serializer = ContentOutputSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)

    def post(self, request, workspace_id, campaign_id, *args, **kwargs):
        serializer = ContentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        content_item = ContentService.create(
            workspace_id=workspace_id, campaign_id=campaign_id,
            user=request.user, data=serializer.validated_data,
        )

        return Response(
            ContentOutputSerializer(content_item).data,
            status=status.HTTP_201_CREATED,
        )


class ContentDetailsApi(PrivateApi):

    def get(self, request, workspace_id, content_id, *args, **kwargs):
        content_item = ContentService.get_details(
            workspace_id=workspace_id, content_id=content_id, user=request.user,
        )

        return Response(ContentOutputSerializer(content_item).data)

    def patch(self, request, workspace_id, content_id, *args, **kwargs):
        serializer = ContentUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        content_item = ContentService.update(
            workspace_id=workspace_id, content_id=content_id,
            user=request.user, data=serializer.validated_data,
        )

        return Response(ContentOutputSerializer(content_item).data)

    def delete(self, request, workspace_id, content_id, *args, **kwargs):
        ContentService.archive(
            workspace_id=workspace_id, content_id=content_id, user=request.user,
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


class ContentStatusApi(PrivateApi):

    def post(self, request, workspace_id, content_id, *args, **kwargs):
        serializer = ContentStatusInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        content_item = ContentService.change_status(
            workspace_id=workspace_id, content_id=content_id,
            user=request.user, new_status=serializer.validated_data["status"],
            comment=serializer.validated_data.get("comment", ""),
        )

        return Response(ContentOutputSerializer(content_item).data)


class ContentStatusHistoryApi(PrivateApi):

    def get(self, request, workspace_id, content_id, *args, **kwargs):
        queryset = ContentService.get_history(
            workspace_id=workspace_id, content_id=content_id, user=request.user,
        )

        paginator = ContentPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        return paginator.get_paginated_response(
            ContentStatusHistoryOutputSerializer(page, many=True).data,
        )


class ContentDuplicateApi(PrivateApi):

    def post(self, request, workspace_id, content_id, *args, **kwargs):
        serializer = ContentDuplicateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        content_item = ContentService.duplicate(
            workspace_id=workspace_id, content_id=content_id,
            user=request.user, title=serializer.validated_data.get("title"),
        )

        return Response(
            ContentOutputSerializer(content_item).data,
            status=status.HTTP_201_CREATED,
        )


class ContentDefinitionListApi(PrivateApi):
    definition_type = None
    output_serializer_class = None

    def get(self, request, workspace_id, *args, **kwargs):
        queryset = ContentDefinitionService.get_list(
            workspace_id=workspace_id, user=request.user,
            definition_type=self.definition_type,
        )

        return Response(self.output_serializer_class(queryset, many=True).data)

    def post(self, request, workspace_id, *args, **kwargs):
        serializer = ContentDefinitionInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        definition = ContentDefinitionService.create(
            workspace_id=workspace_id, user=request.user,
            definition_type=self.definition_type, data=serializer.validated_data,
        )

        return Response(
            self.output_serializer_class(definition).data,
            status=status.HTTP_201_CREATED,
        )


class ContentDefinitionDetailsApi(PrivateApi):
    definition_type = None
    output_serializer_class = None

    def patch(self, request, workspace_id, definition_id, *args, **kwargs):
        serializer = ContentDefinitionInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        definition = ContentDefinitionService.update(
            workspace_id=workspace_id, user=request.user,
            definition_type=self.definition_type, definition_id=definition_id,
            data=serializer.validated_data,
        )

        return Response(self.output_serializer_class(definition).data)

    def delete(self, request, workspace_id, definition_id, *args, **kwargs):
        ContentDefinitionService.delete(
            workspace_id=workspace_id, user=request.user,
            definition_type=self.definition_type, definition_id=definition_id,
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


class ContentPlatformListApi(ContentDefinitionListApi):
    definition_type = "platform"
    output_serializer_class = ContentPlatformOutputSerializer


class ContentPlatformDetailsApi(ContentDefinitionDetailsApi):
    definition_type = "platform"
    output_serializer_class = ContentPlatformOutputSerializer


class ContentFormatListApi(ContentDefinitionListApi):
    definition_type = "format"
    output_serializer_class = ContentFormatOutputSerializer


class ContentFormatDetailsApi(ContentDefinitionDetailsApi):
    definition_type = "format"
    output_serializer_class = ContentFormatOutputSerializer

class ContentCalendarApi(PrivateApi):

    def get(self, request, workspace_id, campaign_id=None, *args, **kwargs):
        serializer = CalendarFilterSerializer(data=request.query_params.dict())
        serializer.is_valid(raise_exception=True)

        result = ContentCalendarService.get_calendar(
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            user=request.user,
            filters=serializer.validated_data,
        )

        output = ContentCalendarOutputSerializer(
            result,
            context={"membership": result["membership"], "now": timezone.now()},
        )

        return Response(output.data)


class ContentCalendarSummaryApi(PrivateApi):

    def get(self, request, workspace_id, *args, **kwargs):
        serializer = CalendarFilterSerializer(data=request.query_params.dict())
        serializer.is_valid(raise_exception=True)

        result = ContentCalendarService.get_summary(
            workspace_id=workspace_id,
            user=request.user,
            filters=serializer.validated_data,
        )

        return Response(CalendarSummaryOutputSerializer(result).data)


class ContentCalendarUnscheduledApi(PrivateApi):

    def get(self, request, workspace_id, *args, **kwargs):
        serializer = CalendarUnscheduledFilterSerializer(data=request.query_params.dict())
        serializer.is_valid(raise_exception=True)

        queryset, membership = ContentCalendarService.get_unscheduled(
            workspace_id=workspace_id,
            user=request.user,
            filters=serializer.validated_data,
        )

        paginator = ContentPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        output = CalendarEventSerializer(
            page, many=True,
            context={"membership": membership, "now": timezone.now()},
        )

        return paginator.get_paginated_response(output.data)


class ContentCalendarConflictsApi(PrivateApi):

    def get(self, request, workspace_id, *args, **kwargs):
        serializer = CalendarFilterSerializer(data=request.query_params.dict())
        serializer.is_valid(raise_exception=True)

        result = ContentCalendarService.get_conflicts(
            workspace_id=workspace_id,
            user=request.user,
            filters=serializer.validated_data,
        )

        return Response(CalendarConflictsOutputSerializer(result).data)


class ContentRescheduleApi(PrivateApi):

    def patch(self, request, workspace_id, content_id, *args, **kwargs):
        serializer = ContentRescheduleInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        content_item, membership = ContentCalendarService.reschedule(
            workspace_id=workspace_id,
            content_id=content_id,
            user=request.user,
            publication_at=serializer.validated_data["publication_at"],
        )

        output = CalendarEventSerializer(
            content_item,
            context={"membership": membership, "now": timezone.now()},
        )

        return Response(output.data, status=status.HTTP_200_OK)


class ContentBulkRescheduleApi(PrivateApi):

    def post(self, request, workspace_id, *args, **kwargs):
        serializer = BulkRescheduleInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = ContentCalendarService.bulk_reschedule(
            workspace_id=workspace_id,
            user=request.user,
            items=serializer.validated_data["items"],
        )

        output = BulkRescheduleOutputSerializer(
            result,
            context={"membership": result["membership"], "now": timezone.now()},
        )

        return Response(output.data, status=status.HTTP_200_OK)
