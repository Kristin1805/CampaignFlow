import json
import math
import re

from datetime import date
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils.dateparse import parse_datetime

from campaignflow.documents.constants import (
    MAX_TEMPLATE_SECTIONS,
    MAX_TABLE_COLUMNS,
    MAX_SECTION_FIELDS,
    MAX_SELECTION_OPTIONS,
    MAX_TEMPLATE_STRUCTURE_BYTES,
    TEMPLATE_SCHEMA_VERSION,
    SECTION_FIELD_TYPES,
    MAX_DOCUMENT_CONTENT_BYTES,
    MAX_DOCUMENT_TABLE_ROWS,
    MAX_DOCUMENT_TOTAL_ROWS,
)

from campaignflow.documents.enums import DocumentSectionType, DocumentFieldType
from campaignflow.documents.placeholders import DocumentPlaceholderRegistry


class DocumentTemplateValidator:
    IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,99}$")

    @staticmethod
    def fail(path, message):
        raise ValidationError(f"{path}: {message}")

    @classmethod
    def validate_identifier(cls, value, path):
        if not isinstance(value, str) or not cls.IDENTIFIER_PATTERN.fullmatch(value):
            cls.fail(path, "Invalid identifier.")

    @classmethod
    def validate_string(cls, value, path, max_length=10000, allow_blank=False):
        if not isinstance(value, str):
            cls.fail(path, "Expected a string.")

        if not allow_blank and not value.strip():
            cls.fail(path, "This field cannot be blank.")

        if len(value) > max_length:
            cls.fail(path, f"Maximum length is {max_length}.")

    @classmethod
    def validate_boolean(cls, value, path):
        if not isinstance(value, bool):
            cls.fail(path, "Expected a boolean.")

    @classmethod
    def validate_keys(cls, value, allowed_keys, path):
        if not isinstance(value, dict):
            cls.fail(path, "Expected an object.")

        unknown = set(value) - set(allowed_keys)

        if unknown:
            cls.fail(path, f"Unknown fields: {', '.join(sorted(unknown))}.")

    @classmethod
    def validate_options(cls, options, path):
        if not isinstance(options, list) or not options:
            cls.fail(path, "A non-empty list of options is required.")

        if len(options) > MAX_SELECTION_OPTIONS:
            cls.fail(path, f"Maximum {MAX_SELECTION_OPTIONS} options are allowed.")

        for index, option in enumerate(options):
            cls.validate_string(option, f"{path}[{index}]", max_length=255)

        if len(options) != len(set(options)):
            cls.fail(path, "Duplicate options are not allowed.")

    @classmethod
    def validate_default(cls, value, field_type, path, options=None):
        if value is None:
            return

        if field_type in {DocumentFieldType.TEXT, DocumentFieldType.LONG_TEXT}:
            cls.validate_string(value, path, allow_blank=True)

        elif field_type in {
            DocumentFieldType.NUMBER,
            DocumentFieldType.DECIMAL,
            DocumentFieldType.CURRENCY,
            DocumentFieldType.PERCENTAGE,
        }:
            if type(value) not in {int, float}:
                cls.fail(path, "Expected a numeric value.")

            if isinstance(value, float) and not math.isfinite(value):
                cls.fail(path, "Numeric value must be finite.")

            if field_type == DocumentFieldType.PERCENTAGE and not 0 <= value <= 100:
                cls.fail(path, "Percentage must be between 0 and 100.")

        elif field_type == DocumentFieldType.BOOLEAN:
            cls.validate_boolean(value, path)

        elif field_type == DocumentFieldType.DATE:
            try:
                if not isinstance(value, str):
                    raise ValueError

                parsed = date.fromisoformat(value)

                if parsed.isoformat() != value:
                    raise ValueError

            except (TypeError, ValueError):
                cls.fail(path, "Expected an ISO date in YYYY-MM-DD format.")

        elif field_type == DocumentFieldType.DATETIME:
            try:
                parsed = parse_datetime(value) if isinstance(value, str) else None
            except (ValueError, TypeError):
                parsed = None

            if parsed is None or parsed.utcoffset() is None:
                cls.fail(path, "Expected a timezone-aware ISO datetime.")

        elif field_type == DocumentFieldType.URL:
            try:
                URLValidator(schemes=["http", "https"])(value)
            except (ValidationError, TypeError):
                cls.fail(path, "Expected a valid HTTP or HTTPS URL.")

        elif field_type == DocumentFieldType.CHOICE:
            if value not in (options or []):
                cls.fail(path, "Default value must be one of the available options.")

        elif field_type == DocumentFieldType.REFERENCE:
            try:
                UUID(value)
            except (ValueError, TypeError, AttributeError):
                cls.fail(path, "Expected a UUID.")

    @classmethod
    def validate_placeholder(cls, placeholder, path, expected_type):
        if not isinstance(placeholder, str):
            cls.fail(path, "Placeholder must be a string.")

        definition = DocumentPlaceholderRegistry.get(key=placeholder)

        if definition is None:
            cls.fail(path, "Unsupported placeholder.")

        actual_type = definition["data_type"]

        compatible_types = {
            "text": {"text"},
            "long_text": {"text", "long_text"},
            "date": {"date"},
            "collection": {"collection"},
        }

        if actual_type not in compatible_types.get(expected_type, {expected_type}):
            cls.fail(path, "Placeholder is incompatible with the field type.")

    @classmethod
    def validate_field(cls, field, path):
        cls.validate_keys(field, {
            "id", "label", "type", "required", "editable",
            "default", "options", "placeholder", "description",
        }, path)

        cls.validate_identifier(field.get("id"), f"{path}.id")
        cls.validate_string(field.get("label"), f"{path}.label", max_length=255)

        field_type = field.get("type")

        if field_type not in DocumentFieldType.values:
            cls.fail(f"{path}.type", "Unsupported field type.")

        for key in ("required", "editable"):
            if key in field:
                cls.validate_boolean(field[key], f"{path}.{key}")

        if "description" in field:
            cls.validate_string(field["description"], f"{path}.description", allow_blank=True)

        if field_type == DocumentFieldType.CHOICE:
            cls.validate_options(field.get("options"), f"{path}.options")

        elif "options" in field:
            cls.fail(f"{path}.options", "Options are only supported for choice fields.")

        if "placeholder" in field:
            cls.validate_placeholder(field["placeholder"], f"{path}.placeholder", field_type)

        if "default" in field:
            cls.validate_default(
                field["default"], field_type,
                f"{path}.default", field.get("options"),
            )

    @classmethod
    def validate_fields(cls, fields, path, max_items):
        if not isinstance(fields, list) or not fields:
            cls.fail(path, "A non-empty list of fields is required.")

        if len(fields) > max_items:
            cls.fail(path, f"Maximum {max_items} fields are allowed.")

        identifiers = set()

        for index, field in enumerate(fields):
            field_path = f"{path}[{index}]"
            cls.validate_field(field, field_path)

            if field["id"] in identifiers:
                cls.fail(field_path, "Duplicate field identifier.")

            identifiers.add(field["id"])

    @classmethod
    def validate_section(cls, section, path):
        common_keys = {
            "id", "title", "type", "description", "instructions",
            "required", "default", "placeholder",
            "columns", "fields", "options", "items",
        }

        cls.validate_keys(section, common_keys, path)

        cls.validate_identifier(section.get("id"), f"{path}.id")
        cls.validate_string(section.get("title"), f"{path}.title", max_length=255)

        section_type = section.get("type")

        if section_type not in DocumentSectionType.values:
            cls.fail(f"{path}.type", "Unsupported section type.")

        for key in ("description", "instructions"):
            if key in section:
                cls.validate_string(section[key], f"{path}.{key}", allow_blank=True)

        if "required" in section:
            cls.validate_boolean(section["required"], f"{path}.required")

        configuration_fields = {
            DocumentSectionType.TABLE: {"columns", "placeholder"},
            DocumentSectionType.KEY_VALUE: {"fields"},
            DocumentSectionType.CHECKLIST: {"items"},
            DocumentSectionType.SELECT: {"options", "default"},
            DocumentSectionType.MULTI_SELECT: {"options", "default"},
            DocumentSectionType.HEADING: set(),
        }

        allowed_configuration = configuration_fields.get(
            section_type, {"default", "placeholder"},
        )

        provided_configuration = set(section) & {
            "columns", "fields", "options", "items", "default", "placeholder",
        }

        if provided_configuration - allowed_configuration:
            cls.fail(path, "Invalid configuration for this section type.")

        if section_type == DocumentSectionType.TABLE:
            cls.validate_fields(
                section.get("columns"), f"{path}.columns", MAX_TABLE_COLUMNS,
            )

            if "placeholder" in section:
                cls.validate_placeholder(
                    section["placeholder"], f"{path}.placeholder", "collection",
                )

        elif section_type == DocumentSectionType.KEY_VALUE:
            cls.validate_fields(
                section.get("fields"), f"{path}.fields", MAX_SECTION_FIELDS,
            )

        elif section_type == DocumentSectionType.CHECKLIST:
            cls.validate_options(section.get("items"), f"{path}.items")

        elif section_type in {
            DocumentSectionType.SELECT,
            DocumentSectionType.MULTI_SELECT,
        }:
            cls.validate_options(section.get("options"), f"{path}.options")

            if section_type == DocumentSectionType.MULTI_SELECT:
                default = section.get("default", [])

                if not isinstance(default, list):
                    cls.fail(f"{path}.default", "Expected a list.")

                if any(value not in section["options"] for value in default):
                    cls.fail(f"{path}.default", "Invalid selected option.")

                if len(default) != len(set(default)):
                    cls.fail(f"{path}.default", "Duplicate selections.")

            else:
                cls.validate_default(
                    section.get("default"), DocumentFieldType.CHOICE,
                    f"{path}.default", section["options"],
                )

        elif section_type in SECTION_FIELD_TYPES:
            field_type = SECTION_FIELD_TYPES[section_type]

            if "default" in section:
                cls.validate_default(
                    section["default"], field_type, f"{path}.default",
                )

            if "placeholder" in section:
                cls.validate_placeholder(
                    section["placeholder"], f"{path}.placeholder", field_type,
                )

    @classmethod
    def validate(cls, structure, require_sections=False):
        try:
            encoded = json.dumps(structure, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, UnicodeError, RecursionError):
            cls.fail("structure", "Invalid JSON structure.")

        if len(encoded) > MAX_TEMPLATE_STRUCTURE_BYTES:
            cls.fail("structure", "Template structure exceeds the maximum allowed size.")

        cls.validate_keys(structure, {"schema_version", "sections"}, "structure")

        if type(structure.get("schema_version")) is not int or structure["schema_version"] != TEMPLATE_SCHEMA_VERSION:
            cls.fail("structure.schema_version", "Unsupported schema version.")

        sections = structure.get("sections")

        if not isinstance(sections, list):
            cls.fail("structure.sections", "Expected a list of sections.")

        if require_sections and not sections:
            cls.fail("structure.sections", "At least one section is required for publication.")

        if len(sections) > MAX_TEMPLATE_SECTIONS:
            cls.fail("structure.sections", f"Maximum {MAX_TEMPLATE_SECTIONS} sections are allowed.")

        identifiers = set()

        for index, section in enumerate(sections):
            path = f"structure.sections[{index}]"
            cls.validate_section(section, path)

            if section["id"] in identifiers:
                cls.fail(path, "Duplicate section identifier.")

            identifiers.add(section["id"])

        return structure


