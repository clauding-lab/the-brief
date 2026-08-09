"""Regression tests for the issue-183 truncation failure (2026-08-02).

The editor's payload sits at the model's HARD per-response ceiling (64k output
tokens on claude-opus-4-8 — probing 128k comes back 64k). When a draft crosses
it the model is cut off mid-JSON and continues in a NEW assistant message.
`--output-format json` reports only the FINAL message in `result`, so the
pipeline received the tail of the brief and rejected it as a schema violation —
twice on 2026-08-02 (issue #183) after three times on 2026-07-31 (issue #181).

The fix reads `--output-format stream-json` and stitches every assistant text
block back together, which reconstructs the payload byte-for-byte. These tests
pin that behaviour, plus the two traps the first attempt fell into:

  * the cut-off alarm must NOT be gated on "parsing failed" — the preamble
    fallback happily salvages a section fragment, so parsing appears to succeed;
  * the cut-off alarm must NOT be gated on `num_turns` — a cut-off-and-continued
    response is still ONE turn.

Event shapes here mirror a real captured CLI stream (forced truncation probe,
2026-08-02).
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from brief.claude.max_client import _parse_cli_stdout, run_max


def _fake_completed(stdout: str, returncode: int = 0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    m.stderr = ""
    return m


def _assistant(text: str, msg_id: str) -> dict:
    return {
        "type": "assistant",
        "message": {"id": msg_id, "content": [{"type": "text", "text": text}]},
    }


def _thinking(msg_id: str) -> dict:
    return {
        "type": "assistant",
        "message": {
            "id": msg_id,
            "content": [{"type": "thinking", "thinking": "pondering the brief"}],
        },
    }


def _result(result_text: str, **extra) -> dict:
    event = {
        "type": "result",
        "subtype": "success",
        "result": result_text,
        "usage": {"input_tokens": 10, "output_tokens": 3456},
        "total_cost_usd": 0.5,
        "num_turns": 1,
    }
    event.update(extra)
    return event


def _stream(*events: dict) -> str:
    return "\n".join(json.dumps(e) for e in events) + "\n"


# --- the core fix ---------------------------------------------------------


class TestStitchesCutOffResponse:
    def test_three_message_response_is_stitched_back_into_one_payload(self):
        # Arrange — the brief, cut at two arbitrary points mid-token.
        head = '{"brief":{"issue_no":183},"sections":[{"slug":"tbo'
        mid = 'nd","ord":1},{"slug":"fisc'
        tail = 'al","ord":8}]}'
        stdout = _stream(
            _assistant(head, "msg_1"),
            _thinking("msg_2"),
            _assistant(mid, "msg_3"),
            _assistant(tail, "msg_4"),
            _result(tail),  # `result` holds ONLY the final message — the bug
        )
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)):
            r = run_max(prompt="write the brief")
        # Assert — the whole brief, not the tail
        assert r.parsed == {
            "brief": {"issue_no": 183},
            "sections": [{"slug": "tbond", "ord": 1}, {"slug": "fiscal", "ord": 8}],
        }
        assert r.assistant_messages == 3
        assert r.raw_text == head + mid + tail

    def test_single_message_response_is_unchanged(self):
        # Arrange — the happy path must not regress.
        stdout = _stream(
            _assistant('{"brief":{"issue_no":182}}', "msg_1"),
            _result('{"brief":{"issue_no":182}}'),
        )
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)):
            r = run_max(prompt="hi")
        # Assert
        assert r.parsed == {"brief": {"issue_no": 182}}
        assert r.assistant_messages == 1

    def test_issue_183_tail_fragment_no_longer_wins(self):
        # Arrange — the EXACT production failure: the tail begins mid-string and
        # its first complete {...} is a lone section object, which the preamble
        # fallback used to extract and hand to Pydantic as if it were the brief.
        head = '{"brief":{"issue_no":183},"sections":[{"slug":"remit","ord":11,"t'
        tail = 'itle":"Remittance"}]}'
        stdout = _stream(
            _assistant(head, "msg_1"),
            _assistant(tail, "msg_2"),
            _result(tail),
        )
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)):
            r = run_max(prompt="write the brief")
        # Assert — top-level keys are the brief's, not a section's
        assert set(r.parsed) == {"brief", "sections"}
        assert r.parsed["sections"][0]["title"] == "Remittance"

    def test_duplicate_assistant_event_is_not_double_stitched(self):
        # Arrange — a re-emitted event must not duplicate its chunk.
        stdout = _stream(
            _assistant('{"a":', "msg_1"),
            _assistant('{"a":', "msg_1"),
            _assistant('1}', "msg_2"),
            _result('1}'),
        )
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)):
            r = run_max(prompt="hi")
        # Assert
        assert r.parsed == {"a": 1}
        assert r.assistant_messages == 2

    def test_thinking_blocks_are_never_stitched_into_the_payload(self):
        # Arrange
        stdout = _stream(
            _thinking("msg_0"),
            _assistant('{"a":1}', "msg_1"),
            _result('{"a":1}'),
        )
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)):
            r = run_max(prompt="hi")
        # Assert
        assert r.raw_text == '{"a":1}'
        assert r.parsed == {"a": 1}

    def test_non_json_noise_lines_are_ignored(self):
        # Arrange — the CLI occasionally prints non-protocol lines on stdout.
        stdout = (
            "warming up\n"
            + _stream(_assistant('{"a":1}', "msg_1"), _result('{"a":1}'))
            + "\n\n"
        )
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)):
            r = run_max(prompt="hi")
        # Assert
        assert r.parsed == {"a": 1}

    def test_usage_and_cost_come_from_the_result_event(self):
        # Arrange
        stdout = _stream(
            _assistant('{"a":1}', "msg_1"),
            _result('{"a":1}', num_turns=2),
        )
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)):
            r = run_max(prompt="hi")
        # Assert
        assert r.tokens == {"input": 10, "output": 3456}
        assert r.total_cost_usd == pytest.approx(0.5)
        assert r.num_turns == 2


# --- thinking and text share ONE message id -------------------------------


class TestThinkingAndTextShareOneMessageId:
    """Regression tests for issue 192 (2026-08-09).

    The stitching above assumed a `thinking` block arrives as its OWN message.
    It does not. With `--effort xhigh` (the editor's pin) the CLI splits ONE
    assistant message into TWO stream events that carry the SAME `message.id`:
    the thinking block first, the answer text second. De-duplicating by
    `message.id` therefore kept the thinking-only event and discarded the event
    holding the brief, leaving zero captured text — so `_parse_cli_stdout` fell
    back to the result field, which is the pre-fix `--output-format json`
    behaviour it exists to replace.

    Consequence in production: every editor call silently ran on the FINAL
    message only. Invisible until the payload was cut off, then the pipeline got
    the tail and rejected a fragment (2026-08-08 issue 190, 2026-08-09 issue
    192). Shape verified against a live `--effort xhigh` probe: two events,
    both `msg_011CdrRxd9KybSrDcRoVj6zx`, blocks `thinking` then `text`.
    """

    def test_text_survives_a_thinking_event_with_the_same_message_id(self):
        # Arrange — one message, split across two events, thinking first.
        stdout = _stream(
            _thinking("msg_1"),
            _assistant('{"a":1}', "msg_1"),
            _result('{"a":1}'),
        )
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)):
            r = run_max(prompt="hi")
        # Assert
        assert r.raw_text == '{"a":1}'
        assert r.parsed == {"a": 1}
        assert r.assistant_messages == 1

    def test_cut_off_payload_is_stitched_when_each_chunk_trails_its_thinking(self):
        # Arrange — the production failure: a cut-off brief where BOTH chunks
        # are preceded by a thinking event sharing their message id.
        head = '{"brief":{"issue_no":192},"sections":[{"slug":"remit","ord":11,"t'
        tail = 'itle":"Remittance"}]}'
        stdout = _stream(
            _thinking("msg_1"),
            _assistant(head, "msg_1"),
            _thinking("msg_2"),
            _assistant(tail, "msg_2"),
            _result(tail),  # the tail alone — what the pipeline used to receive
        )
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)):
            r = run_max(prompt="write the brief")
        # Assert — the whole brief, not the fragment Pydantic rejected
        assert r.raw_text == head + tail
        assert set(r.parsed) == {"brief", "sections"}
        assert r.assistant_messages == 2

    def test_alarm_fires_when_a_thinking_paired_response_is_cut_off(self, caplog):
        # Arrange — the alarm counts text-bearing events, so thinking events
        # must neither suppress it nor be counted as messages themselves.
        stdout = _stream(
            _thinking("msg_1"),
            _assistant('{"a":', "msg_1"),
            _thinking("msg_2"),
            _assistant('1}', "msg_2"),
            _result('1}'),
        )
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)):
            with caplog.at_level("WARNING"):
                run_max(prompt="hi")
        # Assert
        assert "CUT OFF" in caplog.text

    def test_a_thinking_event_alone_does_not_raise_the_alarm(self, caplog):
        # Arrange — one complete message that happens to think first is NOT a
        # cut-off response; counting the thinking event would cry wolf daily.
        stdout = _stream(
            _thinking("msg_1"),
            _assistant('{"a":1}', "msg_1"),
            _result('{"a":1}'),
        )
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)):
            with caplog.at_level("WARNING"):
                run_max(prompt="hi")
        # Assert
        assert "CUT OFF" not in caplog.text


# --- the alarm ------------------------------------------------------------


class TestCutOffAlarm:
    def test_alarm_fires_even_when_the_stitched_payload_parses(self, caplog):
        # Arrange — the issue-181 alarm was gated on "parsing failed" and so
        # stayed silent through two more production failures. Recovery is not
        # a reason for silence: the payload is at the hard ceiling.
        stdout = _stream(
            _assistant('{"a":', "msg_1"),
            _assistant('1}', "msg_2"),
            _result('1}'),
        )
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)):
            with caplog.at_level("WARNING"):
                r = run_max(prompt="hi")
        # Assert
        assert r.parsed == {"a": 1}
        assert "CUT OFF" in caplog.text

    def test_alarm_fires_when_num_turns_is_one(self, caplog):
        # Arrange — a cut-off-and-continued response is still ONE turn. The
        # issue-181 alarm keyed on num_turns > 1 and could never fire.
        stdout = _stream(
            _assistant('{"a":', "msg_1"),
            _assistant('1}', "msg_2"),
            _result('1}', num_turns=1),
        )
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)):
            with caplog.at_level("WARNING"):
                run_max(prompt="hi")
        # Assert
        assert "CUT OFF" in caplog.text

    def test_no_alarm_on_a_clean_single_message_response(self, caplog):
        # Arrange
        stdout = _stream(
            _assistant('{"a":1}', "msg_1"),
            _result('{"a":1}'),
        )
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)):
            with caplog.at_level("WARNING"):
                run_max(prompt="hi")
        # Assert
        assert "CUT OFF" not in caplog.text


# --- CLI wiring + backward compatibility ----------------------------------


class TestCliWiring:
    def test_stream_json_and_verbose_are_passed(self):
        # Arrange — --verbose is mandatory for stream-json under --print.
        stdout = _stream(_assistant('{"a":1}', "msg_1"), _result('{"a":1}'))
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)) as sp:
            run_max(prompt="hi")
        # Assert
        argv = sp.call_args.args[0]
        assert argv[argv.index("--output-format") + 1] == "stream-json"
        assert "--verbose" in argv

    def test_single_object_json_payload_still_parses(self):
        # Arrange — the older `--output-format json` shape must keep working so
        # fixtures and any non-stream caller are unaffected.
        stdout = json.dumps({
            "result": '{"a":1}',
            "usage": {"input_tokens": 1, "output_tokens": 2},
            "total_cost_usd": 0.1,
        })
        # Act
        with patch("brief.claude.max_client.subprocess.run",
                   return_value=_fake_completed(stdout)):
            r = run_max(prompt="hi")
        # Assert
        assert r.parsed == {"a": 1}
        assert r.assistant_messages == 1


class TestParseCliStdout:
    def test_result_event_without_assistant_text_falls_back_to_result_field(self):
        # Arrange — an error result carries no assistant message.
        stdout = _stream(_result("nothing was written"))
        # Act
        raw, outer, count = _parse_cli_stdout(stdout)
        # Assert
        assert raw == "nothing was written"
        assert count == 0
        assert outer["subtype"] == "success"

    def test_assistant_text_survives_a_stream_with_no_result_event(self):
        # Arrange — a stream cut short still has real content; keeping it beats
        # discarding the brief because the trailer never arrived.
        stdout = _stream(_assistant('{"a":', "m1"), _assistant('1}', "m2"))
        # Act
        raw, outer, count = _parse_cli_stdout(stdout)
        # Assert
        assert raw == '{"a":1}'
        assert count == 2
        assert outer == {}

    def test_stdout_with_no_protocol_events_is_rejected(self):
        # Arrange — not a stream and not a result object.
        from brief.claude.max_client import MaxCallError
        # Act / Assert
        with pytest.raises(MaxCallError):
            _parse_cli_stdout("total gibberish, no json at all")

    def test_assistant_messages_preserve_arrival_order(self):
        # Arrange
        stdout = _stream(
            _assistant("A", "m1"), _assistant("B", "m2"), _assistant("C", "m3"),
            _result("C"),
        )
        # Act
        raw, _outer, count = _parse_cli_stdout(stdout)
        # Assert
        assert raw == "ABC"
        assert count == 3
