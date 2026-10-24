
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django_ratelimit.decorators import ratelimit

from rest_framework import serializers, status
from rest_framework.response import Response

from campaignflow.core.apis import PublicApi, PrivateApi

from .models import User
from .selectors import UserSelector
from .services import user_create, user_login, user_logout


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenApi(PublicApi):
    def get(self, request):
        response = Response({
            "csrf_token": get_token(request),
        })

        response["Cache-Control"] = "no-store"

        return response


@method_decorator(csrf_protect, name="dispatch")
class RegisterApi(PublicApi):

    class InputSerializer(serializers.Serializer):
        email = serializers.EmailField()
        nickname = serializers.CharField(max_length=50)
        first_name = serializers.CharField(max_length=150)
        last_name = serializers.CharField(max_length=150)
        password = serializers.CharField(write_only=True, trim_whitespace=False, )

        def validate_email(self, value):
            value = value.strip().lower()

            if User.objects.filter(email__iexact=value).exists():
                raise serializers.ValidationError("Email already registered.")
            return value

        def validate_nickname(self, value):
            value = value.strip()

            if User.objects.filter(nickname__iexact=value).exists():
                raise serializers.ValidationError("Nickname already taken.")

            return value

        def validate(self, attrs):
            user = User(
                email=attrs["email"],
                nickname=attrs["nickname"],
                first_name=attrs["first_name"],
                last_name=attrs["last_name"],
            )

            try:
                validate_password(attrs["password"],user=user,)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({
                    "password": exc.messages
                })

            return attrs

    def post(self, request):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = user_create(**serializer.validated_data)
        except IntegrityError:
            return Response(
                {"detail": "Email or nickname already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(UserSelector.get_user_data(user), status=status.HTTP_201_CREATED,)


@method_decorator(csrf_protect, name="dispatch")
class LoginApi(PublicApi):

    class InputSerializer(serializers.Serializer):
        email = serializers.EmailField()
        password = serializers.CharField(write_only=True, trim_whitespace=False,)

    @method_decorator(
        ratelimit(
            key="ip",
            rate="5/m",
            method="POST",
            block=False,
        )
    )
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {
                    "detail": "Too many login attempts. Please try again later."
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = user_login(
            request=request,
            **serializer.validated_data,
        )

        if user is None:
            return Response(
                {
                    "detail": "Invalid email or password."
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        response = Response(UserSelector.get_user_data(user),status=status.HTTP_200_OK,)

        response["Cache-Control"] = "no-store"

        return response


class LogoutApi(PrivateApi):
    def post(self, request):
        user_logout(request=request)

        return Response(status=status.HTTP_204_NO_CONTENT,)


class CurrentUserApi(PrivateApi):
    def get(self, request):
        response = Response(UserSelector.get_user_data(request.user), status=status.HTTP_200_OK,)

        response["Cache-Control"] = "no-store"

        return response