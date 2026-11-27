from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.dateparse import parse_datetime

from rest_framework import serializers

from campaignflow.documents.constants import (
    TEMPLATE_ORDERING_FIELDS,
    DOCUMENT_TEMPLATE_MAX_PAGE_SIZE,
)
from campaignflow.documents.enums import (
    DocumentTemplateCategory,
    DocumentTemplateStatus,
)
from campaignflow.documents.models import DocumentTemplate, DocumentTemplateVersion
from campaignflow.documents.permissions import DocumentTemplatePermission
from campaignflow.documents.selectors import DocumentTemplateSelector
from campaignflow.documents.validators import DocumentTemplateValidator


class StrictSerializer(serializers.Serializer):

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown_fields = set(data) - set(self.fields)

            if unknown_fields:
                raise serializers.ValidationError({
                    field: "Unknown field." for field in sorted(unknown_fields)
                })

        return super().to_internal_value(data)


class AwareDateTimeField(serializers.DateTimeField):

    def to_internal_value(self, value):
        if isinstance(value, str):
            try:
                parsed = parse_datetime(value)
            except ValueError:
                parsed = None

            if parsed is None or parsed.utcoffset() is None:
                raise serializers.ValidationError(
                    "A timezone-aware ISO datetime is required.",
                )

        elif not hasattr(value, "utcoffset") or value.utcoffset() is None:
            raise serializers.ValidationError("Timezone information is required.")

        return super().to_internal_value(value)


class TemplateStructureField(serializers.JSONField):

    def to_internal_value(self, data):
        value = super().to_internal_value(data)

        try:
            DocumentTemplateValidator.validate(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)

        return value


class DocumentTemplateCreateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=255)
    code = serializers.SlugField(max_length=100)
    description = serializers.CharField(max_length=10000, required=False, allow_blank=True)
    category = serializers.ChoiceField(
        choices=DocumentTemplateCategory.choices,
        required=False,
        default=DocumentTemplateCategory.CUSTOM,
    )
    draft_structure = TemplateStructureField(required=False)

    def validate_code(self, value):
        return value.lower()


class DocumentTemplateUpdateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=255, required=False)
    code = serializers.SlugField(max_length=100, required=False)
    description = serializers.CharField(max_length=10000, required=False, allow_blank=True)
    category = serializers.ChoiceField(choices=DocumentTemplateCategory.choices, required=False)

    def validate_code(self, value):
        return value.lower()

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("At least one field is required.")

        return attrs


class DocumentTemplateDraftSerializer(StrictSerializer):
    structure = TemplateStructureField()
    expected_updated_at = AwareDateTimeField()


class DocumentTemplatePublishSerializer(StrictSerializer):
    expected_updated_at = AwareDateTimeField()
    change_summary = serializers.CharField(
        max_length=5000, allow_blank=True, required=False, default="",
    )


class DocumentTemplateVersionRestoreSerializer(StrictSerializer):
    expected_updated_at = AwareDateTimeField()


class DocumentTemplateDuplicateSerializer(StrictSerializer):
    name = serializers.CharField(max_length=255, required=False)
    code = serializers.SlugField(max_length=100)
    version_id = serializers.UUIDField(required=False)

    def validate_code(self, value):
        return value.lower()


class DocumentTemplateFilterSerializer(StrictSerializer):
    category = serializers.ChoiceField(
        choices=DocumentTemplateCategory.choices, required=False,
    )

    status = serializers.ChoiceField(
        choices=DocumentTemplateStatus.choices, required=False,
    )

    is_system = serializers.BooleanField(required=False)
    is_archived = serializers.BooleanField(required=False)

    search = serializers.CharField(max_length=255, required=False)
    ordering = serializers.ChoiceField(
        choices=TEMPLATE_ORDERING_FIELDS, required=False, default="name",
    )

    page = serializers.IntegerField(required=False, min_value=1)
    page_size = serializers.IntegerField(
        required=False, min_value=1, max_value=DOCUMENT_TEMPLATE_MAX_PAGE_SIZE,
    )

    def validate(self, attrs):
        status = attrs.get("status")
        is_archived = attrs.get("is_archived")

        if status == DocumentTemplateStatus.ARCHIVED:
            if is_archived is False:
                raise serializers.ValidationError({
                    "status": "Conflicting archive filters.",
                })

            attrs["is_archived"] = True

        elif status in {
            DocumentTemplateStatus.DRAFT,
            DocumentTemplateStatus.PUBLISHED,
        } and is_archived is True:
            raise serializers.ValidationError({
                "status": "Conflicting archive filters.",
            })

        return attrs


