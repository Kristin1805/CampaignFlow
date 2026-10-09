
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class User(AbstractUser):
    username = None

    email = models.EmailField(unique=True)
    nickname = models.CharField(max_length=50, unique=True)

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nickname", "first_name", "last_name"]

    objects = UserManager()

    def __str__(self):
        return self.email

