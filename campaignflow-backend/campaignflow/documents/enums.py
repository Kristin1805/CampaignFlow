from django.db import models


class DocumentTemplateCategory(models.TextChoices):
    STRATEGY = "strategy", "Strategy"
    BRIEF = "brief", "Brief"
    CONTENT = "content", "Content"
    SOCIAL_MEDIA = "social_media", "Social media"
    INFLUENCER = "influencer", "Influencer marketing"
    ADVERTISING = "advertising", "Advertising"
    FINANCE = "finance", "Finance"
    ANALYTICS = "analytics", "Analytics"
    FEEDBACK = "feedback", "Feedback"
    PR = "pr", "Public relations"
    EVENTS = "events", "Events"
    OPERATIONS = "operations", "Operations"
    CUSTOM = "custom", "Custom"


class DocumentSectionType(models.TextChoices):
    RICH_TEXT = "rich_text", "Rich text"
    PLAIN_TEXT = "plain_text", "Plain text"
    HEADING = "heading", "Heading"
    TABLE = "table", "Dynamic table"
    CHECKLIST = "checklist", "Checklist"
    KEY_VALUE = "key_value", "Key-value fields"
    NUMBER = "number", "Number"
    DATE = "date", "Date"
    SELECT = "select", "Single selection"
    MULTI_SELECT = "multi_select", "Multiple selection"
    REFERENCE = "reference", "Reference"


class DocumentFieldType(models.TextChoices):
    TEXT = "text", "Text"
    LONG_TEXT = "long_text", "Long text"
    NUMBER = "number", "Number"
    DECIMAL = "decimal", "Decimal"
    CURRENCY = "currency", "Currency"
    PERCENTAGE = "percentage", "Percentage"
    DATE = "date", "Date"
    DATETIME = "datetime", "Date and time"
    URL = "url", "URL"
    BOOLEAN = "boolean", "Boolean"
    CHOICE = "choice", "Choice"
    REFERENCE = "reference", "Reference"


class DocumentTemplateStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"