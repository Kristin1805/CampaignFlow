from campaignflow.content.enums import ContentStatus


DEFAULT_CONTENT_PLATFORMS = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "linkedin": "LinkedIn",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "threads": "Threads",
    "pinterest": "Pinterest",
    "website": "Website",
    "blog": "Blog",
    "newsletter": "Newsletter",
    "other": "Other",
}

DEFAULT_CONTENT_FORMATS = {
    "post": "Post",
    "reel": "Reel",
    "story": "Story",
    "carousel": "Carousel",
    "video": "Video",
    "article": "Article",
    "blog-post": "Blog post",
    "newsletter": "Newsletter",
    "banner": "Banner",
    "advertisement": "Advertisement",
    "other": "Other",
}

CONTENT_STATUS_TRANSITIONS = {
    ContentStatus.IDEA: {
        ContentStatus.DRAFT, ContentStatus.CANCELLED,
    },
    ContentStatus.DRAFT: {
        ContentStatus.IDEA, ContentStatus.IN_PROGRESS,
        ContentStatus.IN_REVIEW, ContentStatus.CANCELLED,
    },
    ContentStatus.IN_PROGRESS: {
        ContentStatus.DRAFT, ContentStatus.IN_REVIEW,
        ContentStatus.CANCELLED,
    },
    ContentStatus.IN_REVIEW: {
        ContentStatus.CHANGES_REQUESTED, ContentStatus.APPROVED,
        ContentStatus.CANCELLED,
    },
    ContentStatus.CHANGES_REQUESTED: {
        ContentStatus.DRAFT, ContentStatus.IN_PROGRESS,
        ContentStatus.IN_REVIEW, ContentStatus.CANCELLED,
    },
    ContentStatus.APPROVED: {
        ContentStatus.SCHEDULED, ContentStatus.DRAFT,
        ContentStatus.CANCELLED,
    },
    ContentStatus.SCHEDULED: {
        ContentStatus.PUBLISHED, ContentStatus.APPROVED,
        ContentStatus.DRAFT, ContentStatus.CANCELLED,
    },
    ContentStatus.PUBLISHED: set(),
    ContentStatus.CANCELLED: {
        ContentStatus.DRAFT,
    },
}

EDITABLE_CONTENT_STATUSES = {
    ContentStatus.IDEA,
    ContentStatus.DRAFT,
    ContentStatus.IN_PROGRESS,
    ContentStatus.CHANGES_REQUESTED,
}

MEMBER_CONTENT_TRANSITIONS = {
    ContentStatus.IDEA,
    ContentStatus.DRAFT,
    ContentStatus.IN_PROGRESS,
    ContentStatus.IN_REVIEW,
}

PUBLICATION_DATE_REQUIRED_STATUSES = {
    ContentStatus.SCHEDULED,
    ContentStatus.PUBLISHED,
}

MAX_CALENDAR_RANGE_DAYS = 93
MAX_BULK_RESCHEDULE_ITEMS = 100
MAX_CALENDAR_FILTER_ITEMS = 100

CALENDAR_TERMINAL_STATUSES = {
    ContentStatus.PUBLISHED,
    ContentStatus.CANCELLED,
}

CALENDAR_RESCHEDULABLE_STATUSES = EDITABLE_CONTENT_STATUSES.copy()

MAX_POSTING_PLAN_BULK_ITEMS = 100
POSTING_PLAN_PAGE_SIZE = 50
POSTING_PLAN_MAX_PAGE_SIZE = 200

POSTING_PLAN_ORDERING_FIELDS = {
    "publication_at": "publication_at",
    "created_at": "created_at",
    "updated_at": "updated_at",
    "campaign": "campaign__name",
    "platform": "platform__name",
    "content_format": "content_format__name",
    "title": "title",
    "status": "status",
    "assignee": "assignee__user__email",
}

POSTING_PLAN_ORDERING_CHOICES = tuple(
    value
    for field in POSTING_PLAN_ORDERING_FIELDS
    for value in (field, f"-{field}")
)

POSTING_PLAN_COLUMN_DEFINITIONS = (
    ("publication_at", "Publication date", "datetime", True, False, True, True, True),
    ("campaign_id", "Campaign", "reference", False, True, True, True, True),
    ("platform_id", "Platform", "reference", True, True, True, True, True),
    ("content_format_id", "Format", "reference", True, True, True, True, True),
    ("title", "Title", "text", True, True, True, True, True),
    ("topic", "Topic", "text", True, False, False, True, True),
    ("description", "Description", "long_text", True, False, False, True, False),
    ("copy", "Caption", "long_text", True, False, False, True, True),
    ("creative_instructions", "Visual concept", "long_text", True, False, False, False, True),
    ("cta", "Call to action", "text", True, False, False, False, True),
    ("destination_url", "Destination URL", "url", True, False, False, False, False),
    ("utm_url", "UTM URL", "url", True, False, False, False, False),
    ("hashtags", "Hashtags", "list", True, False, False, False, False),
    ("internal_notes", "Internal notes", "long_text", True, False, False, False, False),
    ("assignee_id", "Assignee", "reference", True, False, True, True, True),
    ("related_task_id", "Related task", "reference", True, False, False, False, False),
    ("status", "Status", "choice", True, True, True, True, True),
    ("published_at", "Published at", "datetime", False, False, False, False, False),
    ("created_by", "Created by", "reference", False, False, False, False, False),
    ("updated_by", "Updated by", "reference", False, False, False, False, False),
    ("created_at", "Created at", "datetime", False, False, True, False, False),
    ("updated_at", "Updated at", "datetime", False, False, True, False, False),
)

POSTING_PLAN_COLUMN_IDS = tuple(
    column[0] for column in POSTING_PLAN_COLUMN_DEFINITIONS
)

POSTING_PLAN_DEFAULT_VISIBLE_COLUMNS = tuple(
    column[0] for column in POSTING_PLAN_COLUMN_DEFINITIONS if column[7]
)