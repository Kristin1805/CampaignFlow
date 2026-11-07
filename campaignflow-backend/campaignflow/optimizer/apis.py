
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from campaignflow.optimizer.models import OptimizationRun
from campaignflow.optimizer.services import apply_optimization_run


class OptimizationTaskEditSerializer(serializers.Serializer):
    task_id = serializers.UUIDField()
    assignee_id = serializers.UUIDField(required=False, allow_null=True)
    planned_start = serializers.DateTimeField(required=False, allow_null=True)
    planned_end = serializers.DateTimeField(required=False, allow_null=True)
    latest_start_at = serializers.DateTimeField(required=False, allow_null=True)
    is_critical = serializers.BooleanField(required=False)
    slack_hours = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    must_finish_by = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        if "due_at" in attrs and "must_finish_by" in attrs:
            raise serializers.ValidationError({"due_at": "Provide either due_at or must_finish_by, not both."})

        planned_start = attrs.get("planned_start")
        planned_end = attrs.get("planned_end")

        if planned_start is not None and planned_end is not None and planned_start > planned_end:
            raise serializers.ValidationError({"planned_end": "Planned end must be on or after planned start."})

        return attrs


class OptimizationApplyInputSerializer(serializers.Serializer):
    edits = OptimizationTaskEditSerializer(many=True, required=False)


class OptimizationApplyOutputSerializer(serializers.ModelSerializer):
    run_id = serializers.UUIDField(source="id", read_only=True)
    campaign_id = serializers.UUIDField(read_only=True)
    applied = serializers.SerializerMethodField()
    current_campaign_revision = serializers.IntegerField(source="campaign.revision", read_only=True)

    class Meta:
        model = OptimizationRun
        fields = (
            "run_id", "campaign_id", "feasible", "campaign_revision",
            "current_campaign_revision", "applied", "applied_at",
        )
        read_only_fields = fields

    def get_applied(self, obj):
        return obj.applied_at is not None


class OptimizationApplyApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, run_id):
        serializer = OptimizationApplyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        edits = serializer.validated_data.get("edits")

        if edits is not None:
            datetime_fields = {
                "planned_start", "planned_end", "latest_start_at",
                "due_at", "must_finish_by",
            }
            uuid_fields = {"task_id", "assignee_id"}

            edits = [
                {
                    key: (
                        value.isoformat() if key in datetime_fields and value is not None
                        else str(value) if key in uuid_fields | {"slack_hours"} and value is not None
                        else value
                    )
                    for key, value in item.items()
                }
                for item in edits
            ]

        optimization_run = apply_optimization_run(run=run_id, user=request.user, edits=edits)
        optimization_run.refresh_from_db()
        optimization_run.campaign.refresh_from_db(fields=["revision"])

        output_serializer = OptimizationApplyOutputSerializer(optimization_run)
        return Response(output_serializer.data, status=status.HTTP_200_OK)
