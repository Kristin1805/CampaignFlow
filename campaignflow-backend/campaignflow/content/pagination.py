from rest_framework.pagination import PageNumberPagination

from campaignflow.content.constants import POSTING_PLAN_MAX_PAGE_SIZE, POSTING_PLAN_PAGE_SIZE


class ContentPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class PostingPlanPagination(PageNumberPagination):
    page_size = POSTING_PLAN_PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = POSTING_PLAN_MAX_PAGE_SIZE