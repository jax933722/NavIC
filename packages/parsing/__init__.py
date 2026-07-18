"""parsing — raw bytes -> structured ParsedDocument (spec 03 §3 / blueprint §14)."""

from .html import parse_html
from .models import ParsedDocument, ParsedLink

__all__ = ["ParsedDocument", "ParsedLink", "parse_html"]
