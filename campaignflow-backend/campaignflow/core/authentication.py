from rest_framework.authentication import SessionAuthentication


class CampaignFlowSessionAuthentication(SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"