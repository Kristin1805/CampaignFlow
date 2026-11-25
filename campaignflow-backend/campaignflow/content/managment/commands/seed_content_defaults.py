from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from campaignflow.content.services import ContentDefaultsService
from campaignflow.organization.models import Workspace


class Command(BaseCommand):
    help = "Initialize default content platforms and formats for workspaces."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-id", type=str, required=False)

    def handle(self, *args, **options):
        workspace_id = options.get("workspace_id")
        workspaces = Workspace.objects.all()

        if workspace_id:
            try:
                workspace_id = UUID(workspace_id)
            except ValueError as exc:
                raise CommandError("Invalid workspace UUID.") from exc

            workspaces = workspaces.filter(id=workspace_id)

            if not workspaces.exists():
                raise CommandError("Workspace not found.")

        count = 0

        for workspace in workspaces.iterator():
            ContentDefaultsService.initialize_workspace(workspace=workspace)

            self.stdout.write(self.style.SUCCESS(
                f"Content defaults initialized for {workspace.name}."
            ))

            count += 1

        self.stdout.write(self.style.SUCCESS(f"Processed {count} workspace(s)."))