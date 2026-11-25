from rest_framework import serializers

from campaignflow.content.enums import ContentStatus
from campaignflow.content.models import ContentItem, ContentPlatform, ContentFormat, ContentStatusHistory
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