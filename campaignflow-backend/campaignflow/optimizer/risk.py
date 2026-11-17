from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from campaignflow.optimizer.models import Risk
from campaignflow.tasks.enums import TaskStatus


class CampaignRiskAnalyzer:
    DEADLINE_THRESHOLD = timedelta(hours=48)
    SLACK_THRESHOLD = Decimal("2.00")
    EXCLUDED_STATUSES = {TaskStatus.COMPLETED, TaskStatus.CANCELLED}

    RISK_PRIORITY = {
        Risk.LOW: 1,
        Risk.MEDIUM: 2,
        Risk.HIGH: 3,
        Risk.CRITICAL: 4,
    }

    @staticmethod
    def is_scheduled(task):
        return (
            task.planned_start is not None
            and task.planned_end is not None
            and task.planned_start <= task.planned_end
        )

    @staticmethod
    def create_factor(*, code, risk, message, recommendation, task_ids=None):
        task_ids = sorted(set(task_ids or []), key=str)

        return {
            "code": code,
            "risk": risk,
            "message": message,
            "recommendation": recommendation,
            "task_ids": task_ids,
            "affected_tasks_count": len(task_ids),
        }

    @classmethod
    def get_overall_risk(cls, *, factors):
        return max(
            (factor["risk"] for factor in factors),
            key=lambda risk: cls.RISK_PRIORITY[risk],
            default=Risk.LOW,
        )

    @classmethod
    def analyze(cls, *, campaign, tasks, dependencies, optimization_run,
                optimization_stale, now):
        tasks = list(tasks)
        active_tasks = [task for task in tasks if task.status not in cls.EXCLUDED_STATUSES]
        active_task_ids = {task.id for task in active_tasks}
        task_map = {task.id: task for task in tasks}

        overdue_tasks = []
        approaching_deadline_tasks = []
        critical_overdue_tasks = []
        unscheduled_tasks = []
        unassigned_tasks = []
        critical_low_slack_tasks = []

        blockers_by_task = defaultdict(set)
        factors = []

        for task in active_tasks:
            if not cls.is_scheduled(task):
                unscheduled_tasks.append(task.id)

            if task.assignee_id is None:
                unassigned_tasks.append(task.id)

            if task.due_at is not None:
                if task.due_at < now:
                    overdue_tasks.append(task.id)

                    if task.is_critical:
                        critical_overdue_tasks.append(task.id)

                elif task.due_at <= now + cls.DEADLINE_THRESHOLD:
                    approaching_deadline_tasks.append(task.id)

            if (
                task.is_critical
                and task.slack_hours is not None
                and task.slack_hours <= cls.SLACK_THRESHOLD
            ):
                critical_low_slack_tasks.append(task.id)

        for dependency in dependencies:
            if dependency.task_id not in active_task_ids:
                continue

            predecessor = task_map.get(dependency.depends_on_task_id)

            if predecessor is not None and predecessor.status != TaskStatus.COMPLETED:
                blockers_by_task[dependency.task_id].add(predecessor.id)

        blocked_tasks = list(blockers_by_task)
        critical_blocked_tasks = [pk for pk in blocked_tasks if task_map[pk].is_critical]
        regular_blocked_tasks = [pk for pk in blocked_tasks if not task_map[pk].is_critical]
        regular_overdue_tasks = [pk for pk in overdue_tasks if not task_map[pk].is_critical]

        scheduled_tasks = [task for task in active_tasks if cls.is_scheduled(task)]
        schedule_end = max((task.planned_end for task in scheduled_tasks), default=None)

        if campaign.launch_at is not None and campaign.launch_at < now and active_tasks:
            factors.append(cls.create_factor(
                code="CAMPAIGN_OVERDUE",
                risk=Risk.CRITICAL,
                message="The campaign deadline has passed while unfinished tasks remain.",
                recommendation="Review the campaign deadline and prioritize unfinished tasks.",
                task_ids=active_task_ids,
            ))

        if (
            campaign.launch_at is not None
            and schedule_end is not None
            and schedule_end > campaign.launch_at
        ):
            exceeding_tasks = [
                task.id for task in scheduled_tasks
                if task.planned_end > campaign.launch_at
            ]

            factors.append(cls.create_factor(
                code="SCHEDULE_EXCEEDS_DEADLINE",
                risk=Risk.CRITICAL,
                message="The planned completion date exceeds the campaign deadline.",
                recommendation="Run a new optimization and review task assignments.",
                task_ids=exceeding_tasks,
            ))

        if critical_overdue_tasks:
            factors.append(cls.create_factor(
                code="CRITICAL_TASK_OVERDUE",
                risk=Risk.CRITICAL,
                message="Critical tasks are overdue.",
                recommendation="Prioritize overdue critical tasks.",
                task_ids=critical_overdue_tasks,
            ))

        if regular_overdue_tasks:
            factors.append(cls.create_factor(
                code="TASK_OVERDUE",
                risk=Risk.HIGH,
                message="Unfinished tasks are overdue.",
                recommendation="Review task deadlines and progress.",
                task_ids=regular_overdue_tasks,
            ))

        if critical_blocked_tasks:
            factors.append(cls.create_factor(
                code="CRITICAL_TASK_BLOCKED",
                risk=Risk.HIGH,
                message="Critical tasks have unfinished dependencies.",
                recommendation="Resolve dependencies blocking critical tasks.",
                task_ids=critical_blocked_tasks,
            ))

        if critical_low_slack_tasks:
            factors.append(cls.create_factor(
                code="CRITICAL_LOW_SLACK",
                risk=Risk.HIGH,
                message="Critical tasks have insufficient slack hours.",
                recommendation="Monitor critical tasks and avoid additional delays.",
                task_ids=critical_low_slack_tasks,
            ))

        if optimization_stale:
            factors.append(cls.create_factor(
                code="STALE_OPTIMIZATION",
                risk=Risk.MEDIUM,
                message="The latest applied optimization is outdated.",
                recommendation="Generate a new optimization preview.",
            ))

        if regular_blocked_tasks:
            factors.append(cls.create_factor(
                code="TASK_BLOCKED",
                risk=Risk.MEDIUM,
                message="Tasks have unfinished dependencies.",
                recommendation="Complete prerequisite tasks first.",
                task_ids=regular_blocked_tasks,
            ))

        if approaching_deadline_tasks:
            factors.append(cls.create_factor(
                code="DEADLINE_APPROACHING",
                risk=Risk.MEDIUM,
                message="Task deadlines are approaching within 48 hours.",
                recommendation="Review task progress and remaining work.",
                task_ids=approaching_deadline_tasks,
            ))

        if unscheduled_tasks:
            factors.append(cls.create_factor(
                code="UNSCHEDULED_TASK",
                risk=Risk.MEDIUM,
                message="Unfinished tasks have no valid schedule.",
                recommendation="Schedule unfinished tasks or run campaign optimization.",
                task_ids=unscheduled_tasks,
            ))

        if unassigned_tasks:
            factors.append(cls.create_factor(
                code="UNASSIGNED_TASK",
                risk=Risk.MEDIUM,
                message="Unfinished tasks have no assignee.",
                recommendation="Assign available team members to unfinished tasks.",
                task_ids=unassigned_tasks,
            ))

        if campaign.launch_at is None:
            factors.append(cls.create_factor(
                code="NO_CAMPAIGN_DEADLINE",
                risk=Risk.MEDIUM,
                message="The campaign has no launch date.",
                recommendation="Define a campaign deadline.",
            ))

        if not tasks:
            factors.append(cls.create_factor(
                code="NO_CAMPAIGN_TASKS",
                risk=Risk.MEDIUM,
                message="The campaign has no tasks to analyze.",
                recommendation="Create campaign tasks before evaluating scheduling risks.",
            ))

        factors.sort(key=lambda factor: (-cls.RISK_PRIORITY[factor["risk"]], factor["code"]))

        completed_count = sum(task.status == TaskStatus.COMPLETED for task in tasks)
        cancelled_count = sum(task.status == TaskStatus.CANCELLED for task in tasks)
        progress_total = len(tasks) - cancelled_count

        progress_percentage = (
            round(completed_count / progress_total * 100, 2)
            if progress_total else None
        )

        remaining_hours = (
            round((campaign.launch_at - now).total_seconds() / 3600, 2)
            if campaign.launch_at is not None else None
        )

        affected_task_ids = {
            task_id
            for factor in factors
            for task_id in factor["task_ids"]
        }

        critical_tasks = [task for task in active_tasks if task.is_critical]

        missing_due_date_count = sum(task.due_at is None for task in active_tasks)

        data_complete = (
            bool(tasks)
            and campaign.launch_at is not None
            and not unscheduled_tasks
            and not missing_due_date_count
            and not unassigned_tasks
        )

        return {
            "campaign_id": campaign.id,
            "campaign_revision": campaign.revision,
            "analyzed_at": now,
            "risk": cls.get_overall_risk(factors=factors),
            "data_complete": data_complete,
            "launch_at": campaign.launch_at,
            "remaining_hours": remaining_hours,
            "planned_completion_at": schedule_end,
            "progress_percentage": progress_percentage,
            "optimization": {
                "run_id": optimization_run.id if optimization_run else None,
                "risk": optimization_run.risk if optimization_run else None,
                "applied_at": optimization_run.applied_at if optimization_run else None,
                "available": optimization_run is not None,
                "stale": optimization_stale,
            },
            "summary": {
                "total_tasks": len(tasks),
                "active_tasks": len(active_tasks),
                "completed_tasks": completed_count,
                "cancelled_tasks": cancelled_count,
                "scheduled_tasks": len(scheduled_tasks),
                "unscheduled_tasks": len(unscheduled_tasks),
                "unassigned_tasks": len(unassigned_tasks),
                "overdue_tasks": len(overdue_tasks),
                "approaching_deadline_tasks": len(approaching_deadline_tasks),
                "blocked_tasks": len(blocked_tasks),
                "critical_tasks": len(critical_tasks),
                "critical_overdue_tasks": len(critical_overdue_tasks),
                "critical_blocked_tasks": len(critical_blocked_tasks),
                "critical_low_slack_tasks": len(critical_low_slack_tasks),
                "affected_tasks": len(affected_task_ids),
                "risk_factors": len(factors),
            },
            "factors": factors,
            "blocked_tasks": [
                {
                    "task_id": task_id,
                    "blocked_by": sorted(blocker_ids, key=str),
                    "is_critical": task_map[task_id].is_critical,
                }
                for task_id, blocker_ids in sorted(
                    blockers_by_task.items(), key=lambda item: str(item[0])
                )
            ],
            "recommendations": list(dict.fromkeys(
                factor["recommendation"] for factor in factors
            )),
        }