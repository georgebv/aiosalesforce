import pytest

from aiosalesforce.bulk.v2._csv import serialize_ingest_data


class TestSerializer:
    def test_empty(self):
        assert list(serialize_ingest_data([])) == []

    @pytest.mark.parametrize(
        "type_",
        ["list", "generator"],
        ids=["list", "generator"],
    )
    def test_iterable_types(self, type_: str):
        """Tests for a bug where generator was not properly reused."""
        data = [{"FirstName": "Jon", "LastName": "Doe"} for _ in range(100)]
        match type_:
            case "list":
                csvs = list(serialize_ingest_data(data))
            case "generator":
                csvs = list(serialize_ingest_data((v for v in data)))
            case _:
                assert False, f"Unknown type: {type_}"
        assert len(csvs) == 1
        # Extra for header and trailing newline
        assert len(csvs[0].split(b"\n")) == 102
