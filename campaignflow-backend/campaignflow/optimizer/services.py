import json
import subprocess
import time
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import APIException, ValidationError

from campaignflow.campaigns.models import Campaign
from campaignflow.optimizer.models import OptimizationRun
from campaignflow.optimizer.selectors import OptimizerSelector
from campaignflow.tasks.enums import TaskPriority
from campaignflow.tasks.models import Task
from campaignflow.tasks.selectors import TaskWorkloadSelector
from campaignflow.organization.models import WorkspaceMember


class OptimizerTimeout(APIException):
    status_code = 503
    default_detail = "Optimization engine timed out."
    default_code = "optimizer_timeout"


class OptimizerInternalError(APIException):
    status_code = 500
    default_detail = "Optimization engine failed."
    default_code = "optimizer_error"


class OptimizerUnprocessable(APIException):
    status_code = 422
    default_detail = "Optimization cannot be completed."
    default_code = "optimizer_unprocessable"


class OptimizerDependencyCycle(OptimizerUnprocessable):
    default_detail = "Circular dependency detected."
    default_code = "dependency_cycle"

    def __init__(self, cycle=None, message=None):
        super().__init__({
            "code": "dependency_cycle",
            "message": message or self.default_detail,
            "cycle": cycle or [],
        })


class OptimizerInfeasible(OptimizerUnprocessable):
    default_detail = "No feasible optimization plan."
    default_code = "optimizer_infeasible"


