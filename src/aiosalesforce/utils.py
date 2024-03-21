import datetime
import string

from typing import Any, LiteralString, TypeAlias

import orjson


def json_dumps(data: str | bytes | bytearray | Any) -> bytes:
    """
    Serialize data to a JSON formatted bytes object.

    Utility function used to allow users to pass an already serialized JSON.

    Parameters
    ----------
    data : str | bytes | bytearray | Any
        Data to be serialized.

    Returns
    -------
    bytes
        JSON formatted bytes object.

    """
    if isinstance(data, str):
        return data.encode("utf-8")
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, bytes):
        return data
    return orjson.dumps(data, option=orjson.OPT_OMIT_MICROSECONDS | orjson.OPT_UTC_Z)


def json_loads(data: str | bytes | bytearray) -> Any:
    """
    Deserialize JSON formatted data.

    Parameters
    ----------
    data : str | bytes | bytearray
        JSON formatted data.

    Returns
    -------
    Any
        Deserialized data.

    """
    return orjson.loads(data)


# https://developer.salesforce.com/docs/atlas.en-us.soql_sosl.meta/soql_sosl/sforce_api_calls_soql_select_quotedstringescapes.htm
SOQL_RESERVED_CHARACTERS = {
    "\\": "\\\\",  # Backslash
    '"': '\\"',  # Double quote
    "'": "\\'",  # Single quote
}
SOQL_ESCAPE_SEQUENCES = {
    "\n": "\\n",  # Newline
    "\r": "\\r",  # Carriage return
    "\t": "\\t",  # Tab
    "\b": "\\b",  # Backspace (called 'Bell' in SOQL documentation)
    "\f": "\\f",  # Form feed
}
SOQL_ESCAPE_SEQUENCES_FOR_LIKE = {
    "_": "\\_",  # Underscore
    "%": "\\%",  # Percent
}

_ScalarSoqlParameter: TypeAlias = (
    bool | None | int | float | datetime.datetime | datetime.date | str
)
_SoqlParameter: TypeAlias = (
    _ScalarSoqlParameter
    | list[_ScalarSoqlParameter]
    | tuple[_ScalarSoqlParameter]
    | set[_ScalarSoqlParameter]
)


def _sanitize_soql_query_parameter(  # noqa: PLR0911
    value: _SoqlParameter,
    like: bool = False,
) -> str:
    """
    Sanitize SOQL query parameter.

    Unless 'like' is True, the returned string is enclosed in single quotes.

    Parameters
    ----------
    value : str
        Value to be sanitized.
    like : bool, default True
        Whether the string is to be used in a LIKE clause, by default False.
        When True, % and _ characters are escaped and
        the returned string is not enclosed in single quotes.

    Returns
    -------
    str
        Sanitized string.

    """
    match value:
        case True:
            return "true"
        case False:
            return "false"
        case None:
            return "null"
        case int() | float():
            return str(value)
        case datetime.datetime():
            # yyyy-MM-ddTHH:mm:ss.SSS+/-HH:mm
            return value.isoformat(timespec="milliseconds")
        case datetime.date():
            return value.strftime(r"%Y-%m-%d")
        case str():
            pass
        case list() | tuple() | set():
            sanitized_values = []
            for item in value:
                if isinstance(item, (list, tuple, set)):
                    raise TypeError("Nested lists, tuples, and sets are not allowed")
                sanitized_values.append(_sanitize_soql_query_parameter(item, like=like))
            return f"({','.join(sanitized_values)})"
        case _:
            raise TypeError(f"Invalid SOQL parameter type: {type(value).__name__}")

    sanitized_value = value
    for char, sanitized_char in SOQL_RESERVED_CHARACTERS.items():
        sanitized_value = sanitized_value.replace(char, sanitized_char)
    for char, sanitized_char in SOQL_ESCAPE_SEQUENCES.items():
        sanitized_value = sanitized_value.replace(char, sanitized_char)
    if like:
        for char, sanitized_char in SOQL_ESCAPE_SEQUENCES_FOR_LIKE.items():
            sanitized_value = sanitized_value.replace(char, sanitized_char)
    return sanitized_value if like else f"'{sanitized_value}'"


class SoqlFormatter(string.Formatter):
    def format_field(self, value: Any, format_spec: str) -> Any:
        match format_spec:
            case "like":
                return super().format_field(
                    _sanitize_soql_query_parameter(value, like=True),
                    "",
                )
            case _:
                return super().format_field(
                    _sanitize_soql_query_parameter(value, like=False),
                    format_spec,
                )


def format_soql(query: LiteralString, *args, **kwargs) -> str:
    """
    Format SOQL query template with dynamic parameters.

    While SOQL queries are safe by design (cannot create/update/delete records),
    it is still possible to expose sensitive information via SOQL injection.
    It is always recommended to use this function instead of string formatting.

    You should never surround your parameters with single quotes in the query
    template - this is done automatically by this function when necessary.
    E.g., "SELECT Id FROM Object WHERE Value = {value}"

    The only exception to this rule is when you use the 'like' format spec.
    The 'like' format spec is used to escape special characters in a LIKE pattern
    when a portion of it is dynamic.
    E.g., "SELECT Id FROM Object WHERE Value LIKE '%{value:like}'"

    If you don't use the 'like' format spec when formatting LIKE statements,
    you will get unnecessary quotes and special query characters
    (% and _) will not be escaped. This would make you vulnerable to SOQL injection.

    Examples
    --------
    >>> format_soql("SELECT Id FROM Account WHERE Name = {}", "John Doe")
    "SELECT Id FROM Account WHERE Name = 'John Doe'"
    >>> format_soql("SELECT Id FROM Account WHERE Name = {name}", name="John Doe")
    "SELECT Id FROM Account WHERE Name = 'John Doe'"
    >>> format_soql("SELECT Id FROM Account WHERE Name LIKE {value}", value="John%")
    "SELECT Id FROM Account WHERE Name LIKE 'John%'"
    >>> format_soql(
    >>>     "SELECT Id FROM Record WHERE Description LIKE '% fails {pattern:like}'",
    >>>     pattern="50% of the time",
    >>> )
    "SELECT Id FROM Record WHERE Description LIKE '% fails 50\\% of the time'"

    Parameters
    ----------
    query : LiteralString
        SOQL query template.

    Returns
    -------
    str
        Formatted SOQL query.

    """
    # Use vformat to avoid unnecessary args/kwargs unpacking
    return SoqlFormatter().vformat(query, args, kwargs)
