
from django.apps import apps
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from campaignflow.campaigns.models import Campaign
from campaignflow.organization.models import WorkspaceMember
from campaignflow.tasks.enums import TaskStatus
from campaignflow.tasks.models import (
    Task, TaskDependency, TaskStatusHistory, TaskComment, TaskActivity, TaskActivityType,
)
from campaignflow.tasks.selectors import TaskDependencySelector, TaskStatusSelector, TaskCommentSelector
from campaignflow.tasks.permissions import TaskCommentPermission


class TaskActivityService:
    @staticmethod
    def record(*, task, actor, action, metadata=None):
        return TaskActivity.objects.create(task=task, actor=actor, action=action, metadata=metadata or {})


class CampaignRevisionService:
    @staticmethod
    def lock_campaign(*, workspace, campaign_id):
        campaign = Campaign.objects.select_for_update().filter(
            id=campaign_id, workspace=workspace, is_archived=False,
        ).first()
        if campaign is None:
            raise NotFound("Campaign not found.")
        return campaign

    @staticmethod
    def increment(*, campaign):
        Campaign.objects.filter(pk=campaign.pk).update(revision=F("revision") + 1)
        campaign.revision += 1


class TaskService:
    @staticmethod
    def validate_assignee(*, workspace, assignee_id):
        if assignee_id is None:
            return None

        member = WorkspaceMember.objects.filter(id=assignee_id, workspace=workspace).first()
        if member is None:
            raise ValidationError({"assignee_id": "Workspace member not found."})

        return member

    @staticmethod
    def validate_required_skill(*, workspace, required_skill_id):
        if required_skill_id is None:
            return None

        Skill = apps.get_model("organization", "Skill")
        skill = Skill.objects.filter(id=required_skill_id).first()
        if skill is None:
            raise ValidationError({"required_skill_id": "Skill not found."})

        return skill

    @staticmethod
    def validate_task(task):
        try:
            task.full_clean()
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)

    @classmethod
    @transaction.atomic
    def create_task(cls, *, workspace, campaign, data, actor):
        if campaign.workspace_id != workspace.id or campaign.is_archived:
            raise NotFound("Campaign not found.")

        campaign = CampaignRevisionService.lock_campaign(workspace=workspace, campaign_id=campaign.id)

        data = data.copy()
        protected = {
            "status", "planned_start", "planned_end", "latest_start_at", "is_critical", "slack_hours",
            "campaign", "campaign_id", "id", "created_at", "updated_at",
        }
        if protected.intersection(data):
            raise ValidationError({"fields": "Status and optimizer plan fields cannot be set here."})

        allowed = {
            "title", "description", "priority", "estimated_hours", "actual_hours",
            "due_at", "assignee_id", "required_skill_id",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ValidationError({"fields": f"Unsupported fields: {', '.join(sorted(unknown))}"})

        assignee_id = data.pop("assignee_id", None)
        assignee = cls.validate_assignee(workspace=workspace, assignee_id=assignee_id)

        required_skill_id = data.pop("required_skill_id", None)
        required_skill = cls.validate_required_skill(workspace=workspace, required_skill_id=required_skill_id)

        task = Task(campaign=campaign, assignee=assignee, required_skill=required_skill, **data)
        cls.validate_task(task)
        task.save()

        TaskActivityService.record(
            task=task, actor=actor, action=TaskActivityType.CREATED,
            metadata={"title": task.title},
        )

        if assignee is not None:
            TaskActivityService.record(
                task=task, actor=actor, action=TaskActivityType.ASSIGNED,
                metadata={"previous_assignee_id": None, "assignee_id": str(assignee.id)},
            )

        CampaignRevisionService.increment(campaign=campaign)
        return task

    @classmethod
    @transaction.atomic
    def update_task(cls, *, workspace, task_id, data, actor):
        campaign_id = Task.objects.filter(id=task_id, campaign__workspace=workspace, campaign__is_archived=False,).values_list("campaign_id", flat=True).first()
        if campaign_id is None:
            raise NotFound("Task not found.")

        campaign = CampaignRevisionService.lock_campaign(workspace=workspace, campaign_id=campaign_id)
        task = Task.objects.select_for_update().filter(
            id=task_id, campaign__workspace=workspace, campaign__is_archived=False
        ).first()
        if task is None:
            raise NotFound("Task not found.")

        data = data.copy()
        protected = {
            "status", "planned_start", "planned_end", "latest_start_at", "is_critical", "slack_hours",
            "campaign", "campaign_id", "id", "created_at", "updated_at",
        }
        if protected.intersection(data):
            raise ValidationError({"fields": "Status and protected task fields cannot be updated here."})

        allowed = {
            "title", "description", "priority", "estimated_hours", "actual_hours",
            "due_at", "assignee_id", "required_skill_id",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ValidationError({"fields": f"Unsupported fields: {', '.join(sorted(unknown))}"})

        changes = {}
        old_assignee_id = task.assignee_id

        if "assignee_id" in data:
            assignee = cls.validate_assignee(workspace=workspace, assignee_id=data.pop("assignee_id"))
            if task.assignee_id != (assignee.id if assignee else None):
                task.assignee = assignee
                changes["assignee_id"] = {
                    "old": str(old_assignee_id) if old_assignee_id else None,
                    "new": str(task.assignee_id) if task.assignee_id else None,
                }

        if "required_skill_id" in data:
            required_skill = cls.validate_required_skill(workspace=workspace, required_skill_id=data.pop("required_skill_id"))
            if task.required_skill_id != (required_skill.id if required_skill else None):
                changes["required_skill_id"] = {
                    "old": str(task.required_skill_id) if task.required_skill_id else None,
                    "new": str(required_skill.id) if required_skill else None,
                }
                task.required_skill = required_skill

        for field, value in data.items():
            old_value = getattr(task, field)
            if old_value != value:
                changes[field] = {
                    "old": str(old_value) if old_value is not None else None,
                    "new": str(value) if value is not None else None,
                }
                setattr(task, field, value)

        if not changes:
            return task

        cls.validate_task(task)
        task.save()

        TaskActivityService.record(
            task=task, actor=actor, action=TaskActivityType.UPDATED,
            metadata={"changes": changes},
        )

        if "assignee_id" in changes:
            TaskActivityService.record(
                task=task, actor=actor, action=TaskActivityType.ASSIGNED,
                metadata={
                    "previous_assignee_id": changes["assignee_id"]["old"],
                    "assignee_id": changes["assignee_id"]["new"],
                },
            )

        CampaignRevisionService.increment(campaign=campaign)
        return task

    @staticmethod
    @transaction.atomic
    def delete_task(*, workspace, task_id, actor=None):
        campaign_id = Task.objects.filter(
            id=task_id, campaign__workspace=workspace, campaign__is_archived=False,
        ).values_list("campaign_id", flat=True).first()
        if campaign_id is None:
            raise NotFound("Task not found.")

        campaign = CampaignRevisionService.lock_campaign(workspace=workspace, campaign_id=campaign_id)
        task = Task.objects.select_for_update().filter(
            id=task_id, campaign__workspace=workspace, campaign__is_archived=False
        ).first()
        if task is None:
            raise NotFound("Task not found.")

        from campaignflow.approvals.models import TaskApproval, ApprovalStatus

        if TaskApproval.objects.filter(task=task, status=ApprovalStatus.PENDING).exists():
            raise ValidationError({"approval": "Cannot delete a task with a pending approval. Cancel the approval first."})

        task.delete()
        CampaignRevisionService.increment(campaign=campaign)


class TaskDependencyService:
    @staticmethod
    def creates_cycle(*, graph, task_id, depends_on_task_id):
        adjacency = {}

        for source, target in graph:
            adjacency.setdefault(source, set()).add(target)

        stack = [depends_on_task_id]
        visited = set()

        while stack:
            current = stack.pop()

            if current == task_id:
                return True

            if current in visited:
                continue

            visited.add(current)
            stack.extend(adjacency.get(current, set()) - visited)

        return False

    @classmethod
    @transaction.atomic
    def create_dependency(cls, *, workspace, task_id, depends_on_task_id, actor, lag_hours=0,):
        if str(task_id) == str(depends_on_task_id):
            raise ValidationError({"depends_on_task_id": "A task cannot depend on itself."})

        campaign_id = Task.objects.filter(id=task_id,campaign__workspace=workspace,campaign__is_archived=False,).values_list("campaign_id", flat=True).first()

        if campaign_id is None:
            raise NotFound("Task not found.")

        campaign = CampaignRevisionService.lock_campaign(workspace=workspace, campaign_id=campaign_id,)

        task = TaskDependencySelector.get_task(workspace=workspace, task_id=task_id,)

        if task is None or task.campaign_id != campaign.id:
            raise NotFound("Task not found.")

        depends_on_task = TaskDependencySelector.get_task(workspace=workspace, task_id=depends_on_task_id,)

        if depends_on_task is None:
            raise NotFound("Dependency task not found.")

        if task.campaign_id != depends_on_task.campaign_id:
            raise ValidationError({"depends_on_task_id": ("Tasks must belong to the same campaign.")})

        if TaskDependency.objects.filter(task=task, depends_on_task=depends_on_task,).exists():
            raise ValidationError({"depends_on_task_id": "This dependency already exists."})

        graph = TaskDependencySelector.get_campaign_graph(campaign_id=campaign.id,)

        if cls.creates_cycle(graph=graph, task_id=task.id, depends_on_task_id=depends_on_task.id,):
            raise ValidationError({"depends_on_task_id": "Circular dependency detected."})

        dependency = TaskDependency(task=task, depends_on_task=depends_on_task, lag_hours=lag_hours,)

        try:
            dependency.full_clean()
        except DjangoValidationError as exc:
            raise ValidationError(
                exc.message_dict
                if hasattr(exc, "message_dict")
                else exc.messages
            )

        dependency.save()

        TaskActivityService.record(
            task=task,
            actor=actor,
            action=TaskActivityType.DEPENDENCY_ADDED,
            metadata={
                "dependency_id": str(dependency.id),
                "depends_on_task_id": str(depends_on_task.id),
                "lag_hours": str(dependency.lag_hours),
            },
        )

        CampaignRevisionService.increment(campaign=campaign)

        return dependency

    @staticmethod
    @transaction.atomic
    def delete_dependency(*, workspace, task_id, dependency_id, actor,):
        campaign_id = Task.objects.filter(id=task_id, campaign__workspace=workspace, campaign__is_archived=False,).values_list("campaign_id", flat=True).first()

        if campaign_id is None:
            raise NotFound("Task not found.")

        campaign = CampaignRevisionService.lock_campaign(workspace=workspace, campaign_id=campaign_id,)

        dependency = TaskDependencySelector.get_dependency(workspace=workspace, task_id=task_id, dependency_id=dependency_id,)

        if (dependency is None or dependency.task.campaign_id != campaign.id):
            raise NotFound("Dependency not found.")

        TaskActivityService.record(
            task=dependency.task,
            actor=actor,
            action=TaskActivityType.DEPENDENCY_REMOVED,
            metadata={
                "dependency_id": str(dependency.id),
                "depends_on_task_id": str(dependency.depends_on_task_id),
            },
        )

        dependency.delete()

        CampaignRevisionService.increment(campaign=campaign)


class TaskStatusService:
    ALLOWED_TRANSITIONS = {
        TaskStatus.BACKLOG: {TaskStatus.TODO, TaskStatus.CANCELLED},
        TaskStatus.TODO: {TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
        TaskStatus.IN_PROGRESS: {TaskStatus.TODO, TaskStatus.IN_REVIEW, TaskStatus.CANCELLED},
        TaskStatus.IN_REVIEW: {
            TaskStatus.IN_PROGRESS, TaskStatus.CHANGES_REQUESTED,
            TaskStatus.APPROVED, TaskStatus.CANCELLED,
        },
        TaskStatus.CHANGES_REQUESTED: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
        TaskStatus.APPROVED: {TaskStatus.COMPLETED, TaskStatus.IN_REVIEW, TaskStatus.CANCELLED},
        TaskStatus.COMPLETED: set(),
        TaskStatus.CANCELLED: set(),
    }

    @staticmethod
    def validate_dependencies(*, task):
        dependencies = TaskStatusSelector.get_incomplete_dependencies(task=task)
        blocking_tasks = [
            {"id": str(dep.depends_on_task_id), "title": dep.depends_on_task.title}
            for dep in dependencies
        ]

        if blocking_tasks:
            raise ValidationError({
                "dependencies": "Cannot start task while prerequisite tasks are incomplete.",
                "blocking_tasks": blocking_tasks,
            })

    @classmethod
    @transaction.atomic
    def change_status(cls, *, workspace, task_id, new_status, changed_by, approval_context=False):
        campaign_id = Task.objects.filter(
            id=task_id, campaign__workspace=workspace, campaign__is_archived=False,
        ).values_list("campaign_id", flat=True).first()
        if campaign_id is None:
            raise NotFound("Task not found.")

        campaign = CampaignRevisionService.lock_campaign(workspace=workspace, campaign_id=campaign_id)
        task = TaskStatusSelector.get_task(workspace=workspace, task_id=task_id, for_update=True)
        if task is None:
            raise NotFound("Task not found.")

        if task.status == new_status:
            return task

        allowed = cls.ALLOWED_TRANSITIONS.get(task.status, set())
        if new_status not in allowed:
            raise ValidationError({
                "status": f"Cannot change task status from '{task.status}' to '{new_status}'."
            })

        approval_statuses = {
            TaskStatus.IN_REVIEW,
            TaskStatus.APPROVED,
            TaskStatus.CHANGES_REQUESTED,
        }
        if not approval_context and (task.status == TaskStatus.IN_REVIEW or new_status in approval_statuses):
            raise ValidationError({"status": "Approval-related transitions must use the Approval API."})

        if new_status == TaskStatus.IN_PROGRESS:
            cls.validate_dependencies(task=task)

        previous_status = task.status
        task.status = new_status
        task.save(update_fields=["status", "updated_at"])

        TaskStatusHistory.objects.create(task=task, previous_status=previous_status, new_status=new_status, changed_by=changed_by)
        TaskActivityService.record(task=task, actor=changed_by, action=TaskActivityType.STATUS_CHANGED, metadata={"previous_status": previous_status, "new_status": new_status},)
        CampaignRevisionService.increment(campaign=campaign)
        return task


class TaskCommentService:
    @staticmethod
    def validate_content(content):
        if not isinstance(content, str) or not content.strip():
            raise ValidationError({"content": "Comment cannot be empty."})
        content = content.strip()
        if len(content) > 5000:
            raise ValidationError({"content": "Comment cannot exceed 5000 characters."})
        return content

    @classmethod
    @transaction.atomic
    def create_comment(cls, *, workspace, task_id, author, content):
        task = TaskCommentSelector.get_task(workspace=workspace, task_id=task_id)
        if task is None:
            raise NotFound("Task not found.")

        comment = TaskComment.objects.create(task=task, author=author, content=cls.validate_content(content))
        TaskActivityService.record(
            task=task, actor=author, action=TaskActivityType.COMMENT_ADDED,
            metadata={"comment_id": str(comment.id)},
        )
        return comment

    @classmethod
    @transaction.atomic
    def update_comment(cls, *, workspace, task_id, comment_id, user, membership, content):
        comment = TaskCommentSelector.get_comment(workspace=workspace, task_id=task_id, comment_id=comment_id, for_update=True)
        if comment is None or comment.task.campaign.is_archived:
            raise NotFound("Comment not found.")

        TaskCommentPermission.require_edit_access(membership=membership, comment=comment, user=user)

        new_content = cls.validate_content(content)
        if comment.content == new_content:
            return comment

        comment.content = new_content
        comment.save(update_fields=["content", "updated_at"])

        TaskActivityService.record(
            task=comment.task, actor=user, action=TaskActivityType.COMMENT_UPDATED,
            metadata={"comment_id": str(comment.id)},
        )
        return comment

    @classmethod
    @transaction.atomic
    def delete_comment(cls, *, workspace, task_id, comment_id, user, membership):
        comment = TaskCommentSelector.get_comment(workspace=workspace, task_id=task_id, comment_id=comment_id, for_update=True)
        if comment is None or comment.task.campaign.is_archived:
            raise NotFound("Comment not found.")

        TaskCommentPermission.require_edit_access(membership=membership, comment=comment, user=user)

        comment.is_deleted = True
        comment.deleted_at = timezone.now()
        comment.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

        TaskActivityService.record(
            task=comment.task, actor=user, action=TaskActivityType.COMMENT_DELETED,
            metadata={"comment_id": str(comment.id)},
        )