class OptimizerInvalidInput(OptimizerInternalError):
    default_detail = "Optimization engine rejected the input."
    default_code = "optimizer_invalid_input"


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
    def validate_schema(*, payload, schema_path, input_schema=False):
        try:
            from jsonschema import Draft202012Validator, FormatChecker
            from jsonschema.exceptions import SchemaError

            with open(schema_path, encoding="utf-8") as file:
                schema = json.load(file)

            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
            errors = sorted(validator.iter_errors(payload), key=lambda error: str(error.path))

            if errors:
                message = errors[0].message
                if input_schema:
                    raise OptimizerInternalError({
                        "code": "invalid_optimizer_input",
                        "message": message,
                    })
                raise OptimizerInternalError({
                    "code": "invalid_optimizer_output",
                    "message": message,
                })

        except (ImportError, OSError, json.JSONDecodeError, SchemaError) as exc:
            raise OptimizerInternalError("Optimization JSON schema is unavailable or invalid.") from exc

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
        tasks = OptimizerSelector.get_tasks(campaign=campaign)
        task_ids = {task.id for task in tasks}
        dependencies = OptimizerSelector.get_dependencies(campaign=campaign, task_ids=task_ids)
        members = OptimizerSelector.get_members(workspace=campaign.workspace)
        dependencies_by_task = cls.get_dependencies_by_task(dependencies)

        if campaign.launch_at is None:
            raise ValidationError({"launch_at": "Campaign launch date is required for optimization."})

        now = timezone.now()

        if campaign.launch_at <= now:
            raise ValidationError({"launch_at": "Campaign launch date must be in the future."})

        workspace_tz = ZoneInfo(campaign.workspace.timezone)
        busy_hours = TaskWorkloadSelector.get_optimizer_busy_hours(
            workspace=campaign.workspace,
            campaign=campaign,
            start_date=timezone.localtime(now, workspace_tz).date(),
            end_date=timezone.localtime(campaign.launch_at, workspace_tz).date(),
            member_ids=[member.id for member in members],
        )

        task_payload = []

        for task in tasks:
            task_payload.append({
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
                "depends_on": dependencies_by_task.get(task.id, []),
            })

        people_payload = []

        for member in members:
            if member.role == member.Role.GUEST:
                continue

            skills = OptimizerSelector.get_member_skills(member=member)
            capacity = OptimizerSelector.get_member_capacity(member=member)
            absences = OptimizerSelector.get_member_absences(member=member)

            people_payload.append({
                "id": str(member.id),
                "name": member.user.get_full_name() or member.user.email,
                "skills": skills,
                "capacity_h_per_day": float(capacity["capacity_h_per_day"]),
                "busy_h": float(busy_hours.get(member.id, 0)),
                "absences": absences,
            })

        workspace = campaign.workspace

        return {
            "campaign_id": str(campaign.id),
            "now": cls.serialize_datetime(timezone.localtime(now, workspace_tz)),
            "deadline": cls.serialize_datetime(timezone.localtime(campaign.launch_at, workspace_tz)),
            "calendar": {
                "hours_per_day": float(workspace.working_hours_per_day),
                "day_start": "09:00",
                "work_days": workspace.working_days,
            },
            "tasks": task_payload,
            "people": people_payload,
            "options": {
                "reassign": True,
                "weights": {
                    "slack": 50,
                    "descendants": 30,
                    "priority": 20,
                },
            },
        }

    @staticmethod
    def parse_engine_error(output):
        if not isinstance(output, dict):
            return {
                "code": "unknown_engine_error",
                "message": "Optimization engine returned an invalid error response.",
            }

        return {
            "code": output.get("code", "unknown_engine_error"),
            "message": output.get("message", "Optimization engine failed."),
            "details": output.get("details", {}),
        }

    @classmethod
    def run(cls, *, command, payload):
        executable = getattr(settings, "CFENGINE_PATH", None)
        if not executable:
            raise OptimizerInternalError("CFENGINE_PATH is not configured.")

        timeout = getattr(settings, "CFENGINE_TIMEOUT", 10)
        started = time.monotonic()

        try:
            result = subprocess.run(
                [str(executable), *command],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OptimizerTimeout("Optimization exceeded the time limit.") from exc
        except OSError as exc:
            raise OptimizerInternalError("Could not start the optimization engine.") from exc

        duration_ms = int((time.monotonic() - started) * 1000)

        try:
            output = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError) as exc:
            raise OptimizerInternalError("Engine returned invalid JSON.") from exc

        if not isinstance(output, dict):
            raise OptimizerInternalError("Engine output must be a JSON object.")

        if result.returncode == 2:
            details = output.get("details", {})
            cycle = output.get("cycle", []) or (details.get("cycle", []) if isinstance(details, dict) else [])
            raise OptimizerDependencyCycle(cycle=cycle, message=output.get("message"))

        if result.returncode == 3:
            raise OptimizerInvalidInput(cls.parse_engine_error(output))

        if result.returncode == 4:
            raise OptimizerInfeasible(cls.parse_engine_error(output))

        if result.returncode != 0:
            raise OptimizerInternalError({
                **cls.parse_engine_error(output),
                "exit_code": result.returncode,
            })

        return output, duration_ms

    @staticmethod
    def normalize_datetime(value):
        if value is None:
            return None

        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = parse_datetime(value)

        if parsed is None:
            return value

        if timezone.is_aware(parsed):
            parsed = parsed.astimezone(ZoneInfo("UTC"))

        return parsed.isoformat()

    @classmethod
    def normalize_value(cls, field, value):
        if value is None:
            return None

        if field in {"planned_start", "planned_end", "latest_start_at", "due_at"}:
            return cls.normalize_datetime(value)

        if field == "slack_hours":
            return Decimal(str(value))

        if field == "assignee_id":
            return str(value)

        return value

    @staticmethod
    def to_task_plan(output):
        deadlines = {
            item["task_id"]: item["by"]
            for item in output.get("must_finish_by", [])
        }

        plan = []

        for item in output.get("schedule", []):
            task_id = item["task_id"]

            task_plan = {
                "task_id": task_id,
                "assignee_id": item["assignee_id"],
                "planned_start": item["start"],
                "planned_end": item["end"],
                "latest_start_at": item["latest_start"],
                "slack_hours": item["slack_h"],
                "is_critical": item["critical"],
            }

            if task_id in deadlines:
                task_plan["due_at"] = deadlines[task_id]

            plan.append(task_plan)

        return plan

    @classmethod
    def build_diff(cls, *, campaign, output):
        plan = cls.to_task_plan(output)
        task_ids = [item["task_id"] for item in plan]
        tasks = {str(task.id): task for task in campaign.tasks.filter(id__in=task_ids)}
        diff = []

        for item in plan:
            task = tasks.get(item["task_id"])
            if task is None:
                continue

            changes = {}

            for field, value in item.items():
                if field == "task_id":
                    continue

                previous = getattr(task, field, None)

                if cls.normalize_value(field, previous) != cls.normalize_value(field, value):
                    changes[field] = {
                        "old": str(previous) if previous is not None else None,
                        "new": value,
                    }

            if changes:
                diff.append({"task_id": item["task_id"], "changes": changes})

        return diff

    @classmethod
    def preview(cls, *, campaign, user):
        OptimizationApplyService.validate_permission(campaign=campaign, user=user)

        payload = cls.build_input(campaign)
        input_schema = getattr(settings, "CFENGINE_INPUT_SCHEMA", None)
        output_schema = getattr(settings, "CFENGINE_OUTPUT_SCHEMA", None)

        if input_schema:
            cls.validate_schema(payload=payload, schema_path=input_schema, input_schema=True)

        output, duration_ms = cls.run(command=["optimize"], payload=payload)

        if output_schema:
            cls.validate_schema(payload=output, schema_path=output_schema)

        if not output.get("feasible", False):
            raise OptimizerInfeasible("The engine returned an infeasible optimization plan.")

        plan = cls.to_task_plan(output)
        OptimizationApplyService.validate_output(output={"tasks": plan})

        with transaction.atomic():
            locked_campaign = Campaign.objects.select_for_update().get(pk=campaign.pk)

            if locked_campaign.revision != campaign.revision:
                raise OptimizationConflict("Campaign changed during optimization. Please retry.")

            diff = cls.build_diff(campaign=locked_campaign, output=output)

            optimization_run = OptimizationRun.objects.create(
                campaign=locked_campaign,
                requested_by=user,
                input_json=payload,
                output_json=output,
                feasible=True,
                makespan_hours=output["makespan_h"],
                risk=output["risk"],
                engine_version=output["engine_version"],
                duration_ms=output.get("elapsed_ms", duration_ms),
                campaign_revision=locked_campaign.revision,
            )

        return optimization_run, diff


