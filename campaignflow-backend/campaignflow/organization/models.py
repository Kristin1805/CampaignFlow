
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def default_working_days():
    return [0, 1, 2, 3, 4]


def validate_working_days(value):
    if (
        not isinstance(value, list)
        or not value
        or any(type(day) is not int or day not in range(7) for day in value)
        or len(value) != len(set(value))
    ):
        raise ValidationError( "Working days must be unique integers between 0 and 6.")


def validate_timezone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValidationError("Invalid timezone.")


class Workspace(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(max_length=150,)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_workspaces",
    )

    timezone = models.CharField(
        max_length=64,
        default="Europe/Sofia",
        validators=[validate_timezone],
    )

    working_days = models.JSONField(
        default=default_working_days,
        validators=[validate_working_days],
    )

    working_hours_per_day = models.PositiveSmallIntegerField(
        default=8,
        validators=[
            MinValueValidator(1),
            MaxValueValidator(24),
        ],
    )

    created_at = models.DateTimeField(auto_now_add=True,)

    updated_at = models.DateTimeField(auto_now=True, )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
