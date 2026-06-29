"""memlink — AI Memory Interchange Layer."""

__version__ = "0.5.0"

from .converter import ConversionAnalysis, FeatureImpact, analyze_conversion, compare_memories
from .models import JSONValue, Memory, Relationship, Source
from .plugin import Capabilities, FormatPlugin, ReadResult, Severity, ValidationIssue
from .registry import get_reader, get_writer, list_formats

__all__ = [
    "__version__",
    "Memory",
    "Source",
    "Relationship",
    "JSONValue",
    "FormatPlugin",
    "Capabilities",
    "ReadResult",
    "ValidationIssue",
    "Severity",
    "ConversionAnalysis",
    "FeatureImpact",
    "analyze_conversion",
    "compare_memories",
    "get_reader",
    "get_writer",
    "list_formats",
]
