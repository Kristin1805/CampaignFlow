
from django.db.models import QuerySet

from campaignflow.campaigns.models import Campaign


class CampaignSelector:
    ORDERING_FIELDS = {
        "created_at": "created_at",
        "-created_at": "-created_at",
        "starts_on": "starts_on",
        "-starts_on": "-starts_on",
        "name": "name",
        "-name": "-name",
    }

    @staticmethod
    def get_by_id(*, workspace, campaign_id, include_archived=False) -> Campaign | None:
        queryset = Campaign.objects.filter(id=campaign_id, workspace=workspace,).select_related("workspace", "created_by")

        if not include_archived:
            queryset = queryset.filter(is_archived=False)

        return queryset.first()

    @classmethod
    def get_workspace_campaigns(cls, *, workspace, status=None, search=None, ordering="-created_at", include_archived=False,) -> QuerySet[Campaign]:
        queryset = Campaign.objects.filter(workspace=workspace,).select_related("workspace", "created_by")

        if not include_archived:
            queryset = queryset.filter(is_archived=False)

        if status:
            queryset = queryset.filter(status=status)

        if search:
            queryset = queryset.filter(name__icontains=search.strip())

        ordering_field = cls.ORDERING_FIELDS.get(ordering, "-created_at")

        return queryset.order_by(ordering_field, "id")

    @staticmethod
    def get_for_update(*, workspace, campaign_id, include_archived=False):
        queryset = Campaign.objects.select_for_update().filter(id=campaign_id, workspace=workspace,)

        if not include_archived:
            queryset = queryset.filter(is_archived=False)

        return queryset.first()
