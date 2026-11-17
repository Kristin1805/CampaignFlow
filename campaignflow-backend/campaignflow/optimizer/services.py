import json
import logging
import subprocess
import time
import uuid

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    ValidationError,
)

from campaignflow.campaigns.models import Campaign
from campaignflow.organization.models import WorkspaceMember
from campaignflow.optimizer.models import OptimizationRun
from campaignflow.optimizer.selectors import OptimizerSelector
from campaignflow.optimizer.exceptions import (
    OptimizationConflict,
    OptimizerTimeout,
    OptimizerInternalError,
    OptimizerInvalidInput,
    OptimizerInfeasible,
    OptimizerDependencyCycle,
)
from campaignflow.tasks.models import Task, TaskActivityType
from campaignflow.tasks.services import TaskActivityService
from campaignflow.tasks.enums import TaskPriority, TaskStatus
from campaignflow.tasks.selectors import (
    TaskWorkloadSelector,
    CampaignScheduleSelector,
)

logger = logging.getLogger(__name__)


class OptimizerService:
    PRIORITIES = {
        TaskPriority.LOW: 1,
        TaskPriority.MEDIUM: 2,
        TaskPriority.HIGH: 3,
        TaskPriority.URGENT: 4,
    }

    @staticmethod
    def serialize_datetime(value):
        return value.isoformat() if value is not None else None

    @staticmethod
    def validate_schema(payload, schema_path, *, input_schema=False):
        try:
            with open(schema_path, encoding="utf-8") as schema_file:
                schema = json.load(schema_file)
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
            errors = sorted(validator.iter_errors(payload), key=lambda error: str(error.path))
        except (OSError, json.JSONDecodeError, SchemaError) as exc:
            logger.exception("Could not load optimizer schema: %s", schema_path)
            raise OptimizerInternalError("Optimizer JSON schema is unavailable or invalid.") from exc
        if errors:
            error = errors[0]
            logger.error("Optimizer schema validation failed at %s: %s", error.json_path, error.message)
            raise OptimizerInternalError({
                "code": "invalid_optimizer_input" if input_schema else "invalid_optimizer_output",
                "message": "Optimizer JSON schema validation failed.",
                "path": error.json_path,
            })

    @staticmethod
    def get_dependencies_by_task(dependencies):
        grouped = defaultdict(list)
        for dependency in dependencies:
            grouped[dependency.task_id].append({
                "task_id": str(dependency.depends_on_task_id),
                "lag_h": float(dependency.lag_hours),
            })
        return grouped

    @classmethod
    def build_input(cls, campaign):
        now = timezone.now()
        if campaign.launch_at is None or campaign.launch_at <= now:
            raise ValidationError({"launch_at": "Campaign launch date must be in the future."})
        workspace = campaign.workspace
        try:
            workspace_timezone = ZoneInfo(workspace.timezone)
        except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
            logger.exception("Invalid workspace timezone.")
            raise OptimizerInternalError("Invalid workspace timezone.") from exc
        local_now = timezone.localtime(now, workspace_timezone)
        deadline = timezone.localtime(campaign.launch_at, workspace_timezone)
        tasks = OptimizerSelector.get_tasks(campaign=campaign)
        dependencies = OptimizerSelector.get_dependencies(campaign=campaign, task_ids={task.id for task in tasks})
        grouped = cls.get_dependencies_by_task(dependencies)
        members = OptimizerSelector.get_members(workspace=workspace)
        with timezone.override(workspace_timezone):
            busy_hours = TaskWorkloadSelector.get_optimizer_busy_hours(
                workspace=workspace, campaign=campaign, start_date=local_now.date(),
                end_date=deadline.date(), member_ids=[member.id for member in members],
            )
        return {
            "campaign_id": str(campaign.id),
            "now": local_now.isoformat(),
            "deadline": deadline.isoformat(),
            "calendar": {
                "hours_per_day": float(workspace.working_hours_per_day),
                "day_start": "09:00",
                "work_days": workspace.working_days,
            },
            "tasks": [{
                "id": str(task.id),
                "title": task.title,
                "skill": task.required_skill.code if task.required_skill_id else None,
                "estimate_h": float(task.estimated_hours),
                "calibration": 1.0,
                "remaining_ratio": 1.0,
                "priority": cls.PRIORITIES[task.priority],
                "assignee_id": str(task.assignee_id) if task.assignee_id else None,
                "locked_assignee": False,
                "due": cls.serialize_datetime(task.due_at),
                "depends_on": grouped.get(task.id, []),
            } for task in tasks],
            "people": [{
                "id": str(member.id),
                "name": member.user.get_full_name() or member.user.email,
                "skills": OptimizerSelector.get_member_skills(member=member),
                "capacity_h_per_day": float(OptimizerSelector.get_member_capacity(member=member)["capacity_h_per_day"]),
                "busy_h": float(busy_hours.get(member.id, 0)),
                "absences": OptimizerSelector.get_member_absences(member=member),
            } for member in members],
            "options": {"reassign": True, "weights": {"slack": 50, "descendants": 30, "priority": 20}},
        }

    @staticmethod
    def parse_engine_error(output):
        details = output.get("details", {})
        if not isinstance(details, dict):
            details = {}
        return {
            "code": output.get("code", "unknown_engine_error"),
            "message": output.get("message", "Optimization engine failed."),
            "details": {**details, **{key: value for key, value in output.items() if key not in {"code", "message", "details"}}},
        }

    @staticmethod
    def reject_json_constant(value):
        raise ValueError(f"Non-finite JSON number: {value}")

    @classmethod
    def run(cls, *, command, payload):
        executable = getattr(settings, "CFENGINE_PATH", None)
        if not executable:
            raise OptimizerInternalError("CFENGINE_PATH is not configured.")
        timeout = getattr(settings, "CFENGINE_TIMEOUT", 10)
        started = time.monotonic()
        try:
            result = subprocess.run(
                [str(executable), command], input=json.dumps(payload, allow_nan=False),
                capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            logger.warning("Optimization engine timed out after %s seconds.", timeout)
            raise OptimizerTimeout({"code": "optimizer_timeout", "message": "Optimization exceeded the time limit."}) from exc
        except (OSError, ValueError, TypeError) as exc:
            logger.exception("Could not execute optimization engine.")
            raise OptimizerInternalError("Could not execute optimization engine.") from exc
        duration_ms = int((time.monotonic() - started) * 1000)
        try:
            output = json.loads(result.stdout, parse_constant=cls.reject_json_constant)
        except (ValueError, TypeError) as exc:
            logger.error("Invalid engine JSON; exit code: %s", result.returncode)
            raise OptimizerInternalError("Optimization engine returned invalid JSON.") from exc
        if not isinstance(output, dict):
            raise OptimizerInternalError("Optimization engine output must be an object.")
        if result.returncode == 0:
            return output, duration_ms
        error = cls.parse_engine_error(output)
        if result.returncode == 2:
            raise OptimizerDependencyCycle(cycle=error["details"].get("cycle", []), message=error["message"])
        if result.returncode == 3:
            logger.error("Optimization engine rejected Django input: %s", error)
            raise OptimizerInvalidInput(error)
        if result.returncode == 4:
            raise OptimizerInfeasible(error)
        logger.error("Unexpected optimizer exit code: %s", result.returncode)
        raise OptimizerInternalError({"code": "unexpected_engine_error", "message": "Optimization engine failed.", "exit_code": result.returncode})

    @staticmethod
    def to_task_plan(output):
        deadlines = {str(item["task_id"]): item["by"] for item in output.get("must_finish_by", [])}
        plan = []
        for item in output["schedule"]:
            task_id = str(item["task_id"])
            task_plan = {
                "task_id": task_id,
                "assignee_id": item["assignee_id"],
                "planned_start": item["start"],
                "planned_end": item["end"],
                "latest_start_at": item["latest_start"],
                "slack_hours": str(Decimal(str(item["slack_h"])).quantize(Decimal("0.01"))),
                "is_critical": item["critical"],
            }
            if task_id in deadlines:
                task_plan["due_at"] = deadlines[task_id]
            plan.append(task_plan)
        return plan

    @staticmethod
    def serialize_value(value):
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (Decimal, uuid.UUID)):
            return str(value)
        return value

    @classmethod
    def build_diff(cls, *, campaign, output):
        validated = OptimizationApplyService.validate_output(output={"tasks": cls.to_task_plan(output)})
        tasks = {str(task.id): task for task in campaign.tasks.filter(id__in=validated)}
        diff = []
        for task_id, data in validated.items():
            task = tasks.get(task_id)
            if task is None:
                raise OptimizerInternalError("Engine returned an unknown task.")
            changes = {}
            for field, value in data.items():
                previous = getattr(task, field)
                if field == "assignee_id" and previous is not None:
                    previous = str(previous)
                if previous != value:
                    changes[field] = {"old": cls.serialize_value(previous), "new": cls.serialize_value(value)}
            if changes:
                diff.append({"task_id": task_id, "changes": changes})
        return diff

    @classmethod
    def validate_engine_output(cls, *, payload, output):
        task_ids = {task["id"] for task in payload["tasks"]}
        member_ids = {member["id"] for member in payload["people"]}
        schedule_ids = [item["task_id"] for item in output["schedule"]]
        if len(schedule_ids) != len(set(schedule_ids)) or set(schedule_ids) != task_ids:
            raise OptimizerInternalError("Schedule does not match the input task set.")
        for item in output["schedule"]:
            if item["assignee_id"] is not None and item["assignee_id"] not in member_ids:
                raise OptimizerInternalError("Schedule contains an unknown assignee.")
            try:
                start = parse_datetime(item["start"])
                end = parse_datetime(item["end"])
                latest = parse_datetime(item["latest_start"])
                if any(value is None or timezone.is_naive(value) for value in (start, end, latest)) or start > end:
                    raise ValueError("Invalid schedule dates")
            except (ValueError, TypeError, OverflowError) as exc:
                raise OptimizerInternalError("Schedule contains an invalid date range.") from exc
        for field in ("order", "critical_path"):
            ids = output[field]
            if len(ids) != len(set(ids)) or not set(ids).issubset(task_ids):
                raise OptimizerInternalError(f"Engine returned invalid {field}.")
        if set(output["order"]) != task_ids:
            raise OptimizerInternalError("Engine order does not match input tasks.")
        deadline_ids = [item["task_id"] for item in output["must_finish_by"]]
        if len(deadline_ids) != len(set(deadline_ids)) or not set(deadline_ids).issubset(task_ids):
            raise OptimizerInternalError("Engine returned invalid task deadlines.")

    @classmethod
    def preview(cls, *, campaign, user):
        OptimizationApplyService.validate_permission(campaign=campaign, user=user)
        if campaign.is_archived:
            raise OptimizationConflict("Archived campaigns cannot be optimized.")
        initial_revision = campaign.revision
        payload = cls.build_input(campaign)
        cls.validate_schema(payload, settings.CFENGINE_INPUT_SCHEMA, input_schema=True)
        output, duration_ms = cls.run(command="optimize", payload=payload)
        cls.validate_schema(output, settings.CFENGINE_OUTPUT_SCHEMA)
        if not output["feasible"]:
            raise OptimizerInfeasible()
        cls.validate_engine_output(payload=payload, output=output)
        with transaction.atomic():
            locked_campaign = Campaign.objects.select_for_update().filter(pk=campaign.pk, is_archived=False).first()
            if locked_campaign is None or locked_campaign.revision != initial_revision:
                raise OptimizationConflict("Campaign changed during optimization. Please retry.")
            OptimizationApplyService.validate_permission(campaign=locked_campaign, user=user)
            try:
                diff = cls.build_diff(campaign=locked_campaign, output=output)
            except (ValidationError, InvalidOperation, ValueError, OverflowError) as exc:
                logger.exception("Engine plan cannot be represented by Django task fields.")
                raise OptimizerInternalError("Invalid optimizer task plan.") from exc
            try:
                makespan = Decimal(str(output["makespan_h"])).quantize(Decimal("0.01"))
                OptimizationRun._meta.get_field("makespan_hours").run_validators(makespan)
                OptimizationRun._meta.get_field("engine_version").run_validators(output["engine_version"])
                OptimizationRun._meta.get_field("duration_ms").run_validators(output.get("elapsed_ms", duration_ms))
            except (DjangoValidationError, InvalidOperation, ValueError, OverflowError) as exc:
                logger.exception("Engine metadata exceeds model field limits.")
                raise OptimizerInternalError("Invalid optimizer metadata.") from exc
            optimization_run = OptimizationRun.objects.create(
                campaign=locked_campaign, requested_by=user, input_json=payload,
                output_json=output, feasible=True, makespan_hours=makespan,
                risk=output["risk"], engine_version=output["engine_version"],
                duration_ms=output.get("elapsed_ms", duration_ms), campaign_revision=initial_revision,
            )
        return optimization_run, diff


