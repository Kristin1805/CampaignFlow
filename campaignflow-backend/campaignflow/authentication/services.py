
from django.contrib.auth import authenticate, login, logout
from django.db import transaction

from .models import User


@transaction.atomic
def user_create(*, email: str, nickname: str, first_name: str, last_name: str, password: str,) -> User:

    user = User.objects.create_user(
        email=email.strip().lower(),
        nickname=nickname.strip(),
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        password=password,
    )

    return user


def user_login(*, request, email: str, password: str) -> User | None:
    user = authenticate(request, username=email.strip().lower(), password=password,)

    if user is not None:
        login(request, user)

    return user


def user_logout(*, request) -> None:
    logout(request)
