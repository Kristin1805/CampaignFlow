from decimal import Decimal

from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from campaignflow.optimizer.models import OptimizationRun, Risk
from campaignflow.optimizer.pagination import (
    OptimizationHistoryPagination,
)
from campaignflow.optimizer.selectors import OptimizerSelector
from campaignflow.optimizer.services import (
    OptimizationHistoryService,
    OptimizerService,
    apply_optimization_run, CampaignScheduleService,
)
from campaignflow.tasks.enums import TaskStatus


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown_fields = set(data) - set(self.fields)

            if unknown_fields:
                raise serializers.ValidationError({
                    field: "Unknown field."
                    for field in sorted(unknown_fields)
                })

        return super().to_internal_value(data)


class OptimizationTaskEditSerializer(StrictSerializer):
    task_id = serializers.UUIDField()

    assignee_id = serializers.UUIDField(required=False, allow_null=True,)

    planned_start = serializers.DateTimeField(required=False, allow_null=True,)

    planned_end = serializers.DateTimeField(required=False, allow_null=True,)

    latest_start_at = serializers.DateTimeField(required=False, allow_null=True,)

    is_critical = serializers.BooleanField(required=False,)

    slack_hours = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        allow_null=True,
    )

    due_at = serializers.DateTimeField(required=False, allow_null=True,)

    must_finish_by = serializers.DateTimeField(required=False, allow_null=True,)

    def validate(self, attrs):
        if "due_at" in attrs and "must_finish_by" in attrs:
            raise serializers.ValidationError({
                "due_at": (
                    "Provide either due_at or must_finish_by, "
                    "not both."
                )
            })

        planned_start = attrs.get("planned_start")
        planned_end = attrs.get("planned_end")

        if planned_start is not None and planned_end is not None and planned_start > planned_end:
            raise serializers.ValidationError({
                "planned_end": "Planned end must be on or after planned start."
            })

        return attrs


class OptimizationApplyInputSerializer(StrictSerializer):
    edits = OptimizationTaskEditSerializer(many=True, required=False,)

    def validate_edits(self, edits):
        task_ids = set()

        for edit in edits:
            task_id = edit["task_id"]

            if task_id in task_ids:
                raise serializers.ValidationError("Duplicate task ID.")

            task_ids.add(task_id)

        return edits


class OptimizationApplyOutputSerializer(serializers.ModelSerializer):
    run_id = serializers.UUIDField(source="id",read_only=True,)

    campaign_id = serializers.UUIDField(read_only=True,)

    applied = serializers.SerializerMethodField()

    current_campaign_revision = serializers.IntegerField(source="campaign.revision", read_only=True,)

    class Meta:
        model = OptimizationRun

        fields = (
            "run_id",
            "campaign_id",
            "feasible",
            "campaign_revision",
            "current_campaign_revision",
            "applied",
            "applied_at",
        )
        read_only_fields = fields

    def get_applied(self, obj):
        return obj.applied_at is not None


class OptimizationPreviewOutputSerializer(serializers.Serializer):
    run_id = serializers.UUIDField()
    campaign_id = serializers.UUIDField()
    campaign_revision = serializers.IntegerField()
    feasible = serializers.BooleanField()

    makespan_hours = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True,)
    risk = serializers.ChoiceField(choices=Risk.choices,)
    duration_ms = serializers.IntegerField(allow_null=True,)
    engine_version = serializers.CharField()
    output = serializers.JSONField()
    diff = serializers.ListField(child=serializers.DictField(),)




class OptimizationHistoryFilterSerializer(StrictSerializer):

    risk = serializers.ChoiceField(choices=Risk.choices, required=False,)

    feasible = serializers.BooleanField(required=False,)

    applied = serializers.BooleanField(required=False,)

    page = serializers.IntegerField(min_value=1, required=False,)

    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False,)


class OptimizationRequestedBySerializer(serializers.Serializer):
    id = serializers.ReadOnlyField()
    email = serializers.EmailField(read_only=True,)


