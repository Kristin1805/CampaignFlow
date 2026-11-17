from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from itertools import combinations

from campaignflow.organization.enums import WorkloadStatus


class WorkloadCalculator:
    ZERO = Decimal("0.00")
    PRECISION = Decimal("0.01")
    BALANCED_THRESHOLD = Decimal("50")
    FULLY_BOOKED_THRESHOLD = Decimal("90")
    OVERLOADED_THRESHOLD = Decimal("100")

    @classmethod
    def round_hours(cls, value):
        return Decimal(str(value)).quantize(cls.PRECISION, rounding=ROUND_HALF_UP)

    @staticmethod
    def get_dates(start_date, end_date):
        current_date = start_date

        while current_date <= end_date:
            yield current_date
            current_date += timedelta(days=1)

    @staticmethod
    def is_absent(day, absences):
        return any(start_date <= day <= end_date for start_date, end_date in absences)

    @classmethod
    def get_daily_capacity(cls, *, day, working_days, hours_per_day, absences):
        if day.weekday() not in working_days or cls.is_absent(day, absences):
            return cls.ZERO

        return max(cls.ZERO, Decimal(str(hours_per_day)))

    @classmethod
    def get_remaining_task_hours(cls, task):
        estimated = Decimal(str(task.estimated_hours or 0))
        actual = Decimal(str(task.actual_hours or 0))

        return max(cls.ZERO, estimated - actual)

    @staticmethod
    def is_scheduled(task):
        return (
            task.planned_start is not None
            and task.planned_end is not None
            and task.planned_start < task.planned_end
        )

    @classmethod
    def get_utilization(cls, *, capacity, workload):
        if capacity <= cls.ZERO:
            return None

        return cls.round_hours(workload / capacity * 100)

    @classmethod
    def get_status(cls, *, capacity, workload):
        if capacity <= cls.ZERO:
            return WorkloadStatus.OVERLOADED if workload > cls.ZERO else WorkloadStatus.UNAVAILABLE

        utilization = workload / capacity * 100

        if utilization > cls.OVERLOADED_THRESHOLD:
            return WorkloadStatus.OVERLOADED

        if utilization >= cls.FULLY_BOOKED_THRESHOLD:
            return WorkloadStatus.FULLY_BOOKED

        if utilization >= cls.BALANCED_THRESHOLD:
            return WorkloadStatus.BALANCED

        return WorkloadStatus.AVAILABLE

    @classmethod
    def build_metrics(cls, *, capacity, workload):
        capacity = cls.round_hours(capacity)
        workload = cls.round_hours(workload)

        return {
            "capacity_hours": capacity,
            "workload_hours": workload,
            "remaining_capacity_hours": cls.round_hours(max(cls.ZERO, capacity - workload)),
            "overload_hours": cls.round_hours(max(cls.ZERO, workload - capacity)),
            "utilization_percentage": cls.get_utilization(capacity=capacity, workload=workload),
            "status": cls.get_status(capacity=capacity, workload=workload),
        }

    @staticmethod
    def get_overlap_hours(start, end, window_start, window_end):
        overlap_start = max(start, window_start)
        overlap_end = min(end, window_end)

        if overlap_start >= overlap_end:
            return Decimal("0")

        return Decimal(str((overlap_end - overlap_start).total_seconds())) / Decimal("3600")

    @classmethod
    def distribute_task_hours(cls, *, task, working_days, hours_per_day, day_start, tz,
                              start_date, end_date):
        if not cls.is_scheduled(task):
            return {}

        remaining_hours = cls.get_remaining_task_hours(task)

        if remaining_hours <= cls.ZERO:
            return {}

        planned_start = task.planned_start.astimezone(tz)
        planned_end = task.planned_end.astimezone(tz)

        weights = {}
        hours_per_day = Decimal(str(hours_per_day))

        for day in cls.get_dates(planned_start.date(), planned_end.date()):
            if day.weekday() not in working_days or hours_per_day <= cls.ZERO:
                continue

            window_start = datetime.combine(day, day_start, tzinfo=tz)
            window_end = window_start + timedelta(seconds=float(hours_per_day * 3600))

            overlap = cls.get_overlap_hours(
                planned_start, planned_end, window_start, window_end,
            )

            if overlap > cls.ZERO:
                weights[day] = overlap

        # Preserve workload for assignments outside normal working hours.
        if not weights:
            for day in cls.get_dates(planned_start.date(), planned_end.date()):
                window_start = datetime.combine(day, time.min, tzinfo=tz)
                window_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)

                overlap = cls.get_overlap_hours(
                    planned_start, planned_end, window_start, window_end,
                )

                if overlap > cls.ZERO:
                    weights[day] = overlap

        total_weight = sum(weights.values(), cls.ZERO)

        if total_weight <= cls.ZERO:
            return {}

        return {
            day: remaining_hours * weight / total_weight
            for day, weight in weights.items()
            if start_date <= day <= end_date
        }

    @classmethod
    def get_conflicts(cls, *, tasks, start_date, end_date, tz):
        period_start = datetime.combine(start_date, time.min, tzinfo=tz)
        period_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)

        scheduled_tasks = [task for task in tasks if cls.is_scheduled(task)]
        conflicts = []

        for first, second in combinations(scheduled_tasks, 2):
            overlap_start = max(first.planned_start, second.planned_start, period_start)
            overlap_end = min(first.planned_end, second.planned_end, period_end)

            if overlap_start >= overlap_end:
                continue

            conflicts.append({
                "task_ids": [first.id, second.id],
                "campaign_ids": sorted({first.campaign_id, second.campaign_id}, key=str),
                "overlap_start": overlap_start,
                "overlap_end": overlap_end,
                "overlap_hours": cls.round_hours(
                    Decimal(str((overlap_end - overlap_start).total_seconds())) / Decimal("3600")
                ),
            })

        return conflicts

    @classmethod
    def build_weekly_breakdown(cls, daily_breakdown):
        weeks = defaultdict(lambda: {"capacity": cls.ZERO, "workload": cls.ZERO})

        for item in daily_breakdown:
            day = item["date"]
            week_start = day - timedelta(days=day.weekday())

            weeks[week_start]["capacity"] += item["capacity_hours"]
            weeks[week_start]["workload"] += item["workload_hours"]

        return [
            {
                "week_start": week_start,
                "week_end": week_start + timedelta(days=6),
                **cls.build_metrics(capacity=values["capacity"], workload=values["workload"]),
            }
            for week_start, values in sorted(weeks.items())
        ]

    @classmethod
    def calculate_member(cls, *, member_id, name, email, skills, tasks, working_days,
                         hours_per_day, absences, start_date, end_date, day_start, tz,
                         capacity_data=None):
        tasks = list(tasks)

        daily_capacity = {}
        daily_workload = defaultdict(lambda: cls.ZERO)
        daily_task_ids = defaultdict(set)
        campaign_workload = defaultdict(lambda: cls.ZERO)

        if capacity_data is not None:
            daily_capacity = {
                item["date"]: Decimal(str(item["available_hours"]))
                for item in capacity_data
            }
        else:
            for day in cls.get_dates(start_date, end_date):
                daily_capacity[day] = cls.get_daily_capacity(
                    day=day, working_days=working_days,
                    hours_per_day=hours_per_day, absences=absences,
                )

        unscheduled_task_ids = []
        scheduled_task_ids = set()

        for task in tasks:
            if not cls.is_scheduled(task):
                unscheduled_task_ids.append(task.id)
                continue

            distribution = cls.distribute_task_hours(
                task=task, working_days=working_days, hours_per_day=hours_per_day,
                day_start=day_start, tz=tz, start_date=start_date, end_date=end_date,
            )

            for day, hours in distribution.items():
                daily_workload[day] += hours
                daily_task_ids[day].add(task.id)
                campaign_workload[task.campaign_id] += hours
                scheduled_task_ids.add(task.id)

        daily_breakdown = [
            {
                "date": day,
                "is_working_day": day.weekday() in working_days,
                "is_absent": cls.is_absent(day, absences),
                "task_ids": sorted(daily_task_ids[day], key=str),
                **cls.build_metrics(capacity=capacity, workload=daily_workload[day]),
            }
            for day, capacity in daily_capacity.items()
        ]

        total_capacity = sum(daily_capacity.values(), cls.ZERO)
        total_workload = sum(daily_workload.values(), cls.ZERO)

        conflicts = cls.get_conflicts(tasks=tasks, start_date=start_date, end_date=end_date, tz=tz)

        return {
            "member_id": member_id,
            "name": name,
            "email": email,
            "skills": skills,
            **cls.build_metrics(capacity=total_capacity, workload=total_workload),
            "scheduled_tasks_count": len(scheduled_task_ids),
            "unscheduled_tasks_count": len(unscheduled_task_ids),
            "unscheduled_task_ids": sorted(unscheduled_task_ids, key=str),
            "overloaded_days_count": sum(day["status"] == WorkloadStatus.OVERLOADED for day in daily_breakdown),
            "conflicts_count": len(conflicts),
            "conflicts": conflicts,
            "daily_breakdown": daily_breakdown,
            "weekly_breakdown": cls.build_weekly_breakdown(daily_breakdown),
            "campaign_breakdown": [
                {
                    "campaign_id": campaign_id,
                    "workload_hours": cls.round_hours(hours),
                }
                for campaign_id, hours in sorted(campaign_workload.items(), key=lambda item: str(item[0]))
            ],
        }