from .models import User


class UserSelector:

    @staticmethod
    def get_user_data(user: User) -> dict:
        return {
            "id": str(user.id),
            "email": user.email,
            "nickname": user.nickname,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }

    @staticmethod
    def get_by_email(email: str) -> User | None:
        return User.objects.filter(email__iexact=email.strip()).first()