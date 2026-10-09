
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .selectors import UserSelector
from .services import user_create, user_login, user_logout


class RegisterApi(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    class InputSerializer(serializers.Serializer):
        email = serializers.EmailField()
        nickname = serializers.CharField(max_length=50)
        first_name = serializers.CharField(max_length=150)
        last_name = serializers.CharField(max_length=150)
        password = serializers.CharField(write_only=True)

        def validate_email(self, value):
            value = value.strip().lower()
            if User.objects.filter(email=value).exists():
                raise serializers.ValidationError("Email already registered.")
            return value

        def validate_nickname(self, value):
            if User.objects.filter(nickname=value).exists():
                raise serializers.ValidationError("Nickname already taken.")
            return value

        def validate_password(self, value):
            try:
                validate_password(value)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.messages)
            return value

    def post(self, request):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = user_create(**serializer.validated_data)
        except IntegrityError:
            return Response({"detail": "Email or nickname already exists."},status=status.HTTP_400_BAD_REQUEST,)

        return Response(UserSelector.get_user_data(user), status=status.HTTP_201_CREATED,  )


class LoginApi(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    class InputSerializer(serializers.Serializer):
        email = serializers.EmailField()
        password = serializers.CharField()

    def post(self, request):
        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = user_login(
            request=request,
            **serializer.validated_data,
        )

        if user is None:
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(UserSelector.get_user_data(user))


class LogoutApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_logout(request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSelector.get_user_data(request.user))
