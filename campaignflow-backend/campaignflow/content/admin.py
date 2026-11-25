from django.contrib import admin

from campaignflow.content.models import (
    ContentItem, ContentPlatform, ContentFormat, ContentStatusHistory, PostingPlanPreference,
)


@admin.register(ContentPlatform)
class ContentPlatformAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "workspace", "is_default", "created_at")
    list_filter = ("is_default", "workspace")
    search_fields = ("name", "code", "workspace__name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ContentFormat)
class ContentFormatAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "workspace", "is_default", "created_at")
    list_filter = ("is_default", "workspace")
    search_fields = ("name", "code", "workspace__name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ContentItem)
class ContentItemAdmin(admin.ModelAdmin):
    list_display = (
        "title", "campaign", "platform", "content_format",
        "status", "assignee", "publication_at", "is_archived",
    )
    list_filter = ("status", "platform", "content_format", "is_archived")
    search_fields = ("title", "topic", "copy", "description", "campaign__name")
    list_select_related = ("campaign", "platform", "content_format", "assignee", "assignee__user")
    readonly_fields = tuple(field.name for field in ContentItem._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ContentStatusHistory)
class ContentStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("content_item", "previous_status", "new_status", "changed_by", "created_at")
    list_filter = ("previous_status", "new_status")
    search_fields = ("content_item__title", "changed_by__email", "comment")
    list_select_related = ("content_item", "changed_by")
    readonly_fields = tuple(field.name for field in ContentStatusHistory._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PostingPlanPreference)
class PostingPlanPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "id", "workspace", "user",
        "default_ordering", "default_grouping", "updated_at",
    )

    list_filter = ("default_grouping", "created_at", "updated_at")

    search_fields = (
        "workspace__name",
        "user__email",
    )

    readonly_fields = ("id", "created_at", "updated_at")

    list_select_related = ("workspace", "user")