"""The editor's raw output must survive a schema failure (issue 181, 2026-07-31).

Three consecutive publishes failed with "editor_v6 output failed schema
validation" and the raw model output was thrown away every time, so there was
nothing to diagnose from. `_dump_raw_on_failure` writes it to logs/ instead.
"""
import pathlib

from brief import pipeline_v6


class TestDumpRawOnFailure:
    def test_writes_the_stashed_raw_text_and_returns_the_path(self):
        # Arrange
        pipeline_v6._LAST_RAW["editor_v6"] = '{"sections_continued": []}'
        # Act
        path = pipeline_v6._dump_raw_on_failure("editor_v6")
        # Assert
        assert path is not None
        p = pathlib.Path(path)
        try:
            assert p.read_text() == '{"sections_continued": []}'
            assert "editor_v6_raw_" in p.name
        finally:
            p.unlink(missing_ok=True)
            pipeline_v6._LAST_RAW.pop("editor_v6", None)

    def test_returns_none_when_nothing_was_stashed(self):
        # Arrange — e.g. tests that patch _call_with_retries wholesale
        pipeline_v6._LAST_RAW.pop("editor_v6", None)
        # Act / Assert
        assert pipeline_v6._dump_raw_on_failure("editor_v6") is None

    def test_returns_none_on_empty_raw_text(self):
        # Arrange
        pipeline_v6._LAST_RAW["editor_v6"] = ""
        try:
            # Act / Assert
            assert pipeline_v6._dump_raw_on_failure("editor_v6") is None
        finally:
            pipeline_v6._LAST_RAW.pop("editor_v6", None)

    def test_write_failure_is_swallowed_not_raised(self, monkeypatch):
        # Arrange — a broken dumper must never eclipse the real publish error
        pipeline_v6._LAST_RAW["editor_v6"] = "something"

        def _boom(*a, **k):
            raise OSError("read-only file system")

        monkeypatch.setattr(pathlib.Path, "mkdir", _boom)
        try:
            # Act / Assert
            assert pipeline_v6._dump_raw_on_failure("editor_v6") is None
        finally:
            pipeline_v6._LAST_RAW.pop("editor_v6", None)