class DocumentTemplateListSerializer(serializers.ModelSerializer):
    workspace_id = serializers.ReadOnlyField()
    status = serializers.CharField(read_only=True)
    created_by_id = serializers.ReadOnlyField()
    updated_by_id = serializers.ReadOnlyField()
    actions = serializers.SerializerMethodField()

    class Meta:
        model = DocumentTemplate
        fields = (
            "id", "workspace_id", "name", "code", "description",
            "category", "status", "is_system", "is_archived",
            "latest_version", "created_by_id", "updated_by_id",
            "archived_at", "created_at", "updated_at", "actions",
        )

    def get_actions(self, obj):
        return DocumentTemplatePermission.get_actions(
            membership=self.context["membership"],
            template=obj,
        )


class DocumentTemplateVersionListSerializer(serializers.ModelSerializer):
    template_id = serializers.ReadOnlyField()
    published_by_id = serializers.ReadOnlyField()
    published_by_email = serializers.EmailField(
        source="published_by.email", read_only=True,
    )

    class Meta:
        model = DocumentTemplateVersion
        fields = (
            "id", "template_id", "version", "name", "description",
            "category", "change_summary", "published_by_id",
            "published_by_email", "published_at",
        )


class DocumentTemplateVersionSerializer(DocumentTemplateVersionListSerializer):

    class Meta(DocumentTemplateVersionListSerializer.Meta):
        fields = DocumentTemplateVersionListSerializer.Meta.fields + ("structure",)


class DocumentTemplateDetailsSerializer(DocumentTemplateListSerializer):
    draft_structure = serializers.SerializerMethodField()
    published_version = serializers.SerializerMethodField()
    has_unpublished_changes = serializers.SerializerMethodField()

    class Meta(DocumentTemplateListSerializer.Meta):
        fields = DocumentTemplateListSerializer.Meta.fields + (
            "draft_structure",
            "published_version",
            "has_unpublished_changes",
        )

    def get_latest_version(self, obj):
        if not hasattr(self, "_latest_versions"):
            self._latest_versions = {}

        if obj.id not in self._latest_versions:
            self._latest_versions[obj.id] = DocumentTemplateSelector.get_latest_version(
                template=obj,
            )

        return self._latest_versions[obj.id]

    def get_draft_structure(self, obj):
        membership = self.context["membership"]

        if not DocumentTemplatePermission.is_management(membership=membership):
            return None

        return obj.draft_structure

    def get_published_version(self, obj):
        version = self.get_latest_version(obj)

        if version is None:
            return None

        return DocumentTemplateVersionSerializer(version).data

    def get_has_unpublished_changes(self, obj):
        if not DocumentTemplatePermission.is_management(
            membership=self.context["membership"],
        ):
            return None

        version = self.get_latest_version(obj)

        if version is None:
            return True

        return any([
            version.structure != obj.draft_structure,
            version.name != obj.name,
            version.description != obj.description,
            version.category != obj.category,
        ])

from rest_framework import serializers

from campaignflow.documents.enums import DocumentStatus, DocumentTemplateCategory
from campaignflow.documents.models import Document
from campaignflow.documents.permissions import DocumentPermission
from campaignflow.documents.selectors import DocumentSelector


class DocumentStrictSerializer(serializers.Serializer):

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected an object.")

        unknown_fields = set(data) - set(self.fields)

        if unknown_fields:
            raise serializers.ValidationError({
                field: "Unknown field."
                for field in sorted(unknown_fields)
            })

        return super().to_internal_value(data)


class DocumentPeriodSerializer(DocumentStrictSerializer):

    period_start = serializers.DateField(
        required=False, allow_null=True,
    )

    period_end = serializers.DateField(
        required=False, allow_null=True,
    )

    def validate(self, attrs):
        start = attrs.get("period_start")
        end = attrs.get("period_end")

        if not self.partial and bool(start) != bool(end):
            raise serializers.ValidationError({
                "period_end": "Both reporting period dates are required.",
            })

        if start and end and start > end:
            raise serializers.ValidationError({
                "period_end": "End date cannot be before start date.",
            })

        return attrs


class DocumentGenerateSerializer(DocumentPeriodSerializer):

    campaign_id = serializers.UUIDField()
    template_id = serializers.UUIDField()

    template_version_id = serializers.UUIDField(
        required=False, allow_null=True,
    )

    title = serializers.CharField(
        max_length=255, required=False,
    )

    description = serializers.CharField(
        max_length=20000, required=False, allow_blank=True,
    )

    owner_id = serializers.UUIDField(
        required=False, allow_null=True,
    )

    populate_placeholders = serializers.BooleanField(default=True)


class DocumentBlankSerializer(DocumentPeriodSerializer):

    campaign_id = serializers.UUIDField()
    title = serializers.CharField(max_length=255)

    description = serializers.CharField(
        max_length=20000, required=False, allow_blank=True,
    )

    category = serializers.ChoiceField(
        choices=DocumentTemplateCategory.choices,
        default=DocumentTemplateCategory.CUSTOM,
    )

    owner_id = serializers.UUIDField(
        required=False, allow_null=True,
    )


