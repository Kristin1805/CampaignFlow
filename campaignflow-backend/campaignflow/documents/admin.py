from django.contrib import admin

from campaignflow.documents.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "campaign",
        "category",
        "status",
        "owner",
        "is_archived",
        "created_at",
    )

    list_filter = (
        "category",
        "status",
        "is_archived",
        "created_at",
    )

    search_fields = (
        "title",
        "description",
        "campaign__name",
        "owner__user__email",
    )

    list_select_related = (
        "campaign",
        "owner",
        "owner__user",
    )

    readonly_fields = tuple(
        field.name for field in Document._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False