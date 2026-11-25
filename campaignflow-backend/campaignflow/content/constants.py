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