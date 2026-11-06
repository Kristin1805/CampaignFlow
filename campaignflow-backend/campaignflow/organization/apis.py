from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied

from campaignflow.core.apis import PrivateApi
from campaignflow.organization.models import WorkspaceMember
from campaignflow.organization.selectors import WorkspaceSelector
from campaignflow.organization.services import WorkspaceService


class WorkspaceListCreateApi(PrivateApi):
    class InputSerializer(serializers.Serializer):
        name = serializers.CharField(max_length=150)
        timezone = serializers.CharField(required=False, default="Europe/Sofia",)
        working_days = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=6), required=False,)
        working_hours_per_day = serializers.IntegerField(
            min_value=1,
            max_value=24,
            required=False,
            default=8,
        )

    def get(self, request, *args, **kwargs):
        memberships = WorkspaceSelector.get_user_workspaces(user=request.user,)

        result = [
            WorkspaceSelector.serialize_workspace(
                workspace=membership.workspace,
                role=membership.role,
            ).serialize()
            for membership in memberships
        ]

        return Response(result, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        workspace = WorkspaceService.create(user=request.user, **serializer.validated_data,)

        result = WorkspaceSelector.serialize_workspace(workspace=workspace,role=WorkspaceMember.Role.ADMIN,)

        return Response(result.serialize(), status=status.HTTP_201_CREATED,)


class WorkspaceDetailApi(PrivateApi):
    class InputSerializer(serializers.Serializer):
        name = serializers.CharField(max_length=150, required=False)
        timezone = serializers.CharField(required=False)
        working_days = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=6),required=False,)
        working_hours_per_day = serializers.IntegerField(min_value=1, max_value=24, required=False,)

    def get_membership(self, request, workspace_id):
        membership = (
            WorkspaceMember.objects
            .select_related("workspace")
            .filter(workspace_id=workspace_id, user=request.user,)
            .first()
        )

        if membership is None:
            raise NotFound("Workspace not found.")

        return membership

    def get(self, request, workspace_id, *args, **kwargs):
        membership = self.get_membership(request, workspace_id)

        result = WorkspaceSelector.serialize_workspace(
            workspace=membership.workspace,
            role=membership.role,
        )

        return Response(result.serialize())

    def patch(self, request, workspace_id, *args, **kwargs):
        membership = self.get_membership(request, workspace_id)

        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        workspace = WorkspaceService.update(workspace=membership.workspace, acting_member=membership, data=serializer.validated_data,)

        result = WorkspaceSelector.serialize_workspace(workspace=workspace,role=membership.role,)

        return Response(result.serialize())