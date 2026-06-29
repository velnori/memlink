"""memlink — AI Memory Interchange Layer."""

__version__ = "0.6.0"

from .converter import ConversionAnalysis, FeatureImpact, analyze_conversion, compare_memories
from .models import JSONValue, Memory, Relationship, Source
from .plugin import Capabilities, FormatPlugin, ReadResult, Severity, ValidationIssue
from .registry import get_reader, get_writer, list_formats
from .testing import (
    test_plugin_contract,
    test_reader_deterministic,
    test_reader_invalid_input,
    test_reader_minimal,
    test_reader_unknown_fields,
    test_roundtrip_preserves_identity,
    test_writer_produces_output,
)

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
    "test_plugin_contract",
    "test_reader_deterministic",
    "test_reader_invalid_input",
    "test_reader_minimal",
    "test_reader_unknown_fields",
    "test_roundtrip_preserves_identity",
    "test_writer_produces_output",
]