class OptimizationApplyService:
    PLAN_FIELDS = {
        "planned_start",
        "planned_end",
        "latest_start_at",
        "is_critical",
        "slack_hours",
        "due_at",
    }

    DATETIME_FIELDS = {
        "planned_start",
        "planned_end",
        "latest_start_at",
        "due_at",
    }

    @staticmethod
    def validate_permission(*, campaign, user):
        if not user or not user.is_authenticated or not user.is_active:
            raise PermissionDenied("An active authenticated user is required.")

        membership = WorkspaceMember.objects.filter(
            workspace_id=campaign.workspace_id,
            user=user,
        ).first()

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
            raise ValidationError({
                field: "Expected an ISO 8601 datetime string."
            })

        try:
            parsed = parse_datetime(value)
        except (ValueError, OverflowError) as exc:
            raise ValidationError({field: "Invalid datetime."}) from exc

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
            raise ValidationError({
                field: "Expected a decimal number."
            })

        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError({
                field: "Expected a decimal number."
            })

        if not result.is_finite():
            raise ValidationError({
                field: "Expected a finite decimal number."
            })

        if field == "slack_hours" and result < 0:
            raise ValidationError({field: "Slack hours cannot be negative."})

        if result.as_tuple().exponent < -2:
            raise ValidationError({
                field: "Maximum 2 decimal places are allowed."
            })

        if abs(result) >= Decimal("100000000") or len(result.as_tuple().digits) > 10:
            raise ValidationError({
                field: "Maximum 10 digits are allowed."
            })

        return result

    @staticmethod
    def normalize_task_id(value):
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError):
            raise ValidationError({
                "task_id": "Invalid task UUID."
            })

    @staticmethod
    def normalize_assignee_id(value):
        if value is None:
            return None

        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError):
            raise ValidationError({
                "assignee_id": "Invalid workspace member UUID."
            })

    @classmethod
    def validate_plan_item(cls, *, item):
        if not isinstance(item, dict):
            raise ValidationError({
                "tasks": "Each task plan must be an object."
            })

        task_id = item.get("task_id")

        if task_id is None:
            raise ValidationError({
                "task_id": "This field is required."
            })

        allowed_fields = cls.PLAN_FIELDS | {
            "task_id",
            "assignee_id",
            "must_finish_by",
        }

        unknown = set(item) - allowed_fields

        if unknown:
            raise ValidationError({
                "tasks": ("Unsupported plan fields: "+ ", ".join(sorted(unknown)))
            })

        if "due_at" in item and "must_finish_by" in item:
            raise ValidationError({
                "due_at": ("Provide either due_at or must_finish_by, not both.")
            })

        data = {}

        for field in ("planned_start", "planned_end","latest_start_at",):
            if field in item:
                data[field] = cls.parse_datetime_value(field=field, value=item[field],)

        if "must_finish_by" in item:
            data["due_at"] = cls.parse_datetime_value(field="must_finish_by", value=item["must_finish_by"],)
        elif "due_at" in item:
            data["due_at"] = cls.parse_datetime_value(field="due_at", value=item["due_at"],)

        if "is_critical" in item:
            if not isinstance(item["is_critical"], bool):
                raise ValidationError({
                    "is_critical": "Expected a boolean."
                })

            data["is_critical"] = item["is_critical"]

        if "slack_hours" in item:
            data["slack_hours"] = cls.parse_decimal_value(field="slack_hours", value=item["slack_hours"],)

        if "assignee_id" in item:
            data["assignee_id"] = cls.normalize_assignee_id(item["assignee_id"])

        if (data.get("planned_start") is not None and data.get("planned_end") is not None and data["planned_start"] > data["planned_end"]):
            raise ValidationError({
                "planned_end": ("Planned end must be on or after planned start.")
            })

        return cls.normalize_task_id(task_id), data

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
    def validate_output(cls, *, output):
        if not isinstance(output, dict):
            raise ValidationError({
                "output_json": "Invalid optimization output."
            })

        plan_items = output.get("tasks")

        if not isinstance(plan_items, list):
            raise ValidationError({
                "output_json": "Expected a tasks list."
            })


        validated = {}

        for item in plan_items:
            task_id, data = cls.validate_plan_item(item=item)

            if task_id in validated:
                raise ValidationError({
                    "tasks": "Duplicate task ID."
                })

            validated[task_id] = data

        return validated

    @classmethod
    def validate_task(cls, *, task):
        try:
            task.full_clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise ValidationError(exc.message_dict)

            raise ValidationError(exc.messages)

    @classmethod
    @transaction.atomic
    def apply_optimization_run(cls, *, run, user, edits=None):
        run_id = run.id if isinstance(run, OptimizationRun) else run

        initial_run = OptimizationRun.objects.filter(id=run_id,).values("campaign_id",).first()

        if initial_run is None:
            raise NotFound("Optimization run not found.")

        campaign = Campaign.objects.select_for_update().filter(id=initial_run["campaign_id"],is_archived=False,).first()

        if campaign is None:
            raise NotFound("Campaign not found.")

        cls.validate_permission(campaign=campaign,user=user,)

        optimization_run = OptimizationRun.objects.select_for_update().get(id=run_id, campaign=campaign,)

        if optimization_run.applied_at is not None:
            return optimization_run

        if campaign.revision != optimization_run.campaign_revision:
            raise OptimizationConflict("The campaign was modified after the optimization preview. ""Generate a new preview.")

        if not optimization_run.feasible:
            raise ValidationError({
                "run": "An infeasible optimization plan cannot be applied."
            })

        engine_output = optimization_run.output_json
        if "schedule" in engine_output:
            engine_output = {"tasks": OptimizerService.to_task_plan(engine_output)}
        validated_plan = cls.validate_output(output=engine_output)

        validated_edits = cls.validate_edits(edits=edits)

        if not set(validated_edits).issubset(set(validated_plan)):
            raise ValidationError({
                "edits": ("Cannot edit tasks that are not included ""in the optimization plan.")
            })

        for task_id, data in validated_edits.items():
            validated_plan[task_id].update(data)

        tasks = {
            str(task.id): task
            for task in Task.objects.select_for_update().filter(campaign=campaign, id__in=validated_plan.keys(),).order_by("id")
        }

        if "schedule" in optimization_run.output_json:
            active_ids = {str(pk) for pk in Task.objects.filter(campaign=campaign).exclude(
                status__in=[TaskStatus.COMPLETED, TaskStatus.CANCELLED]
            ).values_list("id", flat=True)}
            if active_ids != set(validated_plan):
                raise OptimizationConflict("Task set changed since preview.")

        if len(tasks) != len(validated_plan):
            raise ValidationError({
                "tasks": ("One or more tasks do not belong to this campaign.")
            })

        member_ids = {
            data["assignee_id"]
            for data in validated_plan.values()
            if data.get("assignee_id") is not None
        }

        members = {
            str(member.id): member
            for member in WorkspaceMember.objects.filter(
                workspace_id=campaign.workspace_id,
                id__in=member_ids,
                user__is_active=True,
            ).exclude(role=WorkspaceMember.Role.GUEST)
        }

        if member_ids != set(members):
            raise ValidationError({
                "assignee_id": ("One or more assignees do not belong to this workspace.")
            })

        for task_id, data in validated_plan.items():
            task = tasks[task_id]
            changes = {}
            update_fields = set()

            if "assignee_id" in data:
                assignee_id = data["assignee_id"]

                new_assignee = (members[assignee_id] if assignee_id is not None else None)

                if task.assignee_id != (new_assignee.id if new_assignee else None):
                    changes["assignee_id"] = {
                        "old": (str(task.assignee_id) if task.assignee_id else None),
                        "new": assignee_id,
                    }
                    task.assignee = new_assignee
                    update_fields.add("assignee")

            for field, value in data.items():
                if field == "assignee_id":
                    continue

                previous = getattr(task, field)

                if previous != value:
                    changes[field] = {
                        "old": OptimizerService.serialize_value(previous),
                        "new": OptimizerService.serialize_value(value),
                    }

                    setattr(task, field, value)
                    update_fields.add(field)

            if not changes:
                continue

            if task.planned_start is not None and task.planned_end is not None and task.planned_start > task.planned_end:
                raise ValidationError({"planned_end": "Planned end must be on or after planned start."})
            cls.validate_task(task=task)

            task.save(update_fields=[*sorted(update_fields), "updated_at"])

            TaskActivityService.record(
                task=task,
                actor=user,
                action=TaskActivityType.UPDATED,
                metadata={
                    "source": "optimizer",
                    "optimization_run_id": str(optimization_run.id),
                    "changes": changes,
                },
            )

            if "assignee_id" in changes:
                TaskActivityService.record(
                    task=task, actor=user, action=TaskActivityType.ASSIGNED,
                    metadata={"previous_assignee_id": changes["assignee_id"]["old"],
                              "assignee_id": changes["assignee_id"]["new"],
                              "source": "optimizer"},
                )

        campaign.revision += 1
        campaign.save(update_fields=["revision", "updated_at"])

        optimization_run.applied_at = timezone.now()
        optimization_run.save(update_fields=["applied_at"])

        return optimization_run


