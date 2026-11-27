from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from campaignflow.organization.models import Workspace
from campaignflow.documents.services import DocumentTemplateDefaultsService


class Command(BaseCommand):
    help = "Initialize predefined document templates for existing workspaces."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-id", type=UUID, required=False)

    def handle(self, *args, **options):
        workspace_id = options.get("workspace_id")

        queryset = Workspace.objects.select_related("created_by")

        if workspace_id:
            queryset = queryset.filter(id=workspace_id)

            if not queryset.exists():
                raise CommandError("Workspace not found.")

        total_workspaces = 0
        total_created = 0

        for workspace in queryset.iterator(chunk_size=100):
            created = DocumentTemplateDefaultsService.initialize_workspace(
                workspace=workspace,
            )

            total_workspaces += 1
            total_created += created

            self.stdout.write(
                f"{workspace.name}: {created} templates created.",
            )

        self.stdout.write(self.style.SUCCESS(
            f"Processed {total_workspaces} workspaces. "
            f"Created {total_created} document templates.",
        ))