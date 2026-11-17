from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/auth/",  include("campaignflow.authentication.urls"),),
    path("api/", include("campaignflow.campaigns.urls")),
    path("api/", include("campaignflow.approvals.urls")),
    path("api/", include("campaignflow.optimizer.urls")),
]
