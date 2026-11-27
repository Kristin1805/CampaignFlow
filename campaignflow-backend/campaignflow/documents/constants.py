from campaignflow.documents.enums import DocumentSectionType


MAX_TEMPLATE_SECTIONS = 100
MAX_TABLE_COLUMNS = 50
MAX_SECTION_FIELDS = 50
MAX_SELECTION_OPTIONS = 100
MAX_TEMPLATE_STRUCTURE_BYTES = 512 * 1024

DOCUMENT_TEMPLATE_PAGE_SIZE = 20
DOCUMENT_TEMPLATE_MAX_PAGE_SIZE = 100

TEMPLATE_SCHEMA_VERSION = 1

TEMPLATE_ORDERING_FIELDS = (
    "name", "-name",
    "created_at", "-created_at",
    "updated_at", "-updated_at",
    "category", "-category",
)

EMPTY_TEMPLATE_STRUCTURE = {
    "schema_version": TEMPLATE_SCHEMA_VERSION,
    "sections": [],
}

SECTION_FIELD_TYPES = {
    DocumentSectionType.PLAIN_TEXT: "text",
    DocumentSectionType.RICH_TEXT: "long_text",
    DocumentSectionType.NUMBER: "number",
    DocumentSectionType.DATE: "date",
    DocumentSectionType.SELECT: "choice",
    DocumentSectionType.REFERENCE: "reference",
}