def validate_template_structure(value):
    DocumentTemplateValidator.validate(value)


def validate_document_period(*, period_start, period_end):
    if bool(period_start) != bool(period_end):
        raise ValidationError("Both reporting period dates are required.")

    if period_start and period_end and period_start > period_end:
        raise ValidationError("End date cannot be before start date.")


def validate_document_content(*, structure, content):
    validator = DocumentTemplateValidator

    validator.validate(structure)

    try:
        encoded = json.dumps(
            content, ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ValidationError("Document content must contain valid JSON.")

    if len(encoded) > MAX_DOCUMENT_CONTENT_BYTES:
        raise ValidationError("Document content exceeds the maximum allowed size.")

    validator.validate_keys(
        content, {"schema_version", "sections"}, "content",
    )

    if content.get("schema_version") != structure["schema_version"]:
        raise ValidationError("Document schema version does not match its structure.")

    sections = content.get("sections")

    if not isinstance(sections, dict):
        raise ValidationError("Document sections must be an object.")

    definitions = {
        section["id"]: section for section in structure["sections"]
    }

    if set(sections) != set(definitions):
        raise ValidationError("Document sections do not match the template structure.")

    total_rows = 0

    for section_id, definition in definitions.items():
        value = sections[section_id]
        section_type = definition["type"]
        path = f"content.sections.{section_id}"

        if section_type == DocumentSectionType.TABLE:
            if not isinstance(value, list):
                validator.fail(path, "Expected a list of table rows.")

            if len(value) > MAX_DOCUMENT_TABLE_ROWS:
                validator.fail(path, "Table row limit exceeded.")

            total_rows += len(value)

            columns = {
                column["id"]: column for column in definition["columns"]
            }

            row_ids = set()

            for index, row in enumerate(value):
                row_path = f"{path}[{index}]"

                validator.validate_keys(row, {"id", "cells"}, row_path)
                validator.validate_default(
                    row.get("id"), DocumentFieldType.REFERENCE,
                    f"{row_path}.id",
                )

                row_id = row.get("id")

                if not row_id or row_id in row_ids:
                    validator.fail(row_path, "Invalid or duplicate row identifier.")

                row_ids.add(row_id)

                cells = row.get("cells")

                if not isinstance(cells, dict) or set(cells) != set(columns):
                    validator.fail(row_path, "Invalid table cells.")

                for column_id, column in columns.items():
                    validator.validate_default(
                        cells[column_id],
                        column["type"],
                        f"{row_path}.cells.{column_id}",
                        column.get("options"),
                    )

        elif section_type == DocumentSectionType.KEY_VALUE:
            fields = {
                field["id"]: field for field in definition["fields"]
            }

            if not isinstance(value, dict) or set(value) != set(fields):
                validator.fail(path, "Invalid section fields.")

            for field_id, field in fields.items():
                validator.validate_default(
                    value[field_id], field["type"],
                    f"{path}.{field_id}", field.get("options"),
                )

        elif section_type == DocumentSectionType.CHECKLIST:
            if not isinstance(value, dict):
                validator.fail(path, "Expected a checklist object.")

            if set(value) != set(definition["items"]):
                validator.fail(path, "Checklist items do not match the structure.")

            for item, checked in value.items():
                validator.validate_boolean(checked, f"{path}.{item}")

        elif section_type == DocumentSectionType.SELECT:
            validator.validate_default(
                value, DocumentFieldType.CHOICE,
                path, definition["options"],
            )

        elif section_type == DocumentSectionType.MULTI_SELECT:
            if not isinstance(value, list):
                validator.fail(path, "Expected a list of selected options.")

            if any(
                not isinstance(item, str) or item not in definition["options"]
                for item in value
            ):
                validator.fail(path, "Invalid selected option.")

            if len(value) != len(set(value)):
                validator.fail(path, "Duplicate selected options.")

        elif section_type == DocumentSectionType.HEADING:
            if value is not None:
                validator.fail(path, "Heading sections cannot contain values.")

        elif section_type in SECTION_FIELD_TYPES:
            validator.validate_default(
                value, SECTION_FIELD_TYPES[section_type], path,
            )

        else:
            validator.fail(path, "Unsupported document section type.")

    if total_rows > MAX_DOCUMENT_TOTAL_ROWS:
        raise ValidationError("Document table row limit exceeded.")