class OptimizationHistoryService:

    @staticmethod
    def get_history(
        *,
        workspace,
        campaign_id,
        user,
        filters=None,
    ):
        campaign = OptimizerSelector.get_campaign(workspace=workspace, campaign_id=campaign_id,)

        if campaign is None:
            raise NotFound("Campaign not found.")

        OptimizationApplyService.validate_permission(campaign=campaign, user=user,)

        filters = filters or {}

        return OptimizerSelector.get_optimization_runs(
            workspace=workspace,
            campaign_id=campaign.id,
            risk=filters.get("risk"),
            feasible=filters.get("feasible"),
            applied=filters.get("applied"),
        )

    @staticmethod
    def get_details(*, workspace, run_id,user,):
        optimization_run = OptimizerSelector.get_optimization_run(workspace=workspace, run_id=run_id,)

        if optimization_run is None:
            raise NotFound("Optimization run not found.")

        OptimizationApplyService.validate_permission(campaign=optimization_run.campaign, user=user,)

        return optimization_run

    @staticmethod
    def is_applied(*, optimization_run):
        return optimization_run.applied_at is not None

    @staticmethod
    def is_stale(*, optimization_run):
        if optimization_run.applied_at is not None:
            return False

        return (optimization_run.campaign_revision != optimization_run.campaign.revision)



