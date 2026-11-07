
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

    CREATE_FIELDS = {
        "name",
        "description",
        "goal",
        "starts_on",
        "ends_on",
        "launch_at",
        "budget_total",
    }

    UPDATE_FIELDS = CREATE_FIELDS

    @staticmethod
    def validate_campaign(campaign):
        try:
            campaign.full_clean()
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise ValidationError(exc.message_dict)
            raise ValidationError(exc.messages)

    @staticmethod
    def validate_fields(*, data, allowed_fields):
        if not isinstance(data, dict):
            raise ValidationError({
                "data": "Expected an object."
            })

        protected = {
            "id",
            "workspace",
            "workspace_id",
            "created_by",
            "created_by_id",
            "created_at",
            "updated_at",
            "revision",
            "status",
            "is_archived",
            "archived_at",
        }

        protected_fields = set(data) & protected

        if protected_fields:
            raise ValidationError({
                "fields": (
                    "These fields cannot be modified directly: "
                    + ", ".join(sorted(protected_fields))
                )
            })

        unknown = set(data) - allowed_fields

        if unknown:
            raise ValidationError({
                "fields": (
                    "Unsupported campaign fields: "
                    + ", ".join(sorted(unknown))
                )
            })

    @classmethod
    @transaction.atomic
    def create_campaign(cls, *, workspace, user, data):
        data = data.copy()

        cls.validate_fields(data=data, allowed_fields=cls.CREATE_FIELDS,)

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

        data = data.copy()

        cls.validate_fields(data=data, allowed_fields=cls.UPDATE_FIELDS,)

        changed_fields = set()
        launch_at_changed = False

        for field, value in data.items():
            previous_value = getattr(campaign, field)

            if previous_value == value:
                continue

            setattr(campaign, field, value)
            changed_fields.add(field)

            if field == "launch_at":
                launch_at_changed = True

        if not changed_fields:
            return campaign

        if launch_at_changed:
            campaign.revision += 1
            changed_fields.add("revision")

        cls.validate_campaign(campaign)

        campaign.save(update_fields=[*sorted(changed_fields), "updated_at"])

        return campaign

    @classmethod
    @transaction.atomic
    def change_status(cls, *, workspace, campaign_id, new_status):
        campaign = CampaignSelector.get_for_update(workspace=workspace, campaign_id=campaign_id,)

        if campaign is None:
            raise NotFound("Campaign not found.")

        if campaign.status == new_status:
            return campaign

        allowed = cls.ALLOWED_TRANSITIONS.get(campaign.status, set(),)

        if new_status not in allowed:
            raise ValidationError({
                "status": (
                    f"Cannot change campaign status "
                    f"from '{campaign.status}' to '{new_status}'."
                )
            })

        campaign.status = new_status
        cls.validate_campaign(campaign)
        campaign.save(update_fields=["status", "updated_at"])

        return campaign

    @classmethod
    @transaction.atomic
    def archive_campaign(cls, *, workspace, campaign_id):
        campaign = CampaignSelector.get_for_update(workspace=workspace, campaign_id=campaign_id,)

        if campaign is None:
            raise NotFound("Campaign not found.")

        if campaign.is_archived:
            return campaign

        campaign.is_archived = True
        campaign.archived_at = timezone.now()

        campaign.save(update_fields=["is_archived", "archived_at", "updated_at",])

        return campaign
