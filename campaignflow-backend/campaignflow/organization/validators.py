from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError


def validate_timezone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValidationError("Invalid timezone.")


def validate_working_days(value):
    if (
        not isinstance(value, list)
        or not value
        or any(type(day) is not int or day not in range(7) for day in value)
        or len(value) != len(set(value))
    ):
        raise ValidationError(
            "Working days must be unique integers between 0 and 6."
        )