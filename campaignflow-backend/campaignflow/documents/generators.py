from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError

from campaignflow.documents.constants import SECTION_FIELD_TYPES
from campaignflow.documents.enums import DocumentSectionType, DocumentFieldType
from campaignflow.documents.resolvers import DocumentPlaceholderResolver
from campaignflow.documents.validators import (
    DocumentTemplateValidator,
    validate_document_content,
)


class DocumentGenerator:

    def __init__(self, *, campaign, populate_placeholders=True):
        self.resolver = DocumentPlaceholderResolver(campaign=campaign)
        self.populate_placeholders = populate_placeholders

        self.resolved_placeholders = set()
        self.unresolved_placeholders = set()
        self.empty_fields = []
        self.warnings = []

    @staticmethod
    def is_empty(value):
        return value is None or value == "" or value == [] or value == {}

    @staticmethod
    def get_empty_value(field_type):
        if field_type in {
            DocumentFieldType.TEXT,
            DocumentFieldType.LONG_TEXT,
        }:
            return ""

        if field_type == DocumentFieldType.BOOLEAN:
            return False

        return None

    def resolve_placeholder(self, *, key):
        if not self.populate_placeholders:
            return None

        value = self.resolver.resolve(key=key)

        if self.is_empty(value):
            self.unresolved_placeholders.add(key)
            return None

        self.resolved_placeholders.add(key)

        return deepcopy(value)

    def validate_generated_value(self, *, value, definition, path):
        try:
            DocumentTemplateValidator.validate_default(
                value,
                definition["type"],
                path,
                definition.get("options"),
            )
            return True

        except DjangoValidationError:
            self.warnings.append({
                "path": path,
                "message": "Source value is incompatible with the field type.",
            })
            return False

    def generate_field(self, *, definition, path, source=None):
        field_type = definition["type"]
        value = deepcopy(
            definition.get("default", self.get_empty_value(field_type)),
        )

        candidate = None
        placeholder = definition.get("placeholder")

        if placeholder and self.populate_placeholders:
            candidate = self.resolve_placeholder(key=placeholder)

        elif source is not None:
            candidate = source.get(definition["id"])

        if not self.is_empty(candidate):
            if self.validate_generated_value(
                value=candidate, definition=definition, path=path,
            ):
                value = deepcopy(candidate)

        if self.is_empty(value):
            self.empty_fields.append({
                "path": path,
                "required": definition.get("required", False),
            })

        return value

    def generate_table(self, *, section):
        placeholder = section.get("placeholder")
        sources = []

        if placeholder and self.populate_placeholders:
            sources = self.resolve_placeholder(key=placeholder) or []

        if not isinstance(sources, list):
            raise ValidationError({
                "content": "Table placeholder must resolve to a collection.",
            })

        rows = []

        for index, source in enumerate(sources):
            row_id = str(uuid5(
                NAMESPACE_URL,
                f"campaignflow:{section['id']}:{source.get('id', index)}:{index}",
            ))

            cells = {}

            for column in section["columns"]:
                path = (
                    f"{section['id']}.rows.{row_id}.{column['id']}"
                )

                cells[column["id"]] = self.generate_field(
                    definition=column,
                    path=path,
                    source=source,
                )

            rows.append({
                "id": row_id,
                "cells": cells,
            })

        if not rows:
            self.empty_fields.append({
                "path": section["id"],
                "required": section.get("required", False),
            })

        return rows

    def generate_section(self, *, section):
        section_id = section["id"]
        section_type = section["type"]

        if section_type == DocumentSectionType.TABLE:
            return self.generate_table(section=section)

        if section_type == DocumentSectionType.KEY_VALUE:
            return {
                field["id"]: self.generate_field(
                    definition=field,
                    path=f"{section_id}.{field['id']}",
                )
                for field in section["fields"]
            }

        if section_type == DocumentSectionType.CHECKLIST:
            return {
                item: False for item in section["items"]
            }

        if section_type == DocumentSectionType.SELECT:
            return self.generate_field(
                definition={
                    **section,
                    "type": DocumentFieldType.CHOICE,
                },
                path=section_id,
            )

        if section_type == DocumentSectionType.MULTI_SELECT:
            value = deepcopy(section.get("default", []))

            if not value:
                self.empty_fields.append({
                    "path": section_id,
                    "required": section.get("required", False),
                })

            return value

        if section_type == DocumentSectionType.HEADING:
            return None

        if section_type in SECTION_FIELD_TYPES:
            return self.generate_field(
                definition={
                    **section,
                    "type": SECTION_FIELD_TYPES[section_type],
                },
                path=section_id,
            )

        raise ValidationError({
            "structure": f"Unsupported section type: {section_type}",
        })

    def generate(self, *, structure):
        self.resolved_placeholders.clear()
        self.unresolved_placeholders.clear()
        self.empty_fields.clear()
        self.warnings.clear()

        snapshot = deepcopy(structure)

        try:
            DocumentTemplateValidator.validate(snapshot)

            content = {
                "schema_version": snapshot["schema_version"],
                "sections": {
                    section["id"]: self.generate_section(section=section)
                    for section in snapshot["sections"]
                },
            }

            validate_document_content(
                structure=snapshot,
                content=content,
            )

        except DjangoValidationError as exc:
            raise ValidationError({"content": exc.messages})

        return {
            "structure_snapshot": snapshot,
            "content": content,
            "resolved_placeholders": sorted(self.resolved_placeholders),
            "unresolved_placeholders": sorted(self.unresolved_placeholders),
            "empty_fields": deepcopy(self.empty_fields),
            "warnings": deepcopy(self.warnings),
        }