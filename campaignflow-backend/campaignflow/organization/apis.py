from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from campaignflow.core.apis import PrivateApi
from campaignflow.organization.models import WorkspaceMember
from campaignflow.organization.selectors import WorkspaceSelector
from campaignflow.organization.services import WorkspaceService
from campaignflow.organization.validators import validate_timezone, validate_working_days


class WorkspaceOutputSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    timezone = serializers.CharField()
    working_days = serializers.ListField(child=serializers.IntegerField(),)
    working_hours_per_day = serializers.IntegerField()
    role = serializers.CharField()


class WorkspaceListCreateApi(PrivateApi):
    class InputSerializer(serializers.Serializer):
        name = serializers.CharField(max_length=150, allow_blank=False,)
        timezone = serializers.CharField(max_length=64, required=False, default="Europe/Sofia", validators=[validate_timezone],)
        working_days = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=6,), required=False, validators=[validate_working_days],)
        working_hours_per_day = serializers.IntegerField(min_value=1, max_value=24, required=False, default=8,)

    OutputSerializer = WorkspaceOutputSerializer

    def get(self, request, *args, **kwargs):
        memberships = WorkspaceSelector.get_user_workspaces(user=request.user,)

        results = [
            WorkspaceSelector.serialize_workspace(workspace=membership.workspace, role=membership.role,).serialize()
            for membership in memberships
        ]

        return Response(self.OutputSerializer(results, many=True).data, status=status.HTTP_200_OK,)

    def post(self, request, *args, **kwargs):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        workspace = WorkspaceService.create(user=request.user, **serializer.validated_data,)

        result = WorkspaceSelector.serialize_workspace(workspace=workspace, role=WorkspaceMember.Role.ADMIN,)

        return Response(self.OutputSerializer(result.serialize()).data, status=status.HTTP_201_CREATED,)


class WorkspaceDetailApi(PrivateApi):
    class InputSerializer(serializers.Serializer):
        name = serializers.CharField(max_length=150, allow_blank=False, required=False,)
        timezone = serializers.CharField(max_length=64, required=False, validators=[validate_timezone],)
        working_days = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=6,), required=False, validators=[validate_working_days],)
        working_hours_per_day = serializers.IntegerField(min_value=1, max_value=24, required=False,)

    OutputSerializer = WorkspaceOutputSerializer

    @staticmethod
    def get_membership(*, workspace_id, user):
        membership = WorkspaceSelector.get_membership(workspace_id=workspace_id, user=user,)

        if membership is None:
            raise NotFound("Workspace not found.")

        return membership

    def get(self, request, workspace_id, *args, **kwargs):
        membership = self.get_membership(workspace_id=workspace_id, user=request.user,)

        result = WorkspaceSelector.serialize_workspace(workspace=membership.workspace, role=membership.role,)

        return Response(self.OutputSerializer(result.serialize()).data,)

    def patch(self, request, workspace_id, *args, **kwargs):
        membership = self.get_membership(workspace_id=workspace_id, user=request.user,)

        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        workspace = WorkspaceService.update(workspace=membership.workspace, acting_member=membership, data=serializer.validated_data,)

        result = WorkspaceSelector.serialize_workspace(workspace=workspace, role=membership.role,)

        return Response(self.OutputSerializer(result.serialize()).data,)
