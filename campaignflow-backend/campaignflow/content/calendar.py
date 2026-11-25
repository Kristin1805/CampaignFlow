from calendar import monthrange
from collections import defaultdict, Counter
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from campaignflow.content.constants import (
    MAX_CALENDAR_RANGE_DAYS,
    CALENDAR_TERMINAL_STATUSES,
)
from campaignflow.content.enums import (
    CalendarView, ContentStatus, CalendarConflictType,
)


class CalendarPeriod:

    @staticmethod
    def resolve(*, workspace, view=CalendarView.MONTH, reference_date=None,
                date_from=None, date_to=None):

        tz = ZoneInfo(workspace.timezone)
        reference_date = reference_date or timezone.localdate(timezone=tz)

        if view == CalendarView.DAY:
            start_date = reference_date
            end_date = reference_date

        elif view == CalendarView.WEEK:
            start_date = reference_date - timedelta(days=reference_date.weekday())
            end_date = start_date + timedelta(days=6)

        elif view == CalendarView.MONTH:
            start_date = reference_date.replace(day=1)
            last_day = monthrange(reference_date.year, reference_date.month)[1]
            end_date = reference_date.replace(day=last_day)

        elif view == CalendarView.CUSTOM:
            if date_from is None or date_to is None:
                raise ValidationError({
                    "date_range": "Custom view requires date_from and date_to.",
                })

            start_date = date_from
            end_date = date_to

        else:
            raise ValidationError({"view": "Invalid calendar view."})

        if start_date > end_date:
            raise ValidationError({"date_to": "End date must not precede start date."})

        total_days = (end_date - start_date).days + 1

        if total_days > MAX_CALENDAR_RANGE_DAYS:
            raise ValidationError({
                "date_range": f"Calendar range cannot exceed {MAX_CALENDAR_RANGE_DAYS} days.",
            })

        if end_date == date.max:
            raise ValidationError({"date_to": "End date is outside the supported range."})

        start_at = datetime.combine(start_date, time.min, tzinfo=tz)
        end_at = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)

        return {
            "view": view,
            "timezone": workspace.timezone,
            "date_from": start_date,
            "date_to": end_date,
            "start_at": start_at,
            "end_at": end_at,
            "total_days": total_days,
        }

    @staticmethod
    def get_dates(*, period):
        return [
            period["date_from"] + timedelta(days=offset)
            for offset in range(period["total_days"])
        ]

    @staticmethod
    def get_navigation(*, period):
        start_date = period["date_from"]
        end_date = period["date_to"]
        view = period["view"]

        if view == CalendarView.MONTH:
            previous_date = (start_date - timedelta(days=1)).replace(day=1)
            next_date = end_date + timedelta(days=1)

        else:
            previous_date = start_date - timedelta(days=period["total_days"])
            next_date = end_date + timedelta(days=1)

        return {
            "previous_date": previous_date,
            "next_date": next_date,
        }


class CalendarCalculator:

    @staticmethod
    def get_local_date(*, publication_at, timezone_name):
        return publication_at.astimezone(ZoneInfo(timezone_name)).date()

    @staticmethod
    def is_overdue(*, content_item, now):
        return (
            content_item.publication_at is not None
            and content_item.publication_at < now
            and content_item.status not in CALENDAR_TERMINAL_STATUSES
        )

    @classmethod
    def group_by_date(cls, *, content_items, period):
        grouped = defaultdict(list)

        for item in content_items:
            if item.publication_at is None:
                continue

            local_date = cls.get_local_date(
                publication_at=item.publication_at,
                timezone_name=period["timezone"],
            )

            grouped[local_date].append(item)

        return [
            {
                "date": current_date,
                "total": len(grouped[current_date]),
                "events": grouped[current_date],
            }
            for current_date in CalendarPeriod.get_dates(period=period)
        ]

    @classmethod
    def get_summary(cls, *, content_items, period, unscheduled_count, now):
        status_counts = Counter()
        platform_counts = Counter()
        campaign_counts = Counter()
        assignee_counts = Counter()
        daily_counts = Counter()

        platform_names = {}
        campaign_names = {}
        assignee_names = {}

        overdue_count = 0
        unassigned_count = 0

        for item in content_items:
            status_counts[item.status] += 1

            platform_counts[item.platform_id] += 1
            platform_names[item.platform_id] = item.platform.name

            campaign_counts[item.campaign_id] += 1
            campaign_names[item.campaign_id] = item.campaign.name

            if item.assignee_id is not None:
                assignee_counts[item.assignee_id] += 1
                assignee_names[item.assignee_id] = item.assignee.user.email
            else:
                unassigned_count += 1

            if item.publication_at is not None:
                local_date = cls.get_local_date(
                    publication_at=item.publication_at,
                    timezone_name=period["timezone"],
                )
                daily_counts[local_date] += 1

            if cls.is_overdue(content_item=item, now=now):
                overdue_count += 1

        return {
            "total_publications": len(content_items),
            "ideas": status_counts[ContentStatus.IDEA],
            "draft": status_counts[ContentStatus.DRAFT],
            "in_progress": status_counts[ContentStatus.IN_PROGRESS],
            "in_review": status_counts[ContentStatus.IN_REVIEW],
            "changes_requested": status_counts[ContentStatus.CHANGES_REQUESTED],
            "approved": status_counts[ContentStatus.APPROVED],
            "scheduled": status_counts[ContentStatus.SCHEDULED],
            "published": status_counts[ContentStatus.PUBLISHED],
            "cancelled": status_counts[ContentStatus.CANCELLED],
            "overdue": overdue_count,
            "unscheduled": unscheduled_count,
            "unassigned": unassigned_count,

            "by_platform": [
                {"id": key, "name": platform_names[key], "total": count}
                for key, count in platform_counts.most_common()
            ],

            "by_campaign": [
                {"id": key, "name": campaign_names[key], "total": count}
                for key, count in campaign_counts.most_common()
            ],

            "by_assignee": [
                {"id": key, "name": assignee_names[key], "total": count}
                for key, count in assignee_counts.most_common()
            ],

            "by_date": [
                {"date": current_date, "total": daily_counts[current_date]}
                for current_date in CalendarPeriod.get_dates(period=period)
            ],
        }


