import uuid

from django.conf import settings
from django.db import models

class Risk(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"
    CRITICAL = "CRITICAL", "Critical"


class OptimizationRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.CASCADE,
        related_name="optimization_runs",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_optimization_runs",
    )
    input_json = models.JSONField(default=dict)
    output_json = models.JSONField(default=dict)
    feasible = models.BooleanField(default=False)
    makespan_hours = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    risk = models.CharField(max_length=10, choices=Risk.choices, blank=True)
    engine_version = models.CharField(max_length=100, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    campaign_revision = models.PositiveIntegerField()
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["campaign", "-created_at"]),
            models.Index(fields=["campaign", "applied_at"]),
        ]

    def __str__(self):
        return f"Optimization run {self.id} for campaign {self.campaign_id}"