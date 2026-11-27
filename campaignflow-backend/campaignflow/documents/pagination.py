from rest_framework.pagination import PageNumberPagination

from campaignflow.documents.constants import (
    DOCUMENT_TEMPLATE_PAGE_SIZE,
    DOCUMENT_TEMPLATE_MAX_PAGE_SIZE,
)


class DocumentTemplatePagination(PageNumberPagination):
    page_size = DOCUMENT_TEMPLATE_PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = DOCUMENT_TEMPLATE_MAX_PAGE_SIZE

from rest_framework.pagination import PageNumberPagination


class DocumentPagination(PageNumberPagination):

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100