from datetime import timedelta
from zoneinfo import ZoneInfo

from campaignflow.content.constants import (
    POSTING_PLAN_COLUMN_DEFINITIONS,
    POSTING_PLAN_COLUMN_IDS,
    POSTING_PLAN_DEFAULT_VISIBLE_COLUMNS,
)
from campaignflow.content.enums import ContentStatus, PostingPlanGrouping
from campaignflow.content.selectors import ContentPlatformSelector, ContentFormatSelector


class PostingPlanColumns:

    @staticmethod
    def get_columns(*, workspace):
        choices = {
            "status": [
                {"value": value, "label": label}
                for value, label in ContentStatus.choices
            ],
            "platform_id": [
                {"value": str(platform.id), "label": platform.name}
                for platform in ContentPlatformSelector.get_platforms(workspace=workspace)
            ],
            "content_format_id": [
                {"value": str(content_format.id), "label": content_format.name}
                for content_format in ContentFormatSelector.get_formats(workspace=workspace)
            ],
        }

        columns = []

        for definition in POSTING_PLAN_COLUMN_DEFINITIONS:
            field, label, data_type, editable, required, sortable, filterable, visible = definition

            columns.append({
                "field": field,
                "label": label,
                "data_type": data_type,
                "editable": editable,
                "required": required,
                "sortable": sortable,
                "filterable": filterable,
                "default_visible": visible,
                "choices": choices.get(field, []),
            })

        return columns


class PostingPlanPreferences:

    @staticmethod
    def get_defaults():
        return {
            "visible_columns": list(POSTING_PLAN_DEFAULT_VISIBLE_COLUMNS),
            "column_order": list(POSTING_PLAN_COLUMN_IDS),
            "column_widths": {},
            "default_ordering": "publication_at",
            "default_grouping": PostingPlanGrouping.NONE,
            "default_filters": {},
        }

    @classmethod
    def serialize(cls, *, preference):
        if preference is None:
            return {
                **cls.get_defaults(),
                "is_customized": False,
                "updated_at": None,
            }

        return {
            "visible_columns": preference.visible_columns,
            "column_order": preference.column_order,
            "column_widths": preference.column_widths,
            "default_ordering": preference.default_ordering,
            "default_grouping": preference.default_grouping,
            "default_filters": preference.default_filters,
            "is_customized": True,
            "updated_at": preference.updated_at,
        }


class PostingPlanGroupingCalculator:

    @staticmethod
    def get_group(*, content_item, grouping, timezone_name):
        if grouping == PostingPlanGrouping.NONE:
            return None

        if grouping == PostingPlanGrouping.CAMPAIGN:
            return {
                "key": str(content_item.campaign_id),
                "label": content_item.campaign.name,
            }

        if grouping == PostingPlanGrouping.PLATFORM:
            return {
                "key": str(content_item.platform_id),
                "label": content_item.platform.name,
            }

        if grouping == PostingPlanGrouping.FORMAT:
            return {
                "key": str(content_item.content_format_id),
                "label": content_item.content_format.name,
            }

        if grouping == PostingPlanGrouping.STATUS:
            return {
                "key": content_item.status,
                "label": content_item.get_status_display(),
            }

        if grouping == PostingPlanGrouping.ASSIGNEE:
            if content_item.assignee_id is None:
                return {"key": "unassigned", "label": "Unassigned"}

            return {
                "key": str(content_item.assignee_id),
                "label": content_item.assignee.user.email,
            }

        if content_item.publication_at is None:
            return {"key": "unscheduled", "label": "Unscheduled"}

        local_date = content_item.publication_at.astimezone(
            ZoneInfo(timezone_name),
        ).date()

        if grouping == PostingPlanGrouping.DATE:
            return {
                "key": local_date.isoformat(),
                "label": local_date.isoformat(),
            }

        if grouping == PostingPlanGrouping.WEEK:
            week_start = local_date - timedelta(days=local_date.weekday())
            week_end = week_start + timedelta(days=6)

            return {
                "key": week_start.isoformat(),
                "label": f"{week_start.isoformat()} - {week_end.isoformat()}",
            }

        if grouping == PostingPlanGrouping.MONTH:
            return {
                "key": local_date.strftime("%Y-%m"),
                "label": local_date.strftime("%B %Y"),
            }

        return None

    @classmethod
    def group_rows(cls, *, rows):
        groups = {}

        for row in rows:
            group = row.get("group")

            if group is None:
                continue

            key = group["key"]

            if key not in groups:
                groups[key] = {
                    "key": key,
                    "label": group["label"],
                    "total": 0,
                    "content_ids": [],
                }

            groups[key]["total"] += 1
            groups[key]["content_ids"].append(row["id"])

        return list(groups.values())