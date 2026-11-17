from django.db.models import Prefetch

from campaignflow.campaigns.models import Campaign
from campaignflow.optimizer.models import OptimizationRun
from campaignflow.organization.models import (
    WorkspaceMember,
    WorkspaceMemberSkill,
    WorkspaceMemberTimeOff,
)
from campaignflow.tasks.enums import TaskStatus
from campaignflow.tasks.models import Task, TaskDependency


class OptimizerSelector:
    EXCLUDED_STATUSES = {TaskStatus.COMPLETED, TaskStatus.CANCELLED}

    @staticmethod
    def get_campaign(*, workspace, campaign_id):
        return Campaign.objects.filter(
            id=campaign_id, workspace=workspace, is_archived=False
        ).select_related("workspace").first()

    @classmethod
    def get_tasks(cls, *, campaign):
        return list(
            Task.objects.filter(campaign=campaign)
            .exclude(status__in=cls.EXCLUDED_STATUSES)
            .select_related("required_skill", "assignee")
            .order_by("id")
        )

    @staticmethod
    def get_dependencies(*, campaign, task_ids):
        return list(
            TaskDependency.objects.filter(
                task__campaign=campaign,
                depends_on_task__campaign=campaign,
                task_id__in=task_ids,
                depends_on_task_id__in=task_ids,
            ).order_by("id")
        )

    @staticmethod
    def get_members(*, workspace):
        return list(
            WorkspaceMember.objects.filter(workspace=workspace, user__is_active=True)
            .exclude(role=WorkspaceMember.Role.GUEST)
            .select_related("user", "workspace", "availability")
            .prefetch_related(
                Prefetch(
                    "member_skills",
                    queryset=WorkspaceMemberSkill.objects.select_related("skill"),
                ),
                Prefetch(
                    "time_off_periods",
                    queryset=WorkspaceMemberTimeOff.objects.order_by("start_date", "end_date"),
                ),
            )
            .order_by("id")
        )

    @staticmethod
    def get_member_skills(*, member):
        return [member_skill.skill.code for member_skill in member.member_skills.all()]

    @staticmethod
    def get_member_capacity(*, member):
        try:
            availability = member.availability
        except WorkspaceMember.availability.RelatedObjectDoesNotExist:
            availability = None

        if (availability is not None and availability.working_hours_per_day is not None):
            hours = availability.working_hours_per_day
        else:
            hours = member.workspace.working_hours_per_day

        return {"capacity_h_per_day": hours}

    @staticmethod
    def get_member_absences(*, member):
        return [
            {
                "start_date": period.start_date.isoformat(),
                "end_date": period.end_date.isoformat(),
            }
            for period in member.time_off_periods.all()
        ]

    # CF-054: Optimization history

    @staticmethod
    def get_optimization_runs(
        *,
        workspace,
        campaign_id,
        risk=None,
        feasible=None,
        applied=None,
    ):
        queryset = (
            OptimizationRun.objects.filter(
                campaign_id=campaign_id,
                campaign__workspace=workspace,
                campaign__is_archived=False,
            )
            .select_related("campaign","requested_by",)
        )

        if risk is not None:
            queryset = queryset.filter(risk=risk,)

        if feasible is not None:
            queryset = queryset.filter(feasible=feasible,)

        if applied is not None:
            queryset = queryset.filter(applied_at__isnull=not applied,)

        return queryset.order_by("-created_at","-id",)

    @staticmethod
    def get_optimization_run(*, workspace, run_id,):
        return (
            OptimizationRun.objects.filter(
                id=run_id,
                campaign__workspace=workspace,
                campaign__is_archived=False,
            )
            .select_related("campaign", "campaign__workspace", "requested_by",)
            .first()
        )
