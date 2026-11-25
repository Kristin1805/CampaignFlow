from django.utils import timezone
from rest_framework import serializers

from campaignflow.content.calendar import CalendarCalculator
from campaignflow.content.constants import MAX_BULK_RESCHEDULE_ITEMS
from campaignflow.content.enums import ContentStatus, CalendarConflictType
from campaignflow.content.models import ContentItem, ContentPlatform, ContentFormat, ContentStatusHistory
from campaignflow.content.permissions import ContentPermission
from campaignflow.content.selectors import ContentSelector


class StrictSerializer(serializers.Serializer):

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected an object.")

        unknown_fields = set(data) - set(self.fields)

        if unknown_fields:
            raise serializers.ValidationError({
                field: "Unknown field." for field in sorted(unknown_fields)
            })

        return super().to_internal_value(data)


class ContentPlatformOutputSerializer(serializers.ModelSerializer):

    class Meta:
        model = ContentPlatform
        fields = ("id", "code", "name", "is_default", "created_at", "updated_at")


class ContentFormatOutputSerializer(serializers.ModelSerializer):

    class Meta:
        model = ContentFormat
        fields = ("id", "code", "name", "is_default", "created_at", "updated_at")


class ContentDefinitionInputSerializer(StrictSerializer):
    code = serializers.SlugField(max_length=100)
    name = serializers.CharField(max_length=150)


class ContentUserSerializer(serializers.Serializer):
    id = serializers.ReadOnlyField()
    email = serializers.EmailField()


class ContentAssigneeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    user = ContentUserSerializer()
    role = serializers.CharField()


class ContentInputSerializer(StrictSerializer):
    title = serializers.CharField(max_length=255)
    topic = serializers.CharField(max_length=255, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=20000)
    copy = serializers.CharField(required=False, allow_blank=True, max_length=50000)
    creative_instructions = serializers.CharField(required=False, allow_blank=True, max_length=20000)
    cta = serializers.CharField(max_length=255, required=False, allow_blank=True)
    destination_url = serializers.URLField(max_length=2048, required=False, allow_blank=True)
    utm_url = serializers.URLField(max_length=2048, required=False, allow_blank=True)
    hashtags = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, max_length=100,
    )
    internal_notes = serializers.CharField(required=False, allow_blank=True, max_length=20000)
    publication_at = serializers.DateTimeField(required=False, allow_null=True)
    platform_id = serializers.UUIDField()
    content_format_id = serializers.UUIDField()
    assignee_id = serializers.UUIDField(required=False, allow_null=True)
    related_task_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_hashtags(self, value):
        hashtags = []

        for tag in value:
            tag = tag.strip().lstrip("#").strip()

            if not tag or any(character.isspace() for character in tag):
                raise serializers.ValidationError("Invalid hashtag.")

            hashtags.append(f"#{tag}")

        return list(dict.fromkeys(hashtags))


class ContentCreateSerializer(ContentInputSerializer):
    status = serializers.ChoiceField(
        choices=[ContentStatus.IDEA, ContentStatus.DRAFT],
        required=False, default=ContentStatus.DRAFT,
    )


class ContentUpdateSerializer(ContentInputSerializer):
    pass


class ContentStatusInputSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=ContentStatus.choices)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=5000)


class ContentDuplicateInputSerializer(StrictSerializer):
    title = serializers.CharField(max_length=255, required=False)


class ContentListFilterSerializer(StrictSerializer):
    campaign_id = serializers.UUIDField(required=False)
    platform_id = serializers.UUIDField(required=False)
    content_format_id = serializers.UUIDField(required=False)
    assignee_id = serializers.UUIDField(required=False)
    created_by = serializers.CharField(required=False, max_length=100)
    status = serializers.ChoiceField(choices=ContentStatus.choices, required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    is_archived = serializers.BooleanField(required=False, default=False)
    search = serializers.CharField(required=False, max_length=255)
    ordering = serializers.ChoiceField(
        choices=sorted(ContentSelector.ORDERING_FIELDS), required=False,
    )
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)

    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")

        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError({
                "date_to": "End date must not precede start date.",
            })

        return attrs

    def validate_created_by(self, value):
        from django.contrib.auth import get_user_model
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            return get_user_model()._meta.pk.to_python(value)
        except (DjangoValidationError, ValueError, TypeError) as exc:
            raise serializers.ValidationError("Invalid user identifier.") from exc


