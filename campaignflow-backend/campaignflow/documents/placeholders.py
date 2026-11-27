PLACEHOLDER_REGISTRY = {
    "workspace.name": {
        "label": "Workspace name",
        "data_type": "text",
        "source": "workspace",
    },
    "campaign.name": {
        "label": "Campaign name",
        "data_type": "text",
        "source": "campaign",
    },
    "campaign.description": {
        "label": "Campaign description",
        "data_type": "long_text",
        "source": "campaign",
    },
    "campaign.objectives": {
        "label": "Campaign objectives",
        "data_type": "long_text",
        "source": "campaign",
    },
    "campaign.start_date": {
        "label": "Campaign start date",
        "data_type": "date",
        "source": "campaign",
    },
    "campaign.launch_date": {
        "label": "Campaign launch date",
        "data_type": "date",
        "source": "campaign",
    },
    "campaign.team_members": {
        "label": "Campaign team members",
        "data_type": "collection",
        "source": "organization",
    },
    "campaign.tasks": {
        "label": "Campaign tasks",
        "data_type": "collection",
        "source": "tasks",
    },
    "campaign.publications": {
        "label": "Planned publications",
        "data_type": "collection",
        "source": "content",
    },
}


class DocumentPlaceholderRegistry:

    @staticmethod
    def exists(*, key):
        return key in PLACEHOLDER_REGISTRY

    @staticmethod
    def get(*, key):
        return PLACEHOLDER_REGISTRY.get(key)

    @staticmethod
    def get_all():
        return [
            {"key": key, **definition}
            for key, definition in PLACEHOLDER_REGISTRY.items()
        ]