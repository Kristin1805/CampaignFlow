from django.db import models


class ContentStatus(models.TextChoices):
    IDEA = "IDEA", "Idea"
    DRAFT = "DRAFT", "Draft"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    IN_REVIEW = "IN_REVIEW", "In review"
    CHANGES_REQUESTED = "CHANGES_REQUESTED", "Changes requested"
    APPROVED = "APPROVED", "Approved"
    SCHEDULED = "SCHEDULED", "Scheduled"
    PUBLISHED = "PUBLISHED", "Published"
    CANCELLED = "CANCELLED", "Cancelled"