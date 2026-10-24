
from django.urls import path

from .apis import (
    CsrfTokenApi,
    RegisterApi,
    LoginApi,
    LogoutApi,
    CurrentUserApi,
)

urlpatterns = [
    path("csrf/", CsrfTokenApi.as_view(), name="auth-csrf"),
    path("register/", RegisterApi.as_view(), name="auth-register"),
    path("login/", LoginApi.as_view(), name="auth-login"),
    path("logout/", LogoutApi.as_view(), name="auth-logout"),
    path("check/", CurrentUserApi.as_view(), name="auth-check"),
]