class CalendarConflictDetector:

    @staticmethod
    def create_conflict(*, conflict_type, message, content_items,
                        publication_at=None, reference_id=None):

        content_ids = sorted({item.id for item in content_items}, key=str)

        return {
            "type": conflict_type,
            "message": message,
            "publication_at": publication_at,
            "reference_id": reference_id,
            "content_ids": content_ids,
            "affected_content_count": len(content_ids),
        }

    @staticmethod
    def normalize_boundary(*, value, tz):
        if value is None:
            return None

        if isinstance(value, datetime):
            if timezone.is_naive(value):
                return timezone.make_aware(value, timezone=tz)

            return value

        if isinstance(value, date):
            return datetime.combine(value, time.min, tzinfo=tz)

        return None

    @classmethod
    def is_outside_campaign_period(cls, *, content_item, timezone_name):
        campaign = content_item.campaign
        publication_at = content_item.publication_at
        tz = ZoneInfo(timezone_name)

        start_value = getattr(campaign, "start_at", None)
        end_value = getattr(campaign, "launch_at", None)

        start_at = cls.normalize_boundary(value=start_value, tz=tz)
        end_at = cls.normalize_boundary(value=end_value, tz=tz)

        if start_at is not None and publication_at < start_at:
            return True

        if end_at is not None:
            if isinstance(end_value, date) and not isinstance(end_value, datetime):
                return publication_at >= end_at + timedelta(days=1)

            if publication_at > end_at:
                return True

        return False

    @classmethod
    def detect(cls, *, content_items, timezone_name):
        platform_groups = defaultdict(list)
        assignee_groups = defaultdict(list)
        conflicts = []

        for item in content_items:
            if item.publication_at is None or item.status in CALENDAR_TERMINAL_STATUSES:
                continue

            platform_groups[(item.platform_id, item.publication_at)].append(item)

            if item.assignee_id is not None:
                assignee_groups[(item.assignee_id, item.publication_at)].append(item)

            if cls.is_outside_campaign_period(
                content_item=item, timezone_name=timezone_name,
            ):
                conflicts.append(cls.create_conflict(
                    conflict_type=CalendarConflictType.OUTSIDE_CAMPAIGN_PERIOD,
                    message="Publication is scheduled outside the campaign period.",
                    content_items=[item],
                    publication_at=item.publication_at,
                    reference_id=item.campaign_id,
                ))

        for (platform_id, publication_at), items in platform_groups.items():
            if len(items) < 2:
                continue

            conflicts.append(cls.create_conflict(
                conflict_type=CalendarConflictType.PLATFORM_OVERLAP,
                message="Multiple publications are scheduled on the same platform at the same time.",
                content_items=items,
                publication_at=publication_at,
                reference_id=platform_id,
            ))

        for (assignee_id, publication_at), items in assignee_groups.items():
            if len(items) < 2:
                continue

            conflicts.append(cls.create_conflict(
                conflict_type=CalendarConflictType.ASSIGNEE_OVERLAP,
                message="Multiple publications are assigned to the same member at the same time.",
                content_items=items,
                publication_at=publication_at,
                reference_id=assignee_id,
            ))

        return sorted(
            conflicts,
            key=lambda conflict: (
                conflict["publication_at"],
                conflict["type"],
                str(conflict["reference_id"]),
            ),
        )