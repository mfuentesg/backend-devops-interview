import json
import logging
import sys

from django.conf import settings

from core.json_log import JsonFormatter


def _record(**overrides):
    kwargs = dict(
        name="blog.api",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="hello %s",
        args=("world",),
        exc_info=None,
        func="do_thing",
    )
    kwargs.update(overrides)
    return logging.LogRecord(**kwargs)


def test_format_emits_valid_json_with_expected_keys():
    data = json.loads(JsonFormatter().format(_record()))
    assert data["level"] == "INFO"
    assert data["logger"] == "blog.api"
    assert data["message"] == "hello world"
    assert data["lineno"] == 42
    assert data["funcName"] == "do_thing"
    assert data["timestamp"].endswith("+00:00")
    assert "exception" not in data


def test_format_includes_exception_when_exc_info_present():
    try:
        raise ValueError("boom")
    except ValueError:
        record = _record(exc_info=sys.exc_info())
    formatted = JsonFormatter().format(record)
    assert "\n" not in formatted  # one physical line per record — the file-tail invariant
    data = json.loads(formatted)
    assert "ValueError: boom" in data["exception"]


def test_django_firehose_loggers_are_pinned_to_info():
    # Regardless of LOG_LEVEL (a dev may set LOG_LEVEL=DEBUG in their .env), the
    # firehose loggers stay at INFO — one line per SQL query / watched file /
    # unresolved template var otherwise.
    loggers = settings.LOGGING["loggers"]
    assert loggers["django.db.backends"]["level"] == "INFO"
    assert loggers["django.utils.autoreload"]["level"] == "INFO"
    assert loggers["django.template"]["level"] == "INFO"
