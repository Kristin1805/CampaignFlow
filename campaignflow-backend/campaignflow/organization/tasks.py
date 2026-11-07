from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_workspace_invitation_email(self, *, email: str, workspace_name: str, token: str):
    frontend_url = settings.FRONTEND_URL.rstrip("/")
    invitation_url = f"{frontend_url}/invitations/{token}"

    send_mail(
        subject=f"Invitation to join {workspace_name}",
        message=(
            f"You have been invited to join {workspace_name} on CampaignFlow.\n\n"
            f"Accept your invitation:\n{invitation_url}\n\n"
            "This invitation expires in 7 days."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
