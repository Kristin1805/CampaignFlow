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


class CalendarView(models.TextChoices):
    DAY = "day", "Day"
    WEEK = "week", "Week"
    MONTH = "month", "Month"
    CUSTOM = "custom", "Custom"


class CalendarConflictType(models.TextChoices):
    PLATFORM_OVERLAP = "PLATFORM_OVERLAP", "Platform overlap"
    ASSIGNEE_OVERLAP = "ASSIGNEE_OVERLAP", "Assignee overlap"
    OUTSIDE_CAMPAIGN_PERIOD = "OUTSIDE_CAMPAIGN_PERIOD", "Outside campaign period"

class PostingPlanView(models.TextChoices):
    ALL = "all", "All content"
    WEEK = "week", "Week"
    MONTH = "month", "Month"
    CUSTOM = "custom", "Custom range"
    UNSCHEDULED = "unscheduled", "Unscheduled"


class PostingPlanGrouping(models.TextChoices):
    NONE = "none", "None"
    DATE = "date", "Publication date"
    WEEK = "week", "Week"
    MONTH = "month", "Month"
    CAMPAIGN = "campaign", "Campaign"
    PLATFORM = "platform", "Platform"
    FORMAT = "format", "Content format"
    STATUS = "status", "Status"
    ASSIGNEE = "assignee", "Assignee"