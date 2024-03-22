import csv
import datetime

from typing import Any, Iterable


class CsvBuffer:
    __content: list[bytes]
    __size: int

    def __init__(self) -> None:
        self.__content = []
        self.__size = 0

    def write(self, row: str) -> None:
        """Write a row to the buffer."""
        encoded_row = row.encode("utf-8")
        self.__content.append(encoded_row)
        self.__size += len(encoded_row)

    def pop(self) -> bytes:
        """Remove and return the last row from the buffer."""
        row = self.__content.pop()
        self.__size -= len(row)
        return row

    def flush(self) -> None:
        """Clear the buffer."""
        self.__content = []
        self.__size = 0

    @property
    def n_rows(self) -> int:
        """Number of rows in the buffer (including the header)."""
        return len(self.__content)

    @property
    def size(self) -> int:
        """Size of the buffer in bytes."""
        return self.__size

    @property
    def content(self) -> bytes:
        """Contents of the buffer as a single byte string."""
        return b"".join(self.__content)


def _serialize_value(value: Any) -> str:
    """Serialize a scalar value to a string for CSV serialization."""
    match value:
        case True:
            return "true"
        case False:
            return "false"
        case None:
            return ""
        case datetime.datetime():
            # yyyy-MM-ddTHH:mm:ss.SSS+/-HH:mm
            return value.isoformat(timespec="milliseconds")
        case datetime.date():
            return value.strftime(r"%Y-%m-%d")
        case str() | int() | float():
            return str(value)
        case _:
            raise TypeError(f"Invalid value type '{type(value).__name__}'")


def _serialize_dict(data: dict[str, Any]) -> dict[str, str]:
    """Serialize a dictionary for CSV serialization."""
    new_dict = {}
    for key, value in data.items():
        new_key = key
        if isinstance(value, dict):
            if len(value) != 1:
                raise ValueError(
                    f"Dict for '{key}' must have exactly one value, got {len(value)}"
                )
            new_key = f"{key}.{next(iter(value.keys()))}"
            try:
                new_value = _serialize_value(next(iter(value.values())))
            except TypeError as exc:
                raise TypeError(f"Invalid dict value for '{key}'") from exc
        else:
            new_value = _serialize_value(value)
        new_dict[new_key] = new_value
    return new_dict


def serialize_ingest_data(
    data: Iterable[dict[str, Any]],
    fieldnames: list[str] | None = None,
    max_size_bytes: int = 100_000_000,
    max_records: int = 150_000_000,
) -> Iterable[bytes]:
    """
    Serialize data into CSV files for ingestion by Salesforce Bulk API 2.0.

    None or missing values are ignored by Salesforce.
    To set a field in Salesforce to NULL, use the string "#N/A".

    Parameters
    ----------
    data : Iterable[dict[str, Any]]
        Sequence of dictionaries, each representing a record.
    fieldnames : list[str], optional
        List of field names, determines order of fields in the CSV file.
        By default field names are inferred from the records. This is slow, so
        if you know the field names in advance, it is recommended to provide them.
        If a record is missing a field, it will be written as an empty string.
        If a record has a field not in `fieldnames`, an error will be raised.
    max_size_bytes : int, optional
        Maximum size of each CSV file in bytes.
        The default of 100MB is recommended by Salesforce recommends.
        This accounts for base64 encoding increases in size by up to 50%.
    max_records : int, optional
        Maximum number of records in each CSV file. By default 150,000,000.
        This corresponds to the maximum number of records in a 24-hour period.

    Yields
    ------
    Iterable[bytes]
        CSV file as a byte string.

    """
    if fieldnames is None:
        _fields: set[str] = set()
        for record in (_serialize_dict(record) for record in data):
            _fields.update(record.keys())
        fieldnames = list(_fields)

    buffer = CsvBuffer()
    writer = csv.DictWriter(
        buffer,
        fieldnames=fieldnames,
        lineterminator="\n",
    )

    carry_over: bytes | None = None
    for row in (_serialize_dict(record) for record in data):
        if buffer.size == 0:
            writer.writeheader()
            if carry_over is not None:
                buffer.write(carry_over.decode("utf-8"))
                carry_over = None
        writer.writerow(row)
        if buffer.size >= max_size_bytes or buffer.n_rows >= max_records:
            carry_over = buffer.pop()
            yield buffer.content
            buffer.flush()

    if buffer.size > 0:
        yield buffer.content
