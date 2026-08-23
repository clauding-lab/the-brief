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


class TestParseFailureAlsoDumps:
    """The gap this closes (issue 205, 2026-08-23).

    `_dump_raw_on_failure` was wired to the SCHEMA-validation failure and to
    the sub-editor's malformed-review path — but not to the JSON-PARSE failure
    inside `_call_with_retries`, which is where a truncated response actually
    lands. That morning two editor attempts died there with the full 32.5 KB
    response sitting in `_LAST_RAW`; the next attempt overwrote the stash and
    all three attempts exhausted, so the retry loop raised without ever
    reaching the schema path. Every byte was discarded. What survived was 200
    chars of `{"brief": {"issue_no": 205, ...` — the identical preamble on all
    three attempts, which cannot tell you where the JSON broke.
    """

    def _run(self, monkeypatch, raw_text):
        from brief.claude.max_client import MaxCallResult
        dumped: list[str] = []

        monkeypatch.setattr(
            pipeline_v6, "run_max",
            lambda **kw: MaxCallResult(
                raw_text=raw_text, parsed=None, usage={}, total_cost_usd=0.0,
                tokens={"input": 1000, "output": 65112, "thinking": 54700},
                assistant_messages=2,
            ),
        )
        real_dump = pipeline_v6._dump_raw_on_failure

        def spy(label):
            path = real_dump(label)
            if path:
                dumped.append(path)
            return path

        monkeypatch.setattr(pipeline_v6, "_dump_raw_on_failure", spy)
        monkeypatch.setattr(pipeline_v6.time, "sleep", lambda *_a, **_k: None)

        err = None
        try:
            pipeline_v6._call_with_retries(
                label="editor_v6", prompt_template="P", input_obj={}, attempts=2,
            )
        except pipeline_v6.V6PublishError as e:
            err = e
        return err, dumped

    def test_a_truncated_response_is_written_to_disk_before_the_retry_overwrites_it(
        self, monkeypatch
    ):
        raw = '{"brief": {"issue_no": 205, "volume": 1}, "sections": [{"slug": "bb"'
        err, dumped = self._run(monkeypatch, raw)

        try:
            assert err is not None
            # One dump per failed attempt — NOT one for the whole run, or the
            # second attempt's overwrite loses the first attempt's evidence.
            assert len(dumped) == 2, f"expected a dump per attempt, got {dumped}"
            # Distinct files: two failures inside the same second must not
            # collapse onto one path, or attempt 2 erases attempt 1's evidence.
            assert len(set(dumped)) == 2, f"dumps collided onto one path: {dumped}"
            assert all(pathlib.Path(d).read_text() == raw for d in dumped)
        finally:
            for d in dumped:
                pathlib.Path(d).unlink(missing_ok=True)

    def test_the_error_carries_the_tail_and_the_token_split(self, monkeypatch):
        """A truncation is diagnosable only from its END. The old message sliced
        the first 200 chars, which on a brief is always the same header."""
        raw = '{"brief": {"issue_no": 205}, "sections": [' + 'x' * 5000 + '"CUT_HERE'
        err, dumped = self._run(monkeypatch, raw)

        try:
            message = str(err)
            assert "CUT_HERE" in message, "the truncation point must be visible"
            assert "thinking=54700" in message, "the thinking share must be visible"
            assert "raw_len=5051" in message
        finally:
            for d in dumped:
                pathlib.Path(d).unlink(missing_ok=True)
