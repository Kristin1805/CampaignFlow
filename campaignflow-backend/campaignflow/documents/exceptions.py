from rest_framework.exceptions import APIException


class DocumentTemplateConflict(APIException):
    status_code = 409
    default_detail = "A document template conflict occurred."
    default_code = "document_template_conflict"