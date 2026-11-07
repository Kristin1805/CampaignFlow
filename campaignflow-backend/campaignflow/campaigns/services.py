
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from campaignflow.campaigns.models import Campaign
from campaignflow.campaigns.selectors import CampaignSelector


class CampaignService:
    ALLOWED_TRANSITIONS = {
        Campaign.Status.DRAFT: {
            Campaign.Status.PLANNING,
            Campaign.Status.CANCELLED,
        },
        Campaign.Status.PLANNING: {
            Campaign.Status.ACTIVE,
            Campaign.Status.CANCELLED,
        },
        Campaign.Status.ACTIVE: {
            Campaign.Status.PAUSED,
            Campaign.Status.COMPLETED,
            Campaign.Status.CANCELLED,
        },
        Campaign.Status.PAUSED: {
            Campaign.Status.ACTIVE,
            Campaign.Status.CANCELLED,
        },
        Campaign.Status.COMPLETED: set(),
        Campaign.Status.CANCELLED: set(),
    }

    @staticmethod
    def validate_campaign(campaign):
        try:
            campaign.full_clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise ValidationError(exc.message_dict)
            raise ValidationError(exc.messages)

    @classmethod
    @transaction.atomic
    def create_campaign(cls, *, workspace, user, data):
        campaign = Campaign(workspace=workspace, created_by=user, status=Campaign.Status.DRAFT, **data,)

        cls.validate_campaign(campaign)
        campaign.save()

        return campaign

    @classmethod
    @transaction.atomic
    def update_campaign(cls, *, workspace, campaign_id, data):
        campaign = CampaignSelector.get_for_update(workspace=workspace, campaign_id=campaign_id,)

        if campaign is None:
            raise NotFound("Campaign not found.")

        for field, value in data.items():
            setattr(campaign, field, value)

        cls.validate_campaign(campaign)
        campaign.save()

        return campaign

    @classmethod
    @transaction.atomic
    def change_status(cls, *, workspace, campaign_id, new_status):
        campaign = CampaignSelector.get_for_update(workspace=workspace, campaign_id=campaign_id,)

        if campaign is None:
            raise NotFound("Campaign not found.")

        if campaign.status == new_status:
            return campaign

        allowed = cls.ALLOWED_TRANSITIONS.get(campaign.status, set())

        if new_status not in allowed:
            raise ValidationError({
                "status": f"Cannot change campaign status from '{campaign.status}' to '{new_status}'."
            })

        campaign.status = new_status
        cls.validate_campaign(campaign)
        campaign.save(update_fields=["status", "updated_at"])

        return campaign

    @classmethod
    @transaction.atomic
    def archive_campaign(cls, *, workspace, campaign_id):
        campaign = CampaignSelector.get_for_update(workspace=workspace,campaign_id=campaign_id,)

        if campaign is None:
            raise NotFound("Campaign not found.")

        campaign.is_archived = True
        campaign.archived_at = timezone.now()
        campaign.save(update_fields=["is_archived", "archived_at", "updated_at"])

        return campaign
