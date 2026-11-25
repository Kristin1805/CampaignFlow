from rest_framework.exceptions import APIException


class PostingPlanConflict(APIException):
    status_code = 409
    default_detail = "The content item has been modified by another user."
    default_code = "posting_plan_conflict"

    def __init__(self, *, content_id, updated_at):
        super().__init__({
            "code": self.default_code,
            "message": self.default_detail,
            "content_id": str(content_id),
            "updated_at": updated_at.isoformat(),
        })