class ContentOutputSerializer(serializers.ModelSerializer):
    campaign_id = serializers.UUIDField()
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)
    workspace_id = serializers.UUIDField(source="campaign.workspace_id", read_only=True)

    platform_id = serializers.UUIDField()
    content_format_id = serializers.UUIDField()
    assignee_id = serializers.UUIDField(allow_null=True)
    related_task_id = serializers.UUIDField(allow_null=True)

    platform = ContentPlatformOutputSerializer(read_only=True)
    content_format = ContentFormatOutputSerializer(read_only=True)
    assignee = ContentAssigneeSerializer(read_only=True, allow_null=True)
    created_by = ContentUserSerializer(read_only=True)
    updated_by = ContentUserSerializer(read_only=True)

    class Meta:
        model = ContentItem
        fields = (
            "id", "workspace_id", "campaign_id", "campaign_name",
            "title", "topic", "description", "copy", "creative_instructions",
            "cta", "destination_url", "utm_url", "hashtags", "internal_notes",
            "platform_id", "platform", "content_format_id", "content_format",
            "assignee_id", "assignee", "related_task_id", "status",
            "publication_at", "published_at", "created_by", "updated_by",
            "is_archived", "archived_at", "created_at", "updated_at",
        )


class ContentStatusHistoryOutputSerializer(serializers.ModelSerializer):
    content_item_id = serializers.UUIDField()
    changed_by = ContentUserSerializer(read_only=True)

    class Meta:
        model = ContentStatusHistory
        fields = (
            "id", "content_item_id", "previous_status", "new_status",
            "changed_by", "comment", "created_at",
        )

class CalendarUUIDListField(serializers.ListField):
    child = serializers.UUIDField()

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", MAX_CALENDAR_FILTER_ITEMS)
        kwargs.setdefault("allow_empty", False)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = [value.strip() for value in data.split(",")]

        values = super().to_internal_value(data)

        return list(dict.fromkeys(values))


class CalendarStatusListField(serializers.ListField):
    child = serializers.ChoiceField(choices=ContentStatus.choices)

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", len(ContentStatus.choices))
        kwargs.setdefault("allow_empty", False)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = [value.strip() for value in data.split(",")]

        values = super().to_internal_value(data)

        return list(dict.fromkeys(values))


class CalendarAwareDateTimeField(serializers.DateTimeField):

    def to_internal_value(self, value):
        if isinstance(value, str):
            try:
                parsed = parse_datetime(value)
            except ValueError:
                parsed = None

            if parsed is None or timezone.is_naive(parsed):
                raise serializers.ValidationError(
                    "Provide an ISO 8601 datetime with a timezone offset."
                )

        elif hasattr(value, "tzinfo") and timezone.is_naive(value):
            raise serializers.ValidationError("Timezone information is required.")

        return super().to_internal_value(value)


class CalendarBaseFilterSerializer(StrictSerializer):
    campaign_ids = CalendarUUIDListField(required=False)
    platform_ids = CalendarUUIDListField(required=False)
    format_ids = CalendarUUIDListField(required=False)
    assignee_ids = CalendarUUIDListField(required=False)
    statuses = CalendarStatusListField(required=False)
    search = serializers.CharField(required=False, max_length=255)
    unassigned_only = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if attrs.get("unassigned_only") and attrs.get("assignee_ids"):
            raise serializers.ValidationError({
                "assignee_ids": "Cannot combine assignee filters with unassigned_only.",
            })

        return attrs


class CalendarFilterSerializer(CalendarBaseFilterSerializer):
    view = serializers.ChoiceField(
        choices=CalendarView.choices, required=False, default=CalendarView.MONTH,
    )
    reference_date = serializers.DateField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)

        view = attrs.get("view", CalendarView.MONTH)
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")

        if view == CalendarView.CUSTOM:
            if date_from is None or date_to is None:
                raise serializers.ValidationError({
                    "date_range": "Custom view requires date_from and date_to.",
                })

            if date_from > date_to:
                raise serializers.ValidationError({
                    "date_to": "End date must not precede start date.",
                })

            if attrs.get("reference_date") is not None:
                raise serializers.ValidationError({
                    "reference_date": "Reference date is not used in custom view.",
                })

        elif date_from is not None or date_to is not None:
            raise serializers.ValidationError({
                "date_range": "Explicit date ranges require custom view.",
            })

        return attrs


class CalendarUnscheduledFilterSerializer(CalendarBaseFilterSerializer):
    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100)


class ContentRescheduleInputSerializer(StrictSerializer):
    publication_at = CalendarAwareDateTimeField(allow_null=True)


class BulkRescheduleItemSerializer(ContentRescheduleInputSerializer):
    content_id = serializers.UUIDField()


