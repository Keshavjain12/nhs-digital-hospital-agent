"""Shared schema base.

The API contract (docs/api/api-contract-v1.md) uses camelCase on the wire, because the
frontend consumes it directly and TypeScript convention is camelCase. Python code stays
snake_case. Rather than spelling camelCase field names in Python — which fights PEP 8 and
every linter — the translation happens once, here, via an alias generator.

Every request and response schema in the application inherits from one of these.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base for all wire schemas: snake_case in Python, camelCase in JSON."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,  # accept either spelling on input; be liberal in what we accept
        from_attributes=True,  # allows constructing directly from ORM objects
    )


class ResponseMeta(CamelModel):
    """The `meta` block carried by every successful response.

    `data_origin` is not optional decoration. It is how the frontend knows to render the
    synthetic-data notice, and it is the mechanism that makes "never present synthetic
    data as real" (brief §7) structural rather than a matter of discipline.
    """

    request_id: str | None = None
    data_origin: str | None = None


class PageMeta(ResponseMeta):
    page: int
    page_size: int
    total_items: int
    total_pages: int
