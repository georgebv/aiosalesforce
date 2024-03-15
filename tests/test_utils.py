import datetime

import pytest

from aiosalesforce.utils import _sanitize_soql_query_parameter, format_soql


class TestSoqlFormatting:
    @pytest.mark.parametrize(
        "value, expected",
        [
            (True, "true"),
            (False, "false"),
            (None, "null"),
            (1, "1"),
            (1.23, "1.23"),
            (
                datetime.datetime(2024, 5, 6, 12, 0, 0),
                "2024-05-06T12:00:00+00:00",
            ),
            (
                datetime.datetime.strptime(
                    "2024-05-06T12:00:00+08:00",
                    r"%Y-%m-%dT%H:%M:%S%z",
                ),
                "2024-05-06T12:00:00+08:00",
            ),
            (datetime.date(2024, 5, 6), "2024-05-06"),
            ("foo", "'foo'"),
            ("", "''"),
            ("'", "'\\''"),
            ('"', "'\\\"'"),
            ("foo\nbar", "'foo\\nbar'"),
            ("foo\r\nbar", "'foo\\r\\nbar'"),
            ("foo\tbar", "'foo\\tbar'"),
            ("foo\bbar", "'foo\\bbar'"),
            ("foo\fbar", "'foo\\fbar'"),
            (
                "First Name:\t'John'\r\nLast Name:\t'Doe'",
                "'First Name:\\t\\'John\\'\\r\\nLast Name:\\t\\'Doe\\''",
            ),
            ("_Jon_\r\n%Doe%", "'_Jon_\\r\\n%Doe%'"),
        ],
        ids=[
            "boolean true",
            "boolean false",
            "null",
            "integer",
            "float",
            "datetime no tz",
            "datetime with tz",
            "date",
            "no-op string",
            "empty string",
            "single quote",
            "double quote",
            "newline",
            "crlf",
            "tab",
            "backspace",
            "form feed",
            "combination of escape sequences",
            "percent and underscore",
        ],
    )
    def test_sanitize_soql_query_parameter_without_like(
        self,
        value: str,
        expected: str,
    ):
        assert _sanitize_soql_query_parameter(value, like=False) == expected

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("foo", "foo"),
            ("foo%", "foo\\%"),
            ("foo_", "foo\\_"),
            ("%foo_bar%", "\\%foo\\_bar\\%"),
            ("foo%bar_\r\n_baz_", "foo\\%bar\\_\\r\\n\\_baz\\_"),
        ],
        ids=[
            "no-op string",
            "percent",
            "underscore",
            "percent and underscore",
            "combination of escape sequences",
        ],
    )
    def test_sanitize_soql_query_parameter_with_like(
        self,
        value: str,
        expected: str,
    ):
        assert _sanitize_soql_query_parameter(value, like=True) == expected

    @pytest.mark.parametrize(
        "value, expected",
        [
            ([1, 2, 3], "(1,2,3)"),
            ((1, 2, 3), "(1,2,3)"),
            ({1, 2, 3}, "(1,2,3)"),
            ([], "()"),
            ((), "()"),
            (set(), "()"),
            (
                [
                    True,
                    False,
                    None,
                    42,
                    3.14,
                    datetime.date(2024, 5, 6),
                    "_foo\r\nbar%",
                ],
                "".join(
                    [
                        "(",
                        ",".join(
                            [
                                "true",
                                "false",
                                "null",
                                "42",
                                "3.14",
                                "2024-05-06",
                                "'_foo\\r\\nbar%'",
                            ]
                        ),
                        ")",
                    ]
                ),
            ),
        ],
        ids=[
            "list of integers",
            "tuple of integers",
            "set of integers",
            "empty list",
            "empty tuple",
            "empty set",
            "list of mixed types",
        ],
    )
    def test_sanitize_soql_query_parameter_sequence(self, value: str, expected: str):
        assert _sanitize_soql_query_parameter(value, like=False) == expected

    def test_sanitize_soql_query_parameter_invalid_type_error(self):
        with pytest.raises(TypeError, match=r"Invalid SOQL parameter type: dict"):
            _sanitize_soql_query_parameter({"foo": "bar"}, like=False)  # type: ignore

    def test_sanitize_soql_query_parameter_nested_sequence_error(self):
        with pytest.raises(
            TypeError,
            match=r"Nested lists, tuples, and sets are not allowed",
        ):
            _sanitize_soql_query_parameter([1, [2, 3]], like=False)  # type: ignore

    @pytest.mark.parametrize(
        "query, args, kwargs, expected",
        [
            (
                "SELECT Id FROM Account WHERE Name = {}",
                ["Acme"],
                {},
                "SELECT Id FROM Account WHERE Name = 'Acme'",
            ),
            (
                "SELECT Id FROM Account WHERE Name = {name}",
                [],
                {"name": "Acme"},
                "SELECT Id FROM Account WHERE Name = 'Acme'",
            ),
            (
                "SELECT Id FROM Account WHERE Name = {} AND Industry = {}",
                ["Acme", "Technology"],
                {},
                "SELECT Id FROM Account WHERE Name = 'Acme' AND Industry = 'Technology'",
            ),
            (
                "SELECT Id FROM Account WHERE Name = {name} AND Industry = {industry}",
                [],
                {"name": "Acme", "industry": "Technology"},
                "SELECT Id FROM Account WHERE Name = 'Acme' AND Industry = 'Technology'",
            ),
            (
                "SELECT Id FROM Record WHERE Description = {}",
                ["_foo\r\nbar%"],
                {},
                "SELECT Id FROM Record WHERE Description = '_foo\\r\\nbar%'",
            ),
            (
                "SELECT Id FROM Record WHERE Description LIKE '%{value:like}_'",
                [],
                {"value": "_foo\r\nbar%"},
                "SELECT Id FROM Record WHERE Description LIKE '%\\_foo\\r\\nbar\\%_'",
            ),
            (
                "SELECT Id FROM Record WHERE Value IN {values}",
                [],
                {
                    "values": [
                        True,
                        False,
                        None,
                        42,
                        3.14,
                        datetime.date(2024, 5, 6),
                        "_foo\r\nbar%",
                    ]
                },
                " ".join(
                    [
                        "SELECT Id FROM Record WHERE Value IN",
                        "".join(
                            [
                                "(",
                                ",".join(
                                    [
                                        "true",
                                        "false",
                                        "null",
                                        "42",
                                        "3.14",
                                        "2024-05-06",
                                        "'_foo\\r\\nbar%'",
                                    ]
                                ),
                                ")",
                            ]
                        ),
                    ]
                ),
            ),
        ],
        ids=[
            "single arg",
            "single kwarg",
            "multiple args",
            "multiple kwargs",
            "escape sequences",
            "like format spec",
            "sequence",
        ],
    )
    def test_format_soql(
        self,
        query: str,
        args: list,
        kwargs: dict,
        expected: str,
    ):
        assert format_soql(query, *args, **kwargs) == expected
