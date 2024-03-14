from typing import Any

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
    return orjson.dumps(data)


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
