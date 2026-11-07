from django.urls import path

from campaignflow.approvals.apis import (
    TaskApprovalListCreateApi, TaskApprovalDetailApi,
    TaskApprovalApproveApi, TaskApprovalRequestChangesApi,
    TaskApprovalCancelApi, TaskApprovalPendingApi,
)

urlpatterns = [
    path("workspaces/<uuid:workspace_id>/approvals/pending/", TaskApprovalPendingApi.as_view(), name="task-approvals-pending",),
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/approvals/", TaskApprovalListCreateApi.as_view(), name="task-approval-list-create",),
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/approvals/<uuid:approval_id>/", TaskApprovalDetailApi.as_view(), name="task-approval-detail",),
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/approvals/<uuid:approval_id>/approve/", TaskApprovalApproveApi.as_view(), name="task-approval-approve",),
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/approvals/<uuid:approval_id>/request-changes/", TaskApprovalRequestChangesApi.as_view(), name="task-approval-request-changes",),
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/approvals/<uuid:approval_id>/cancel/", TaskApprovalCancelApi.as_view(), name="task-approval-cancel",),
]
