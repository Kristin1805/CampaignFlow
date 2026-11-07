
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from campaignflow.core.apis import PrivateApi
from campaignflow.campaigns.models import Campaign
from campaignflow.campaigns.selectors import CampaignSelector
from campaignflow.campaigns.services import CampaignService
from campaignflow.campaigns.permissions import CampaignPermission


class CampaignOutputSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    workspace_id = serializers.UUIDField()
    name = serializers.CharField()
    description = serializers.CharField()
    goal = serializers.CharField()
    status = serializers.CharField()
    starts_on = serializers.DateField(allow_null=True)
    ends_on = serializers.DateField(allow_null=True)
    launch_at = serializers.DateTimeField(allow_null=True)
    budget_total = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    created_by_id = serializers.UUIDField()
    is_archived = serializers.BooleanField()
    archived_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class CampaignInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False, allow_blank=False)
    description = serializers.CharField(required=False, allow_blank=True)
    goal = serializers.CharField(required=False, allow_blank=True)
    starts_on = serializers.DateField(required=False, allow_null=True)
    ends_on = serializers.DateField(required=False, allow_null=True)
    launch_at = serializers.DateTimeField(required=False, allow_null=True)
    budget_total = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        required=False,
        allow_null=True,
    )


class CampaignListQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Campaign.Status.choices, required=False)
    search = serializers.CharField(required=False, allow_blank=True)
    ordering = serializers.ChoiceField(
        choices=list(CampaignSelector.ORDERING_FIELDS),
        required=False,
        default="-created_at",
    )


class CampaignStatusInputSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Campaign.Status.choices)


class CampaignPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class CampaignListCreateApi(PrivateApi):
    def get(self, request, workspace_id, *args, **kwargs):
        membership = CampaignPermission.get_membership(workspace_id=workspace_id, user=request.user,)

        serializer = CampaignListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        queryset = CampaignSelector.get_workspace_campaigns(workspace=membership.workspace, **serializer.validated_data,)

        paginator = CampaignPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)

        return paginator.get_paginated_response(CampaignOutputSerializer(page, many=True).data)

    def post(self, request, workspace_id, *args, **kwargs):
        membership = CampaignPermission.get_membership(workspace_id=workspace_id, user=request.user,)
        CampaignPermission.require_management(membership=membership)

        serializer = CampaignInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        if not data.get("name"):
            raise serializers.ValidationError({
                "name": "This field is required."
            })

        campaign = CampaignService.create_campaign(workspace=membership.workspace, user=request.user, data=data,)

        return Response(CampaignOutputSerializer(campaign).data, status=status.HTTP_201_CREATED,)


class CampaignDetailApi(PrivateApi):
    def get(self, request, workspace_id, campaign_id, *args, **kwargs):
        membership = CampaignPermission.get_membership(workspace_id=workspace_id, user=request.user,)

        campaign = CampaignSelector.get_by_id(workspace=membership.workspace, campaign_id=campaign_id,)

        if campaign is None:
            raise NotFound("Campaign not found.")

        return Response(CampaignOutputSerializer(campaign).data)

    def patch(self, request, workspace_id, campaign_id, *args, **kwargs):
        membership = CampaignPermission.get_membership(workspace_id=workspace_id, user=request.user,)
        CampaignPermission.require_management(membership=membership)

        serializer = CampaignInputSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        campaign = CampaignService.update_campaign(workspace=membership.workspace, campaign_id=campaign_id, data=serializer.validated_data,)

        return Response(CampaignOutputSerializer(campaign).data)

    def delete(self, request, workspace_id, campaign_id, *args, **kwargs):
        membership = CampaignPermission.get_membership(workspace_id=workspace_id, user=request.user,)
        CampaignPermission.require_admin(membership=membership)

        CampaignService.archive_campaign(workspace=membership.workspace, campaign_id=campaign_id,)

        return Response(status=status.HTTP_204_NO_CONTENT)


class CampaignStatusApi(PrivateApi):
    def patch(self, request, workspace_id, campaign_id, *args, **kwargs):
        membership = CampaignPermission.get_membership(workspace_id=workspace_id, user=request.user,)
        CampaignPermission.require_management(membership=membership)

        serializer = CampaignStatusInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        campaign = CampaignService.change_status(workspace=membership.workspace, campaign_id=campaign_id,new_status=serializer.validated_data["status"],)

        return Response(CampaignOutputSerializer(campaign).data)