class OptimizationConflict(APIException):
    status_code = 409
    default_detail = "Optimization conflicts with the current campaign state."
    default_code = "optimization_conflict"


class OptimizationApplyService:
    PLAN_FIELDS = {
        "assignee_id", "planned_start", "planned_end", "latest_start_at",
        "slack_hours", "is_critical", "due_at",
    }
    DATE_FIELDS = {"planned_start", "planned_end", "latest_start_at", "due_at"}

    @staticmethod
    def validate_permission(*, campaign, user):
        if not user or not user.is_authenticated:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Authentication is required.")
        permitted = WorkspaceMember.objects.filter(
            workspace=campaign.workspace,
            user=user,
            role__in=[WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.MANAGER],
        ).exists()
        if not permitted:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only workspace admins and managers can optimize campaigns.")

    @classmethod
    def validate_output(cls, *, output):
        plan = output.get("tasks")
        if not isinstance(plan, list):
            raise ValidationError({"tasks": "Expected a list of planned tasks."})
        seen = set()
        for index, item in enumerate(plan):
            if not isinstance(item, dict) or not item.get("task_id"):
                raise ValidationError({"tasks": f"Invalid task at index {index}."})
            task_id = str(item["task_id"])
            if task_id in seen:
                raise ValidationError({"tasks": f"Duplicate task: {task_id}."})
            seen.add(task_id)
            if "planned_start" in item and "planned_end" in item:
                start = cls.parse_date(item["planned_start"])
                end = cls.parse_date(item["planned_end"])
                if start and end and start > end:
                    raise ValidationError({"tasks": f"End precedes start for {task_id}."})
        return plan

    @staticmethod
    def parse_date(value):
        if value is None or isinstance(value, datetime):
            return value
        parsed = parse_datetime(value) if isinstance(value, str) else None
        if parsed is None or timezone.is_naive(parsed):
            raise ValidationError({"datetime": "Expected an ISO 8601 timezone-aware datetime."})
        return parsed

    @classmethod
    def merge_edits(cls, *, plan, edits):
        if edits is None:
            return plan
        indexed = {str(item["task_id"]): dict(item) for item in plan}
        for edit in edits:
            task_id = str(edit["task_id"])
            if task_id not in indexed:
                raise ValidationError({"edits": f"Task {task_id} is not in the optimization plan."})
            if "must_finish_by" in edit:
                if "due_at" in edit:
                    raise ValidationError({"edits": "Use due_at or must_finish_by, not both."})
                edit = {**edit, "due_at": edit["must_finish_by"]}
            for key, value in edit.items():
                if key in cls.PLAN_FIELDS:
                    indexed[task_id][key] = value
        return list(indexed.values())

    @classmethod
    def apply_optimization_run(cls, *, run, user, edits=None):
        from campaignflow.tasks.enums import TaskStatus

        with transaction.atomic():
            optimization_run = OptimizationRun.objects.select_related(
                "campaign", "campaign__workspace"
            ).select_for_update().filter(pk=run).first()
            if optimization_run is None:
                from rest_framework.exceptions import NotFound
                raise NotFound("Optimization run not found.")

            campaign = Campaign.objects.select_for_update().get(pk=optimization_run.campaign_id)
            cls.validate_permission(campaign=campaign, user=user)

            if campaign.is_archived:
                raise OptimizationConflict("Archived campaigns cannot be optimized.")
            if optimization_run.applied_at is not None:
                raise OptimizationConflict("Optimization run has already been applied.")
            if not optimization_run.feasible:
                raise ValidationError({"run": "An infeasible optimization cannot be applied."})
            if campaign.revision != optimization_run.campaign_revision:
                raise OptimizationConflict("Campaign changed since preview. Run optimization again.")

            output = optimization_run.output_json
            plan = OptimizerService.to_task_plan(output)
            plan = cls.merge_edits(plan=plan, edits=edits)
            cls.validate_output(output={"tasks": plan})

            tasks = {
                str(task.id): task
                for task in Task.objects.select_for_update().filter(campaign=campaign)
            }
            active_ids = {
                task_id for task_id, task in tasks.items()
                if task.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
            }
            plan_ids = {str(item["task_id"]) for item in plan}
            if plan_ids != active_ids:
                raise OptimizationConflict("Task set changed since preview. Run optimization again.")

            member_ids = {
                str(item["assignee_id"])
                for item in plan if item.get("assignee_id") is not None
            }
            valid_member_ids = {
                str(pk) for pk in WorkspaceMember.objects.filter(
                    workspace=campaign.workspace, user__is_active=True,
                    id__in=member_ids,
                ).values_list("id", flat=True)
            }
            if member_ids != valid_member_ids:
                raise ValidationError({"assignee_id": "Assignee must be an active workspace member."})

            updated_tasks = []
            for item in plan:
                task = tasks[str(item["task_id"])]
                changed = False
                for field in cls.PLAN_FIELDS:
                    if field not in item:
                        continue
                    value = item[field]
                    if field in cls.DATE_FIELDS:
                        value = cls.parse_date(value)
                    elif field == "slack_hours" and value is not None:
                        value = Decimal(str(value))
                    elif field == "assignee_id" and value is not None:
                        from uuid import UUID
                        value = UUID(str(value))
                    if getattr(task, field) != value:
                        setattr(task, field, value)
                        changed = True
                if changed:
                    updated_tasks.append(task)

            if updated_tasks:
                Task.objects.bulk_update(updated_tasks, sorted(cls.PLAN_FIELDS))

            campaign.revision += 1
            campaign.save(update_fields=["revision"])
            optimization_run.applied_at = timezone.now()
            optimization_run.save(update_fields=["applied_at"])
            return optimization_run


def apply_optimization_run(*, run, user, edits=None):
    return OptimizationApplyService.apply_optimization_run(
        run=run, user=user, edits=edits,
    )