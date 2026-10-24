import uuid

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(
        self,
        email,
        nickname,
        first_name,
        last_name,
        password=None,
        **extra_fields,
    ):
        if not email:
            raise ValueError("Email is required.")

        if not nickname:
            raise ValueError("Nickname is required.")

        if not first_name or not last_name:
            raise ValueError("First and last name are required.")

        if not password:
            raise ValueError("Password is required.")

        user = self.model(
            email=self.normalize_email(email.strip()),
            nickname=nickname,
            first_name=first_name,
            last_name=last_name,
            **extra_fields,
        )

        user.set_password(password)
        user.full_clean()
        user.save(using=self._db)

        return user

    def create_superuser(
        self,
        email,
        nickname,
        first_name,
        last_name,
        password=None,
        **extra_fields,
    ):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields["is_staff"] is not True:
            raise ValueError("Superuser must have is_staff=True.")

        if extra_fields["is_superuser"] is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(
            email=email,
            nickname=nickname,
            first_name=first_name,
            last_name=last_name,
            password=password,
            **extra_fields,
        )


class User(AbstractUser):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    username = None

    email = models.EmailField(unique=True, )

    nickname = models.CharField(max_length=50, unique=True,)

    first_name = models.CharField(max_length=150,)

    last_name = models.CharField(max_length=150,)

    USERNAME_FIELD = "email"

    REQUIRED_FIELDS = [
        "nickname",
        "first_name",
        "last_name",
    ]

    objects = UserManager()

    def __str__(self):
        return self.email