class OptimizationHistoryOutputSerializer(serializers.ModelSerializer):

    run_id = serializers.UUIDField(source="id", read_only=True,)

    campaign_id = serializers.UUIDField(read_only=True,)

    requested_by = OptimizationRequestedBySerializer(read_only=True,)

    applied = serializers.SerializerMethodField()

    class Meta:
        model = OptimizationRun

        fields = (
            "run_id",
            "campaign_id",
            "requested_by",
            "feasible",
            "risk",
            "makespan_hours",
            "engine_version",
            "duration_ms",
            "campaign_revision",
            "applied",
            "applied_at",
            "created_at",
        )

        read_only_fields = fields

    def get_applied(self, obj):
        return OptimizationHistoryService.is_applied(optimization_run=obj,)


class OptimizationDetailsOutputSerializer(OptimizationHistoryOutputSerializer):

    current_campaign_revision = serializers.IntegerField(source="campaign.revision", read_only=True,)

    stale = serializers.SerializerMethodField()

    schedule = serializers.SerializerMethodField()

    critical_path = serializers.SerializerMethodField()

    changes = serializers.SerializerMethodField()

    must_finish_by = serializers.SerializerMethodField()

    class Meta(OptimizationHistoryOutputSerializer.Meta):
        fields = (
            OptimizationHistoryOutputSerializer.Meta.fields
            + (
                "current_campaign_revision",
                "stale",
                "input_json",
                "output_json",
                "schedule",
                "critical_path",
                "changes",
                "must_finish_by",
            )
        )

        read_only_fields = fields

    def get_stale(self, obj):
        return OptimizationHistoryService.is_stale(
            optimization_run=obj,
        )

    def get_schedule(self, obj):
        return obj.output_json.get(
            "schedule",
            [],
        )

    def get_critical_path(self, obj):
        return obj.output_json.get(
            "critical_path",
            [],
        )

    def get_changes(self, obj):
        return obj.output_json.get(
            "changes",
            [],
        )

    def get_must_finish_by(self, obj):
        return obj.output_json.get(
            "must_finish_by",
            [],
        )


# CF-053: Preview API


class OptimizationPreviewApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, campaign_id):
        workspace = getattr(request, "workspace", None)

        if workspace is None:
            raise ValidationError({
                "workspace": "Workspace context is required."
            })

        campaign = OptimizerSelector.get_campaign(workspace=workspace, campaign_id=campaign_id,)

        if campaign is None:
            raise NotFound("Campaign not found.")

        optimization_run, diff = OptimizerService.preview(campaign=campaign, user=request.user,)

        data = {
            "run_id": optimization_run.id,
            "campaign_id": optimization_run.campaign_id,
            "campaign_revision": optimization_run.campaign_revision,
            "feasible": optimization_run.feasible,
            "makespan_hours": optimization_run.makespan_hours,
            "risk": optimization_run.risk,
            "duration_ms": optimization_run.duration_ms,
            "engine_version": optimization_run.engine_version,
            "output": optimization_run.output_json,
            "diff": diff,
        }

        serializer = OptimizationPreviewOutputSerializer(instance=data,)

        return Response(serializer.data, status=status.HTTP_200_OK,)


