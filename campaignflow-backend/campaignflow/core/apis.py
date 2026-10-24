from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView


class CampaignFlowSessionAuthentication(SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"


class PublicApi(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class PrivateApi(APIView):
    authentication_classes = [CampaignFlowSessionAuthentication]
    permission_classes = [IsAuthenticated]