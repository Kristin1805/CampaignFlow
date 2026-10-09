
from django.urls import path

from .apis import (
    RegisterApi,
    LoginApi,
    LogoutApi,
    CurrentUserApi,
)

urlpatterns = [
    path("register/", RegisterApi.as_view(), name="register"),
    path("login/", LoginApi.as_view(), name="login"),
    path("logout/", LogoutApi.as_view(), name="logout"),
    path("me/", CurrentUserApi.as_view(), name="current-user"),
]
