from __future__ import annotations

import logging
from typing import Final


LOG_EMPTY_VALUE: Final[str] = "-"
LOG_CONTEXT_FIELDS: Final[tuple[str, ...]] = (
    "operation",
    "user_id",
    "email",
    "program_id",
    "exercise_id",
    "status_code",
)


class ContextDefaultsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for field_name in LOG_CONTEXT_FIELDS:
            if not hasattr(record, field_name):
                setattr(record, field_name, LOG_EMPTY_VALUE)

        return True


def serialize_log_value(value: object | None) -> str:
    if value is None:
        return LOG_EMPTY_VALUE

    string_value = str(value).strip()

    if string_value == "":
        return LOG_EMPTY_VALUE

    return string_value


def build_log_extra(
    operation: str,
    user_id: object | None,
    email: object | None,
    program_id: object | None,
    exercise_id: object | None,
    status_code: object | None,
) -> dict[str, str]:
    return {
        "operation": serialize_log_value(operation),
        "user_id": serialize_log_value(user_id),
        "email": serialize_log_value(email),
        "program_id": serialize_log_value(program_id),
        "exercise_id": serialize_log_value(exercise_id),
        "status_code": serialize_log_value(status_code),
    }
