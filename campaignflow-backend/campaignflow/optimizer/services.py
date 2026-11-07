from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from campaignflow.campaigns.models import Campaign
from campaignflow.organization.models import WorkspaceMember
from campaignflow.optimizer.models import OptimizationRun
from campaignflow.tasks.models import Task, TaskActivity, TaskActivityType


class OptimizationConflict(APIException):
    status_code = 409
    default_detail = "The optimization plan is stale."
    default_code = "optimization_conflict"


class OptimizationApplyService:
    PLAN_FIELDS = {
        "planned_start",
        "planned_end",
        "latest_start_at",
        "is_critical",
        "slack_hours",
        "due_at",
    }

    @staticmethod
    def validate_permission(*, campaign, user):
        membership = WorkspaceMember.objects.filter(workspace=campaign.workspace, user=user,).first()

        if membership is None:
            raise NotFound("Campaign not found.")

        if membership.role not in (
            WorkspaceMember.Role.ADMIN,
            WorkspaceMember.Role.MANAGER,
        ):
            raise PermissionDenied("Only workspace admins and managers can apply optimization plans.")

        return membership

    @staticmethod
    def parse_datetime_value(*, field, value):
        if value is None:
            return None

        if not isinstance(value, str):
            raise ValidationError({field: "Expected an ISO 8601 datetime string."})

        parsed = parse_datetime(value)

        if parsed is None or timezone.is_naive(parsed):
            raise ValidationError({
                field: "Expected a timezone-aware ISO 8601 datetime."
            })

        return parsed

    @staticmethod
    def parse_decimal_value(*, field, value):
        if value is None:
            return None

        if isinstance(value, bool):
            raise ValidationError({field: "Expected a decimal number."})

        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError({field: "Expected a decimal number."})

        if not result.is_finite():
            raise ValidationError({field: "Expected a finite decimal number."})

        if result.as_tuple().exponent < -2 or len(result.as_tuple().digits) > 10:
            raise ValidationError({field: "Expected a decimal with at most 10 digits and 2 decimal places."})

        return result

    @classmethod
    def validate_plan_item(cls, *, item):
        if not isinstance(item, dict):
            raise ValidationError({"tasks": "Each task plan must be an object."})

        task_id = item.get("task_id")

        if not task_id:
            raise ValidationError({"task_id": "This field is required."})

        allowed = cls.PLAN_FIELDS | {"task_id", "assignee_id"}
        unknown = set(item) - allowed

        if unknown:
            raise ValidationError({
                "tasks": f"Unsupported plan fields: {', '.join(sorted(unknown))}"
            })

        data = {}

        for field in ("planned_start", "planned_end", "latest_start_at", "due_at"):
            if field in item:
                data[field] = cls.parse_datetime_value(field=field, value=item[field])

        if "is_critical" in item:
            if not isinstance(item["is_critical"], bool):
                raise ValidationError({"is_critical": "Expected a boolean."})
            data["is_critical"] = item["is_critical"]

        if "slack_hours" in item:
            data["slack_hours"] = cls.parse_decimal_value(
                field="slack_hours",
                value=item["slack_hours"],
            )

        if "assignee_id" in item:
            data["assignee_id"] = item["assignee_id"]

        if ("planned_start" in data and "planned_end" in data and data["planned_start"] is not None and data["planned_end"] is not None
            and data["planned_start"] > data["planned_end"]
        ):
            raise ValidationError({
                "planned_end": "Planned end must be on or after planned start."
            })

        return str(task_id), data

    @classmethod
    def validate_edits(cls, *, edits):
        if edits is None:
            return {}

        if not isinstance(edits, list):
            raise ValidationError({"edits": "Expected a list of task edits."})

        validated = {}

        for item in edits:
            task_id, data = cls.validate_plan_item(item=item)

            if task_id in validated:
                raise ValidationError({"edits": "Duplicate task ID."})

            validated[task_id] = data

        return validated

    @classmethod
    @transaction.atomic
    def apply_optimization_run(cls, *, run, user, edits=None):
        run_id = run.id if isinstance(run, OptimizationRun) else run

        initial_run = OptimizationRun.objects.select_related("campaign").filter(
            id=run_id,
        ).first()

        if initial_run is None:
            raise NotFound("Optimization run not found.")

        campaign = Campaign.objects.select_for_update().filter(
            id=initial_run.campaign_id,
            is_archived=False,
        ).first()

        if campaign is None:
            raise NotFound("Campaign not found.")

        cls.validate_permission(campaign=campaign, user=user)

        optimization_run = OptimizationRun.objects.select_for_update().get(
            id=run_id,
            campaign=campaign,
        )

        if optimization_run.applied_at is not None:
            return optimization_run

        if campaign.revision != optimization_run.campaign_revision:
            raise OptimizationConflict(
                "The campaign was modified after the optimization preview. Generate a new preview."
            )

        if not optimization_run.feasible:
            raise ValidationError({
                "run": "An infeasible optimization plan cannot be applied."
            })

        output = optimization_run.output_json

        if not isinstance(output, dict):
            raise ValidationError({"output_json": "Invalid optimization output."})

        plan_items = output.get("tasks")

        if not isinstance(plan_items, list):
            raise ValidationError({"output_json": "Expected a tasks list."})

        validated_plan = {}

        for item in plan_items:
            task_id, data = cls.validate_plan_item(item=item)

            if task_id in validated_plan:
                raise ValidationError({"output_json": "Duplicate task ID in optimization output."})

            validated_plan[task_id] = data

        validated_edits = cls.validate_edits(edits=edits)

        if set(validated_edits) - set(validated_plan):
            raise ValidationError({
                "edits": "Cannot edit tasks that are not included in the optimization plan."
            })

        for task_id, data in validated_edits.items():
            validated_plan[task_id].update(data)

        tasks = {
            str(task.id): task
            for task in Task.objects.select_for_update().filter(
                campaign=campaign,
                id__in=validated_plan.keys(),
            )
        }

        if len(tasks) != len(validated_plan):
            raise ValidationError({
                "tasks": "One or more tasks do not belong to this campaign."
            })

        member_ids = {
            str(data["assignee_id"])
            for data in validated_plan.values()
            if data.get("assignee_id") is not None
        }

        members = {
            str(member.id): member
            for member in WorkspaceMember.objects.filter(
                workspace=campaign.workspace,
                id__in=member_ids,
            )
        }

        if member_ids - set(members):
            raise ValidationError({
                "assignee_id": "One or more assignees do not belong to this workspace."
            })

        for task_id, data in validated_plan.items():
            task = tasks[task_id]
            changes = {}

            if "assignee_id" in data:
                assignee_id = data.pop("assignee_id")
                new_assignee = members.get(str(assignee_id)) if assignee_id is not None else None

                if task.assignee_id != (new_assignee.id if new_assignee else None):
                    changes["assignee_id"] = {
                        "old": str(task.assignee_id) if task.assignee_id else None,
                        "new": str(new_assignee.id) if new_assignee else None,
                    }
                    task.assignee = new_assignee

            for field, value in data.items():
                previous = getattr(task, field)

                if previous != value:
                    changes[field] = {
                        "old": str(previous) if previous is not None else None,
                        "new": str(value) if value is not None else None,
                    }
                    setattr(task, field, value)

            if changes:
                try:
                    task.full_clean()
                except Exception as exc:
                    if hasattr(exc, "message_dict"):
                        raise ValidationError(exc.message_dict)
                    raise

                task.save()

                TaskActivity.objects.create(
                    task=task,
                    actor=user,
                    action=TaskActivityType.UPDATED,
                    metadata={
                        "source": "optimizer",
                        "optimization_run_id": str(optimization_run.id),
                        "changes": changes,
                    },
                )

        optimization_run.applied_at = timezone.now()
        optimization_run.save(update_fields=["applied_at"])

        return optimization_run


def apply_optimization_run(run, user, edits=None):
    return OptimizationApplyService.apply_optimization_run(
        run=run,
        user=user,
        edits=edits,
    )