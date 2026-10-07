import re

_UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
_PATTERN = re.compile(
    r"([0-9]+)\s*/\s*(?:([0-9]+)\s*)?(second|minute|hour|day)s?",
    re.IGNORECASE,
)


def parse_limit(spec: str) -> tuple[int, int]:
    if not isinstance(spec, str):
        raise TypeError("limit must be a string such as '5/minute'")
    match = _PATTERN.fullmatch(spec.strip())
    if match is None:
        raise ValueError(
            f"invalid limit {spec!r}, expected a form like '5/minute' or '10/5 minutes'"
        )
    count = int(match[1])
    multiplier = int(match[2]) if match[2] else 1
    if count < 1 or multiplier < 1:
        raise ValueError(f"invalid limit {spec!r}, numbers must be >= 1")
    return count, multiplier * _UNITS[match[3].lower()]