class OptimizationApplyApi(APIView):
    permission_classes = [IsAuthenticated]

    DATETIME_FIELDS = {
        "planned_start",
        "planned_end",
        "latest_start_at",
        "due_at",
        "must_finish_by",
    }

    STRING_FIELDS = {
        "task_id",
        "assignee_id",
        "slack_hours",
    }

    @classmethod
    def serialize_edits(cls, edits):
        if edits is None:
            return None

        serialized_edits = []

        for item in edits:
            serialized_item = {}

            for field, value in item.items():
                if value is None:
                    serialized_item[field] = None

                elif field in cls.DATETIME_FIELDS:
                    serialized_item[field] = value.isoformat()

                elif field in cls.STRING_FIELDS:
                    serialized_item[field] = str(value)

                else:
                    serialized_item[field] = value

            serialized_edits.append(serialized_item)

        return serialized_edits

    def post(self, request, run_id):
        workspace = getattr(request, "workspace", None)

        if workspace is None:
            raise ValidationError({
                "workspace": "Workspace context is required."
            })

        serializer = OptimizationApplyInputSerializer(data=request.data,)

        serializer.is_valid(raise_exception=True,)

        existing_run = OptimizerSelector.get_optimization_run(workspace=workspace, run_id=run_id,)

        if existing_run is None:
            raise NotFound("Optimization run not found.")

        edits = self.serialize_edits(serializer.validated_data.get("edits"),)

        optimization_run = apply_optimization_run(
            run=run_id,
            user=request.user,
            edits=edits,
        )

        optimization_run.refresh_from_db()

        optimization_run.campaign.refresh_from_db(fields=["revision"],)

        output_serializer = OptimizationApplyOutputSerializer(instance=optimization_run,)

        return Response(output_serializer.data, status=status.HTTP_200_OK,)



class OptimizationHistoryApi(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, campaign_id):
        workspace = getattr(request, "workspace",None,)

        if workspace is None:
            raise ValidationError({
                "workspace": "Workspace context is required."
            })

        filter_serializer = OptimizationHistoryFilterSerializer(
            data=request.query_params.dict(),
        )

        filter_serializer.is_valid(raise_exception=True,)

        queryset = OptimizationHistoryService.get_history(
            workspace=workspace,
            campaign_id=campaign_id,
            user=request.user,
            filters=filter_serializer.validated_data,
        )

        paginator = OptimizationHistoryPagination()

        page = paginator.paginate_queryset(queryset, request, view=self,)

        serializer = OptimizationHistoryOutputSerializer(instance=page, many=True,)

        return paginator.get_paginated_response(serializer.data,)

class OptimizationDetailsApi(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, run_id):
        workspace = getattr(request, "workspace", None,)

        if workspace is None:
            raise ValidationError({
                "workspace": "Workspace context is required."
            })

        optimization_run = OptimizationHistoryService.get_details(workspace=workspace, run_id=run_id, user=request.user,)

        serializer = OptimizationDetailsOutputSerializer(instance=optimization_run,)

        return Response(serializer.data, status=status.HTTP_200_OK,)



class CampaignScheduleFilterSerializer(serializers.Serializer):

    assignee_id = serializers.UUIDField(required=False,)

    status = serializers.ChoiceField(choices=TaskStatus.choices,required=False,)

    is_critical = serializers.BooleanField(required=False,)

    def to_internal_value(self, data):
        unknown_fields = set(data) - set(self.fields)

        if unknown_fields:
            raise serializers.ValidationError({
                field: "Unknown filter."
                for field in sorted(unknown_fields)
            })

        return super().to_internal_value(data)



class ScheduleAssigneeSerializer(serializers.Serializer):
    id = serializers.UUIDField()

    user_id = serializers.ReadOnlyField()

    email = serializers.EmailField(source="user.email", read_only=True,)

class CampaignScheduleTaskSerializer(serializers.Serializer):

    id = serializers.UUIDField()

    campaign_id = serializers.UUIDField()

    title = serializers.CharField()

    status = serializers.CharField()

    priority = serializers.CharField()

    assignee_id = serializers.UUIDField(allow_null=True,)

    assignee = ScheduleAssigneeSerializer(allow_null=True, read_only=True,)

    required_skill_id = serializers.UUIDField(allow_null=True,)

    required_skill_code = serializers.CharField(source="required_skill.code", allow_null=True, read_only=True,)

    estimated_hours = serializers.DecimalField(max_digits=10, decimal_places=2,)

    actual_hours = serializers.DecimalField(max_digits=10, decimal_places=2,)

    planned_start = serializers.DateTimeField(allow_null=True,)

    planned_end = serializers.DateTimeField(allow_null=True,)

    latest_start_at = serializers.DateTimeField(allow_null=True,)

    due_at = serializers.DateTimeField(allow_null=True,)

    slack_hours = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True,)

    is_critical = serializers.BooleanField()

    is_scheduled = serializers.SerializerMethodField()

    def get_is_scheduled(self, obj):
        return CampaignScheduleService.is_task_scheduled(task=obj,)