class CampaignScheduleService:

    @staticmethod
    def get_campaign(*, workspace, campaign_id, user,):
        campaign = OptimizerSelector.get_campaign(workspace=workspace, campaign_id=campaign_id,)

        if campaign is None:
            raise NotFound("Campaign not found.")

        membership = WorkspaceMember.objects.filter(
            workspace=campaign.workspace,
            user=user,
            user__is_active=True,
        ).first()

        if membership is None:
            raise NotFound("Campaign not found.")

        if membership.role not in {
            WorkspaceMember.Role.ADMIN,
            WorkspaceMember.Role.MANAGER,
        }:
            raise PermissionDenied("You cannot access the campaign schedule.")

        return campaign

    @staticmethod
    def is_task_scheduled(*, task):
        return (
            task.planned_start is not None
            and task.planned_end is not None
            and task.planned_start <= task.planned_end
        )

    @staticmethod
    def is_optimization_stale(*, campaign,optimization_run,):
        if optimization_run is None:
            return False

        expected_revision = (optimization_run.campaign_revision + 1)

        return (campaign.revision != expected_revision)

    @classmethod
    def get_schedule(cls, *, workspace, campaign_id, user, filters=None,):
        campaign = cls.get_campaign(workspace=workspace, campaign_id=campaign_id, user=user,)

        filters = filters or {}

        tasks = list(
            CampaignScheduleSelector.get_tasks(
                campaign=campaign,
                assignee_id=filters.get("assignee_id"),
                status=filters.get("status"),
                is_critical=filters.get("is_critical"),
            )
        )

        dependencies = list(CampaignScheduleSelector.get_dependencies(campaign=campaign,))

        task_ids = {task.id for task in tasks}

        visible_dependencies = [
            dependency
            for dependency in dependencies
            if (dependency.task_id in task_ids and dependency.depends_on_task_id in task_ids
            )
        ]

        scheduled_tasks = [task for task in tasks if cls.is_task_scheduled(task=task)]

        unscheduled_tasks = [task for task in tasks if not cls.is_task_scheduled(task=task)]

        critical_tasks = [task for task in tasks if task.is_critical]

        optimization_run = (OptimizerSelector.get_latest_applied_run(campaign=campaign,))

        start_dates = [task.planned_start for task in scheduled_tasks]

        end_dates = [task.planned_end for task in scheduled_tasks]

        return {
            "campaign_id": campaign.id,
            "campaign_revision": campaign.revision,
            "launch_at": campaign.launch_at,
            "optimization_run_id": (
                optimization_run.id
                if optimization_run is not None
                else None
            ),
            "optimization_stale": cls.is_optimization_stale(campaign=campaign, optimization_run=optimization_run,),
            "schedule_start": (min(start_dates) if start_dates else None),
            "schedule_end": (max(end_dates) if end_dates else None),
            "summary": {
                "total_tasks": len(tasks),
                "scheduled_tasks": len(scheduled_tasks),
                "unscheduled_tasks": len(unscheduled_tasks),
                "critical_tasks": len(critical_tasks),
                "total_dependencies": len(visible_dependencies),
            },
            "tasks": tasks,
            "dependencies": visible_dependencies,
            "unscheduled_task_ids": [task.id for task in unscheduled_tasks],
        }

    @classmethod
    def get_critical_path(cls, *, workspace, campaign_id, user,):
        campaign = cls.get_campaign(workspace=workspace, campaign_id=campaign_id, user=user,)

        optimization_run = (OptimizerSelector.get_latest_applied_run(campaign=campaign,))

        if optimization_run is None:
            return {
                "campaign_id": campaign.id,
                "campaign_revision": campaign.revision,
                "optimization_run_id": None,
                "optimization_revision": None,
                "applied_at": None,
                "available": False,
                "stale": False,
                "risk": None,
                "makespan_hours": None,
                "critical_path": [],
                "tasks": [],
                "missing_task_ids": [],
            }

        output = optimization_run.output_json

        critical_path_ids = [
            str(task_id)
            for task_id in output.get(
                "critical_path",
                [],
            )
        ]

        tasks = CampaignScheduleSelector.get_tasks(campaign=campaign,).filter(id__in=critical_path_ids,)

        task_map = {str(task.id): task for task in tasks}

        ordered_tasks = [task_map[task_id] for task_id in critical_path_ids if task_id in task_map]

        missing_task_ids = [task_id for task_id in critical_path_ids if task_id not in task_map]

        stale = (
            cls.is_optimization_stale(campaign=campaign, optimization_run=optimization_run,)
            or bool(missing_task_ids)
            or any(not task.is_critical for task in ordered_tasks)
        )

        return {
            "campaign_id": campaign.id,
            "campaign_revision": campaign.revision,
            "optimization_run_id": optimization_run.id,
            "optimization_revision": (optimization_run.campaign_revision),
            "applied_at": optimization_run.applied_at,
            "available": "critical_path" in output,
            "stale": stale,
            "risk": optimization_run.risk,
            "makespan_hours": (optimization_run.makespan_hours),
            "critical_path": critical_path_ids,
            "tasks": ordered_tasks,
            "missing_task_ids": missing_task_ids,
        }


def apply_optimization_run(run, user, edits=None):
    return OptimizationApplyService.apply_optimization_run(run=run, user=user,edits=edits,)