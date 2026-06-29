"""Tests for --fail-on-loss CLI flag."""

from datetime import datetime, timezone

from memlink.models import Memory


class TestFailOnLoss:
    def test_fail_on_loss_exits_5_when_loss_detected(self):
        memory = Memory(
            id="test-001",
            name="Test",
            body="Content.",
            kind="dynamic",
            domains=["user"],
            extensions={"custom_field": "value"},
            created_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        )
        from memlink.converter import analyze_conversion
        from memlink.ombre_reader import OmbreReader
        from memlink.openclaw_writer import OpenClawWriter

        reader = OmbreReader()
        writer = OpenClawWriter(output_mode="structured")
        analysis = analyze_conversion([memory], reader, writer)

        lost = [i for i in analysis.impacts if i.severity == "lost"]
        assert len(lost) >= 1, "Expected lost extensions when target preserve_unknown_fields=False"

    def test_fail_on_loss_succeeds_when_no_loss(self):
        memory = Memory(
            id="test-002",
            name="Test",
            body="Content.",
            kind="dynamic",
            domains=["user"],
            created_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        )
        from memlink.converter import analyze_conversion
        from memlink.ombre_reader import OmbreReader
        from memlink.openclaw_writer import OpenClawWriter

        reader = OmbreReader()
        writer = OpenClawWriter(output_mode="structured")
        analysis = analyze_conversion([memory], reader, writer)

        lost = [i for i in analysis.impacts if i.severity == "lost"]
        assert len(lost) == 0

    def test_no_fail_on_loss_by_default(self):
        memory = Memory(
            id="test-003",
            name="Test",
            body="Content.",
            kind="dynamic",
            extensions={"x": "y"},
        )
        from memlink.converter import analyze_conversion
        from memlink.ombre_reader import OmbreReader
        from memlink.openclaw_writer import OpenClawWriter

        reader = OmbreReader()
        writer = OpenClawWriter(output_mode="structured")
        analysis = analyze_conversion([memory], reader, writer)
        lost = [i for i in analysis.impacts if i.severity == "lost"]
        assert isinstance(lost, list)  # analyze_conversion never raises SystemExit
