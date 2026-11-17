from django.db import models


class WorkloadStatus(models.TextChoices):
    AVAILABLE = "AVAILABLE", "Available"
    BALANCED = "BALANCED", "Balanced"
    FULLY_BOOKED = "FULLY_BOOKED", "Fully booked"
    OVERLOADED = "OVERLOADED", "Overloaded"
    UNAVAILABLE = "UNAVAILABLE", "Unavailable"