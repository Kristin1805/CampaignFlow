from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from .authentication import CampaignFlowSessionAuthentication


class PublicApi(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class PrivateApi(APIView):
    authentication_classes = [CampaignFlowSessionAuthentication]
    permission_classes = [IsAuthenticated]