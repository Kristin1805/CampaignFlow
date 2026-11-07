from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from campaignflow.approvals.models import TaskApproval, ApprovalStatus
from campaignflow.approvals.permissions import TaskApprovalPermission
from campaignflow.approvals.selectors import TaskApprovalSelector
from campaignflow.organization.models import WorkspaceMember
from campaignflow.tasks.enums import TaskStatus
from campaignflow.tasks.models import Task, TaskActivityType
from campaignflow.tasks.services import (
    CampaignRevisionService,
    TaskActivityService,
    TaskStatusService,
)


class TaskApprovalService:
    @staticmethod
    def validate_message(message, field="message", required=False):
        if not isinstance(message, str):
            raise ValidationError({field: "Must be a string."})
        message = message.strip()
        if required and not message:
            raise ValidationError({field: "This field is required."})
        if len(message) > 5000:
            raise ValidationError({field: "Cannot exceed 5000 characters."})
        return message

    @staticmethod
    def get_reviewer(*, workspace, reviewer_id, task):
        reviewer = WorkspaceMember.objects.select_related("user").filter(
            id=reviewer_id, workspace=workspace, user__is_active=True
        ).first()
        if reviewer is None:
            raise ValidationError({"reviewer_id": "Active workspace reviewer not found."})
        if reviewer.role == WorkspaceMember.Role.GUEST:
            raise ValidationError({"reviewer_id": "Guests cannot review tasks."})
        if task.assignee_id == reviewer.id:
            raise ValidationError({"reviewer_id": "The task assignee cannot review their own task."})
        return reviewer

    @staticmethod
    def get_locked_task(*, workspace, task_id):
        campaign_id = Task.objects.filter(id=task_id, campaign__workspace=workspace, campaign__is_archived=False,).values_list("campaign_id", flat=True).first()

        if campaign_id is None:
            raise NotFound("Task not found.")

        CampaignRevisionService.lock_campaign(workspace=workspace, campaign_id=campaign_id,)

        task = TaskApprovalSelector.get_task(workspace=workspace, task_id=task_id, for_update=True,)

        if task is None:
            raise NotFound("Task not found.")

        return task

    @classmethod
    def get_locked_pending_approval(cls, *, workspace, task_id, approval_id):
        task = cls.get_locked_task(workspace=workspace, task_id=task_id,)

        approval = TaskApproval.objects.select_for_update().filter(id=approval_id, task=task,).first()

        if approval is None:
            raise NotFound("Approval not found.")
        if approval.status != ApprovalStatus.PENDING:
            raise ValidationError({"approval": "This approval has already been processed."})
        if task.status != TaskStatus.IN_REVIEW:
            raise ValidationError({"status": "Task is not currently in review."})
        return task, approval

    @classmethod
    @transaction.atomic
    def submit_for_review(
        cls,
        *,
        workspace,
        task_id,
        requested_by,
        membership,
        reviewer_id,
        submission_message="",
    ):
        task = cls.get_locked_task(
            workspace=workspace,
            task_id=task_id,
        )

        TaskApprovalPermission.require_submit(membership=membership, task=task,)

        if task.status != TaskStatus.IN_PROGRESS:
            raise ValidationError({"status": "Only in-progress tasks can be submitted for review."})
        if TaskApprovalSelector.get_pending_approval(task=task):
            raise ValidationError({"approval": "A pending approval already exists."})

        reviewer = cls.get_reviewer(workspace=workspace,reviewer_id=reviewer_id,task=task,)

        message = cls.validate_message(submission_message,"submission_message",)

        approval = TaskApproval.objects.create(
            task=task,
            requested_by=requested_by,
            reviewer=reviewer,
            submission_message=message,
        )

        TaskStatusService.change_status(
            workspace=workspace,
            task_id=task.id,
            new_status=TaskStatus.IN_REVIEW,
            changed_by=requested_by,
            approval_context=True,
        )

        TaskActivityService.record(
            task=task,
            actor=requested_by,
            action=TaskActivityType.APPROVAL_REQUESTED,
            metadata={
                "approval_id": str(approval.id),
                "reviewer_id": str(reviewer.id),
                "previous_status": None,
                "new_status": ApprovalStatus.PENDING,
            },
        )
        return approval

    @classmethod
    @transaction.atomic
    def approve(
        cls,
        *,
        workspace,
        task_id,
        approval_id,
        user,
        membership,
        decision_comment="",
    ):
        task, approval = cls.get_locked_pending_approval(
            workspace=workspace,
            task_id=task_id,
            approval_id=approval_id,
        )

        TaskApprovalPermission.require_decision(
            membership=membership,
            approval=approval,
            user=user,
        )

        comment = cls.validate_message(decision_comment, "decision_comment",)

        approval.status = ApprovalStatus.APPROVED
        approval.decision_comment = comment
        approval.decided_by = user
        approval.decided_at = timezone.now()

        approval.save(update_fields=["status", "decision_comment", "decided_by", "decided_at",])

        TaskStatusService.change_status(
            workspace=workspace,
            task_id=task.id,
            new_status=TaskStatus.APPROVED,
            changed_by=user,
            approval_context=True,
        )

        TaskActivityService.record(
            task=task,
            actor=user,
            action=TaskActivityType.APPROVAL_APPROVED,
            metadata={
                "approval_id": str(approval.id),
                "reviewer_id": str(approval.reviewer_id),
                "previous_status": ApprovalStatus.PENDING,
                "new_status": ApprovalStatus.APPROVED,
            },
        )
        return approval

    @classmethod
    @transaction.atomic
    def request_changes(
        cls,
        *,
        workspace,
        task_id,
        approval_id,
        user,
        membership,
        decision_comment,
    ):
        task, approval = cls.get_locked_pending_approval(workspace=workspace, task_id=task_id, approval_id=approval_id,)

        TaskApprovalPermission.require_decision(membership=membership, approval=approval, user=user,)

        comment = cls.validate_message(decision_comment, "decision_comment", required=True,)

        approval.status = ApprovalStatus.CHANGES_REQUESTED
        approval.decision_comment = comment
        approval.decided_by = user
        approval.decided_at = timezone.now()

        approval.save(update_fields=["status", "decision_comment", "decided_by", "decided_at",])

        TaskStatusService.change_status(
            workspace=workspace,
            task_id=task.id,
            new_status=TaskStatus.CHANGES_REQUESTED,
            changed_by=user,
            approval_context=True,
        )

        TaskActivityService.record(
            task=task,
            actor=user,
            action=TaskActivityType.APPROVAL_CHANGES_REQUESTED,
            metadata={
                "approval_id": str(approval.id),
                "reviewer_id": str(approval.reviewer_id),
                "previous_status": ApprovalStatus.PENDING,
                "new_status": ApprovalStatus.CHANGES_REQUESTED,
                "decision_comment": comment,
            },
        )
        return approval

    @classmethod
    @transaction.atomic
    def cancel(
        cls,
        *,
        workspace,
        task_id,
        approval_id,
        user,
        membership,
        reason="",
    ):
        task, approval = cls.get_locked_pending_approval(workspace=workspace, task_id=task_id, approval_id=approval_id,)

        TaskApprovalPermission.require_cancel(membership=membership, approval=approval, user=user,)

        comment = cls.validate_message(reason, "reason",)

        approval.status = ApprovalStatus.CANCELLED
        approval.decision_comment = comment
        approval.decided_by = user
        approval.cancelled_at = timezone.now()

        approval.save(update_fields=["status", "decision_comment", "decided_by", "cancelled_at",])

        TaskStatusService.change_status(
            workspace=workspace,
            task_id=task.id,
            new_status=TaskStatus.IN_PROGRESS,
            changed_by=user,
            approval_context=True,
        )

        TaskActivityService.record(
            task=task,
            actor=user,
            action=TaskActivityType.APPROVAL_CANCELLED,
            metadata={
                "approval_id": str(approval.id),
                "reviewer_id": str(approval.reviewer_id),
                "previous_status": ApprovalStatus.PENDING,
                "new_status": ApprovalStatus.CANCELLED,
                "reason": comment,
            },
        )
        return approval