class CampaignScheduleDependencySerializer(serializers.Serializer):
    id = serializers.UUIDField()

    task_id = serializers.UUIDField()

    depends_on_task_id = serializers.UUIDField()

    lag_hours = serializers.DecimalField(max_digits=10, decimal_places=2,)



class CampaignScheduleSummarySerializer(serializers.Serializer):

    total_tasks = serializers.IntegerField()

    scheduled_tasks = serializers.IntegerField()

    unscheduled_tasks = serializers.IntegerField()

    critical_tasks = serializers.IntegerField()

    total_dependencies = serializers.IntegerField()



class CampaignScheduleOutputSerializer(serializers.Serializer):

    campaign_id = serializers.UUIDField()

    campaign_revision = serializers.IntegerField()

    launch_at = serializers.DateTimeField(allow_null=True,)

    optimization_run_id = serializers.UUIDField(allow_null=True,)

    optimization_stale = serializers.BooleanField()

    schedule_start = serializers.DateTimeField(allow_null=True,)

    schedule_end = serializers.DateTimeField(allow_null=True,)

    summary = CampaignScheduleSummarySerializer()

    tasks = CampaignScheduleTaskSerializer(many=True,)

    dependencies = CampaignScheduleDependencySerializer(many=True,)

    unscheduled_task_ids = serializers.ListField(child=serializers.UUIDField(),)



class CampaignCriticalPathOutputSerializer(serializers.Serializer):

    campaign_id = serializers.UUIDField()

    campaign_revision = serializers.IntegerField()

    optimization_run_id = serializers.UUIDField(allow_null=True,)

    optimization_revision = serializers.IntegerField(allow_null=True,)

    applied_at = serializers.DateTimeField(allow_null=True,)

    available = serializers.BooleanField()

    stale = serializers.BooleanField()

    risk = serializers.ChoiceField(choices=Risk.choices, allow_null=True, allow_blank=True,)

    makespan_hours = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True,)

    critical_path = serializers.ListField(child=serializers.UUIDField(),)

    tasks = CampaignScheduleTaskSerializer(many=True,)

    missing_task_ids = serializers.ListField(child=serializers.UUIDField(),)


class CampaignScheduleApi(APIView):

    permission_classes = [IsAuthenticated,]

    def get(self, request, campaign_id):
        workspace = getattr(request, "workspace", None,)

        if workspace is None:
            raise ValidationError({
                "workspace": ("Workspace context is required.")
            })

        filter_serializer = (
            CampaignScheduleFilterSerializer(data=request.query_params.dict(),)
        )

        filter_serializer.is_valid(raise_exception=True,)

        result = CampaignScheduleService.get_schedule(
            workspace=workspace,
            campaign_id=campaign_id,
            user=request.user,
            filters=filter_serializer.validated_data,
        )

        serializer = CampaignScheduleOutputSerializer(instance=result,)

        return Response(serializer.data, status=status.HTTP_200_OK,)



class CampaignCriticalPathApi(APIView):

    permission_classes = [IsAuthenticated,]

    def get(self, request, campaign_id):
        workspace = getattr(request, "workspace", None,)

        if workspace is None:
            raise ValidationError({
                "workspace": (
                    "Workspace context is required."
                )
            })

        result = CampaignScheduleService.get_critical_path(workspace=workspace, campaign_id=campaign_id, user=request.user,)

        serializer = (CampaignCriticalPathOutputSerializer(instance=result,))

        return Response(serializer.data,status=status.HTTP_200_OK,)

