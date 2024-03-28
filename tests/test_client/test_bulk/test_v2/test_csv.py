import datetime
import sys
import zoneinfo

from typing import Callable, Iterable

import pytest

from aiosalesforce.bulk.v2._csv import (
    _serialize_dict,
    _serialize_value,
    deserialize_ingest_results,
    serialize_ingest_data,
)


class TestValueSerializer:
    @pytest.mark.parametrize(
        "value, expected",
        [
            (True, "true"),
            (False, "false"),
            (None, ""),
            (datetime.datetime(2024, 5, 6, 12, 13, 14), "2024-05-06T12:13:14.000"),
            pytest.param(
                datetime.datetime(
                    *(2024, 5, 6, 12, 0, 0, 123000),
                    tzinfo=zoneinfo.ZoneInfo("America/New_York")
                    if sys.platform != "win32"
                    else None,
                ),
                "2024-05-06T12:00:00.123-04:00",
                marks=pytest.mark.skipif(
                    sys.platform == "win32",
                    reason="Windows doesn't have IANA time zone database",
                ),
            ),
            (datetime.date(2024, 5, 6), "2024-05-06"),
            ("foo", "foo"),
            (1, "1"),
            (1.5, "1.5"),
        ],
        ids=[
            "True",
            "False",
            "None",
            "datetime",
            "datetime with time zone",
            "date",
            "str",
            "int",
            "float",
        ],
    )
    def test_supported(self, value, expected):
        assert _serialize_value(value) == expected

    def test_unsupported(self):
        with pytest.raises(TypeError, match="Invalid value type"):
            _serialize_value(object())


class TestDictSerializer:
    def test_empty(self):
        assert _serialize_dict({}) == {}

    def test_single(self):
        data = {"FirstName": "Jon"}
        assert _serialize_dict(data) == {"FirstName": "Jon"}

    def test_nested(self):
        data = {"Name": {"FirstName": "Jon"}}
        assert _serialize_dict(data) == {"Name.FirstName": "Jon"}

    def test_invalid_nested(self):
        with pytest.raises(
            ValueError, match="Dict for 'Name' must have exactly one value"
        ):
            _serialize_dict({"Name": {"FirstName": "Jon", "LastName": "Doe"}})

    def test_invalid_value(self):
        with pytest.raises(TypeError, match="Invalid dict value for 'Name'"):
            _serialize_dict({"Name": {"FirstName": object()}})


class TestCsvSerializer:
    def test_empty(self):
        assert list(serialize_ingest_data([])) == []

    def test_single_row(self):
        data = [{"FirstName": "Jon", "LastName": "Doe"}]
        csvs = list(serialize_ingest_data(data))
        assert len(csvs) == 1
        assert csvs[0] == b"FirstName,LastName\nJon,Doe\n"

    @pytest.mark.parametrize(
        "func,warns",
        [
            (list, False),
            (tuple, False),
            (lambda x: (v for v in x), True),
        ],
        ids=[
            "list",
            "tuple",
            "generator",
        ],
    )
    def test_iterable_types(self, func: Callable[[Iterable], Iterable], warns: bool):
        """Tests for a bug where generator was not properly reused."""
        data = [{"FirstName": "Jon", "LastName": "Doe"} for _ in range(100)]
        if warns:
            with pytest.warns(UserWarning, match="Passing a generator"):
                csvs = list(serialize_ingest_data(func(data)))
        else:
            csvs = list(serialize_ingest_data(func(data)))
        assert len(csvs) == 1
        # Extra for header and trailing newline
        assert len(csvs[0].split(b"\n")) == 102

    def test_multiple_files(self):
        data = [{"FirstName": "Jon", "LastName": "Doe"} for _ in range(100)]
        csvs = list(serialize_ingest_data(data, max_records=30))
        assert len(csvs) == 4
        for i in range(3):
            assert len(deserialize_ingest_results(csvs[i])) == 30
        assert len(deserialize_ingest_results(csvs[-1])) == 10

    def test_carryover(self):
        data = [{"FirstName": "Jon", "LastName": "Doe"} for _ in range(100)]
        csvs = list(serialize_ingest_data(data, max_size_bytes=117))
        assert len(csvs) == 9
        assert sum(len(deserialize_ingest_results(csv)) for csv in csvs) == len(data)

    def test_nested(self):
        data = [
            {"FirstName": "Jon", "LastName": "Doe", "Employer__r": {"EID__c": "123"}}
            for _ in range(100)
        ]
        csvs = list(serialize_ingest_data(data))
        assert len(csvs) == 1
        assert csvs[0] == b"\n".join(
            [
                b"FirstName,LastName,Employer__r.EID__c",
                *[b"Jon,Doe,123" for _ in range(100)],
                b"",
            ]
        )

    def test_everything(self):
        data = [
            {
                "Active": True,
                "Rehire": False,
                "Bonus": None,
                "Hired": datetime.datetime(2024, 5, 6, 12, 13, 14),
                "Birthdate": datetime.date(2000, 1, 1),
                "FirstName": "Jon",
                "LastName": "Doe",
                "Salary": 100_000,
                "TaxRate": 0.25,
                "Employer__r": {"EID__c": "123"},
            }
            for _ in range(100)
        ]
        csvs = list(serialize_ingest_data(data, max_records=30))
        assert len(csvs) == 4
        for i in range(3):
            assert csvs[i] == b"\n".join(
                [
                    b"Active,Rehire,Bonus,Hired,Birthdate,FirstName,LastName,Salary,TaxRate,Employer__r.EID__c",
                    *[
                        b"true,false,,2024-05-06T12:13:14.000,2000-01-01,Jon,Doe,100000,0.25,123"
                        for _ in range(30)
                    ],
                    b"",
                ]
            )
            assert len(deserialize_ingest_results(csvs[i])) == 30
        assert csvs[-1] == b"\n".join(
            [
                b"Active,Rehire,Bonus,Hired,Birthdate,FirstName,LastName,Salary,TaxRate,Employer__r.EID__c",
                *[
                    b"true,false,,2024-05-06T12:13:14.000,2000-01-01,Jon,Doe,100000,0.25,123"
                    for _ in range(10)
                ],
                b"",
            ]
        )
        assert len(deserialize_ingest_results(csvs[-1])) == 10