class BulkRescheduleInputSerializer(StrictSerializer):
    items = BulkRescheduleItemSerializer(many=True, allow_empty=False, max_length=MAX_BULK_RESCHEDULE_ITEMS,)

    def validate_items(self, items):
        content_ids = [item["content_id"] for item in items]

        if len(content_ids) != len(set(content_ids)):
            raise serializers.ValidationError("Duplicate content IDs are not allowed.")

        return items

class CalendarPeriodOutputSerializer(serializers.Serializer):
    view = serializers.ChoiceField(choices=CalendarView.choices)
    timezone = serializers.CharField()
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    start_at = serializers.DateTimeField()
    end_at = serializers.DateTimeField()
    total_days = serializers.IntegerField()


class CalendarNavigationSerializer(serializers.Serializer):
    previous_date = serializers.DateField()
    next_date = serializers.DateField()


class CalendarActionsSerializer(serializers.Serializer):
    can_view = serializers.BooleanField()
    can_edit = serializers.BooleanField()
    can_reschedule = serializers.BooleanField()
    can_unschedule = serializers.BooleanField()
    can_archive = serializers.BooleanField()


class CalendarEventSerializer(serializers.ModelSerializer):
    campaign_id = serializers.UUIDField()
    campaign_name = serializers.CharField(source="campaign.name")
    platform = ContentPlatformOutputSerializer(read_only=True)
    content_format = ContentFormatOutputSerializer(read_only=True)
    assignee = ContentAssigneeSerializer(read_only=True, allow_null=True)
    related_task_id = serializers.UUIDField(allow_null=True)

    local_date = serializers.SerializerMethodField()
    copy_preview = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()

    class Meta:
        model = ContentItem
        fields = (
            "id", "campaign_id", "campaign_name", "title", "topic",
            "platform", "content_format", "assignee", "related_task_id",
            "status", "publication_at", "published_at", "local_date",
            "copy_preview", "is_overdue", "updated_at", "actions",
        )

    def get_local_date(self, obj):
        if obj.publication_at is None:
            return None

        return CalendarCalculator.get_local_date(
            publication_at=obj.publication_at,
            timezone_name=obj.campaign.workspace.timezone,
        ).isoformat()

    def get_copy_preview(self, obj):
        return obj.copy[:200]

    def get_is_overdue(self, obj):
        now = self.context.get("now") or timezone.now()

        return CalendarCalculator.is_overdue(content_item=obj, now=now)

    def get_actions(self, obj):
        membership = self.context["membership"]

        return ContentPermission.get_calendar_actions(
            membership=membership, content_item=obj,
        )


class CalendarDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    total = serializers.IntegerField()
    events = CalendarEventSerializer(many=True)


class CalendarCountSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    total = serializers.IntegerField()


class CalendarDailyCountSerializer(serializers.Serializer):
    date = serializers.DateField()
    total = serializers.IntegerField()


class CalendarSummarySerializer(serializers.Serializer):
    total_publications = serializers.IntegerField()
    ideas = serializers.IntegerField()
    draft = serializers.IntegerField()
    in_progress = serializers.IntegerField()
    in_review = serializers.IntegerField()
    changes_requested = serializers.IntegerField()
    approved = serializers.IntegerField()
    scheduled = serializers.IntegerField()
    published = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    overdue = serializers.IntegerField()
    unscheduled = serializers.IntegerField()
    unassigned = serializers.IntegerField()

    by_platform = CalendarCountSerializer(many=True)
    by_campaign = CalendarCountSerializer(many=True)
    by_assignee = CalendarCountSerializer(many=True)
    by_date = CalendarDailyCountSerializer(many=True)


class CalendarConflictSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=CalendarConflictType.choices)
    message = serializers.CharField()
    publication_at = serializers.DateTimeField(allow_null=True)
    reference_id = serializers.UUIDField(allow_null=True)
    content_ids = serializers.ListField(child=serializers.UUIDField())
    affected_content_count = serializers.IntegerField()


class ContentCalendarOutputSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField()
    campaign_id = serializers.UUIDField(allow_null=True)
    period = CalendarPeriodOutputSerializer()
    navigation = CalendarNavigationSerializer()
    summary = CalendarSummarySerializer()
    days = CalendarDaySerializer(many=True)
    conflicts = CalendarConflictSerializer(many=True)


class CalendarSummaryOutputSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField()
    period = CalendarPeriodOutputSerializer()
    summary = CalendarSummarySerializer()


class CalendarConflictsOutputSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField()
    period = CalendarPeriodOutputSerializer()
    total_conflicts = serializers.IntegerField()
    conflicts = CalendarConflictSerializer(many=True)


class BulkRescheduleOutputSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField()
    requested_count = serializers.IntegerField()
    updated_count = serializers.IntegerField()
    items = CalendarEventSerializer(many=True)