class DocumentMetadataSerializer(DocumentPeriodSerializer):

    title = serializers.CharField(
        max_length=255, required=False,
    )

    description = serializers.CharField(
        max_length=20000, required=False, allow_blank=True,
    )

    category = serializers.ChoiceField(
        choices=DocumentTemplateCategory.choices,
        required=False,
    )

    owner_id = serializers.UUIDField(required=False)


class DocumentDuplicateSerializer(DocumentStrictSerializer):

    title = serializers.CharField(
        max_length=255, required=False,
    )


class DocumentStatusSerializer(DocumentStrictSerializer):

    status = serializers.ChoiceField(
        choices=DocumentStatus.choices,
    )


class DocumentEmptySerializer(DocumentStrictSerializer):
    pass


class DocumentListFilterSerializer(DocumentStrictSerializer):

    campaign_id = serializers.UUIDField(required=False)
    template_id = serializers.UUIDField(required=False)
    owner_id = serializers.UUIDField(required=False)

    category = serializers.ChoiceField(
        choices=DocumentTemplateCategory.choices,
        required=False,
    )

    status = serializers.ChoiceField(
        choices=DocumentStatus.choices,
        required=False,
    )

    period_start = serializers.DateField(required=False)
    period_end = serializers.DateField(required=False)

    created_from = serializers.DateField(required=False)
    created_to = serializers.DateField(required=False)

    search = serializers.CharField(
        max_length=255, required=False, allow_blank=True,
    )

    is_archived = serializers.BooleanField(default=False)

    ordering = serializers.ChoiceField(
        choices=sorted(DocumentSelector.ORDERING_FIELDS),
        default="-created_at",
    )

    page = serializers.IntegerField(
        min_value=1, required=False,
    )

    page_size = serializers.IntegerField(
        min_value=1, max_value=100, required=False,
    )

    def validate(self, attrs):
        periods = [
            ("period_start", "period_end"),
            ("created_from", "created_to"),
        ]

        for start_field, end_field in periods:
            start = attrs.get(start_field)
            end = attrs.get(end_field)

            if start and end and start > end:
                raise serializers.ValidationError({
                    end_field: "End date cannot be before start date.",
                })

        return attrs


class DocumentUserSerializer(serializers.Serializer):

    id = serializers.ReadOnlyField()
    email = serializers.EmailField(read_only=True)


class DocumentOwnerSerializer(serializers.Serializer):

    id = serializers.UUIDField(read_only=True)
    role = serializers.CharField(read_only=True)
    user = DocumentUserSerializer(read_only=True)


class DocumentTemplateReferenceSerializer(serializers.Serializer):

    id = serializers.UUIDField(read_only=True)
    template_id = serializers.UUIDField(read_only=True)
    version = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    category = serializers.CharField(read_only=True)
    published_at = serializers.DateTimeField(read_only=True)


class DocumentListOutputSerializer(serializers.ModelSerializer):

    workspace_id = serializers.UUIDField(
        source="campaign.workspace_id", read_only=True,
    )

    campaign_id = serializers.UUIDField(read_only=True)

    campaign_name = serializers.CharField(
        source="campaign.name", read_only=True,
    )

    template_version = DocumentTemplateReferenceSerializer(
        read_only=True,
    )

    owner = DocumentOwnerSerializer(read_only=True)
    created_by = DocumentUserSerializer(read_only=True)
    updated_by = DocumentUserSerializer(read_only=True)

    actions = serializers.SerializerMethodField()

    class Meta:
        model = Document

        fields = [
            "id",
            "workspace_id",
            "campaign_id",
            "campaign_name",
            "template_version",
            "title",
            "description",
            "category",
            "owner",
            "status",
            "period_start",
            "period_end",
            "created_by",
            "updated_by",
            "is_archived",
            "archived_at",
            "created_at",
            "updated_at",
            "actions",
        ]

    def get_actions(self, obj):
        return DocumentPermission.get_actions(
            membership=self.context["membership"],
            document=obj,
        )


class DocumentOutputSerializer(DocumentListOutputSerializer):

    class Meta(DocumentListOutputSerializer.Meta):

        fields = [
            *DocumentListOutputSerializer.Meta.fields,
            "structure_snapshot",
            "content",
        ]


class DocumentGenerationPreviewSerializer(serializers.Serializer):

    workspace_id = serializers.UUIDField()
    campaign_id = serializers.UUIDField()
    template_id = serializers.UUIDField()
    template_version_id = serializers.UUIDField()
    template_version = serializers.IntegerField()

    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    category = serializers.CharField()
    owner_id = serializers.UUIDField()

    period_start = serializers.DateField(allow_null=True)
    period_end = serializers.DateField(allow_null=True)

    status = serializers.CharField()

    structure_snapshot = serializers.JSONField()
    content = serializers.JSONField()

    resolved_placeholders = serializers.ListField(
        child=serializers.CharField(),
    )

    unresolved_placeholders = serializers.ListField(
        child=serializers.CharField(),
    )

    empty_fields = serializers.ListField(
        child=serializers.DictField(),
    )

    warnings = serializers.ListField(
        child=serializers.DictField(),
    )