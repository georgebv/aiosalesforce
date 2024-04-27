from functools import cached_property
from html import unescape
from typing import TYPE_CHECKING, Iterable, Literal

import httpx

from aiosalesforce.composite.exceptions import InvalidStateError
from aiosalesforce.exceptions import raise_salesforce_error
from aiosalesforce.utils import json_dumps, json_loads

if TYPE_CHECKING:
    from aiosalesforce.client import Salesforce


class Subrequest:
    """
    Composite Batch subrequest.

    Parameters
    ----------
    method : Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
        HTTP method.
    url : str
        Request URL.
    rich_input : dict, optional
        Input body for the request.
    binary_part_name : str, optional
        Name of the binary part in the multipart request.
    binary_part_name_alias : str, optional
        The name parameter in the Content-Disposition header of the binary body part.

    """

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    url: str
    rich_input: dict | None
    binary_part_name: str | None
    binary_part_name_alias: str | None

    __response: dict | None

    def __init__(
        self,
        method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"],
        url: str,
        rich_input: dict | None = None,
        binary_part_name: str | None = None,
        binary_part_name_alias: str | None = None,
    ) -> None:
        self.method = method
        self.url = url
        self.rich_input = rich_input
        self.binary_part_name = binary_part_name
        self.binary_part_name_alias = binary_part_name_alias

        if (self.binary_part_name is None) ^ (self.binary_part_name_alias is None):
            raise ValueError(
                "Both or neither of 'binary_part_name' and 'binary_part_name_alias' "
                "must be provided."
            )

        self.__response = None

    def to_dict(self) -> dict:
        payload = {
            "method": self.method,
            "url": self.url,
            "richInput": self.rich_input,
            "binaryPartName": self.binary_part_name,
            "binaryPartNameAlias": self.binary_part_name_alias,
        }
        return {key: value for key, value in payload.items() if value is not None}

    @property
    def response(self) -> dict:
        """Subrequest response."""
        if self.__response is None:
            raise InvalidStateError("Subrequest response has not been set")
        return self.__response

    @response.setter
    def response(self, value: dict) -> None:
        self.__response = value

    @property
    def done(self) -> bool:
        """Whether the subrequest has been executed."""
        return self.__response is not None

    @property
    def status_code(self) -> int:
        """HTTP status code of the subrequest response."""
        return self.response["statusCode"]

    @property
    def result(self) -> dict | list | None:
        """Subrequest result (response body)."""
        return self.response["result"]

    @property
    def is_success(self) -> bool:
        """Whether this subrequest was successful."""
        return 200 <= self.status_code < 300

    def raise_for_status(self) -> None:
        """Raise an exception if this subrequest failed."""
        if not self.is_success:
            raise_salesforce_error(httpx.Response(self.status_code, json=self.result))


class QuerySubrequest(Subrequest):
    """SOQL query subrequest."""

    @property
    def records(self) -> list[dict]:
        """Query records."""
        self.raise_for_status()
        assert isinstance(self.result, dict)
        return self.result["records"]


class SobjectCreateSubrequest(Subrequest):
    """sObject create subrequest."""

    @property
    def id(self) -> str:
        """ID of the created record."""
        self.raise_for_status()
        assert isinstance(self.result, dict)
        return self.result["id"]


class SobjectGetSubrequest(Subrequest):
    """sObject get subrequest."""

    @property
    def record(self) -> dict:
        """Retrieved record."""
        self.raise_for_status()
        assert isinstance(self.result, dict)
        return self.result


class SobjectUpsertSubrequest(Subrequest):
    """sObject upsert subrequest."""

    @property
    def id(self) -> str:
        """ID of the upserted record."""
        self.raise_for_status()
        assert isinstance(self.result, dict)
        return self.result["id"]

    @property
    def created(self) -> bool:
        """Whether the record was created."""
        self.raise_for_status()
        assert isinstance(self.result, dict)
        return self.result["created"]


class SobjectSubrequestClient:
    """
    Client for sObject operations.

    Parameters
    ----------
    composite_batch_request : CompositeBatchRequest
        Composite Batch request.

    """

    composite_batch_request: "CompositeBatchRequest"
    base_path: str
    """Base path in the format /services/data/v[version]/sobjects"""

    def __init__(self, composite_batch_request: "CompositeBatchRequest") -> None:
        self.composite_batch_request = composite_batch_request
        self.base_path = "/".join(
            [
                "",
                "services",
                "data",
                f"v{self.composite_batch_request.salesforce_client.version}",
                "sobjects",
            ]
        )

    def create(
        self,
        sobject: str,
        /,
        data: dict | str | bytes | bytearray,
    ) -> SobjectCreateSubrequest:
        """
        Create a new record.

        Parameters
        ----------
        sobject : str
            Salesforce object name.
            E.g. "Account", "Contact", etc.
        data : dict | str | bytes | bytearray
            Data to create the record with.
            Either a dict or a JSON string/bytes representing a dict.

        Returns
        -------
        SobjectCreateSubrequest
            Create subrequest.
            Record ID can be accessed via the `id` property.

        """
        subrequest = SobjectCreateSubrequest(
            "POST",
            f"{self.base_path}/{sobject}",
            rich_input=data if isinstance(data, dict) else json_loads(data),
        )
        self.composite_batch_request.subrequests.append(subrequest)
        return subrequest

    def get(
        self,
        sobject: str,
        id_: str,
        /,
        external_id_field: str | None = None,
        fields: Iterable[str] | None = None,
    ) -> SobjectGetSubrequest:
        """
        Get record by ID or external ID.

        Parameters
        ----------
        sobject : str
            Salesforce object name.
            E.g. "Account", "Contact", etc.
        id_ : str
            Salesforce record ID or external ID (if external_id_field is provided).
        external_id_field : str, optional
            External ID field name, by default None.
        fields : Iterable[str], optional
            Fields to get for the record.
            By default returns all fields.

        Returns
        -------
        SobbjectGetSubrequest
            Get subrequest.
            Record can be accessed via the `record` property.

        """
        url = httpx.URL(
            "/".join(
                [
                    self.base_path,
                    sobject,
                    id_ if external_id_field is None else f"{external_id_field}/{id_}",
                ]
            )
        )
        if fields is not None:
            url = url.copy_add_param("fields", ",".join(fields))
        subrequest = SobjectGetSubrequest("GET", str(url))
        self.composite_batch_request.subrequests.append(subrequest)
        return subrequest

    def update(
        self,
        sobject: str,
        id_: str,
        /,
        data: dict | str | bytes | bytearray,
    ) -> Subrequest:
        """
        Update record by ID.

        Parameters
        ----------
        sobject : str
            Salesforce object name.
            E.g. "Account", "Contact", etc.
        id_ : str
            Salesforce record ID.
        data : dict | str | bytes | bytearray
            Data to update the record with.
            Either a dict or a JSON string/bytes representing a dict.

        Returns
        -------
        Subrequest

        """
        subrequest = Subrequest(
            "PATCH",
            f"{self.base_path}/{sobject}/{id_}",
            rich_input=data if isinstance(data, dict) else json_loads(data),
        )
        self.composite_batch_request.subrequests.append(subrequest)
        return subrequest

    def delete(
        self,
        sobject: str,
        id_: str,
        /,
        external_id_field: str | None = None,
    ) -> Subrequest:
        """
        Delete record by ID.

        Parameters
        ----------
        sobject : str
            Salesforce object name.
            E.g. "Account", "Contact", etc.
        id_ : str
            Salesforce record ID or external ID (if external_id_field is provided).
        external_id_field : str, optional
            External ID field name.
            If not provided, id_ is treated as a record ID.

        Returns
        -------
        Subrequest

        """
        url = f"{self.base_path}/{sobject}"
        if external_id_field is None:
            url += f"/{id_}"
        else:
            url += f"/{external_id_field}/{id_}"
        subrequest = Subrequest("DELETE", url)
        self.composite_batch_request.subrequests.append(subrequest)
        return subrequest

    def upsert(
        self,
        sobject: str,
        id_: str,
        /,
        external_id_field: str,
        data: dict | str | bytes | bytearray,
        validate: bool = True,
    ) -> SobjectUpsertSubrequest:
        """
        Upsert (update if exists, create if not) record by external ID.

        Parameters
        ----------
        sobject : str
            Salesforce object name.
            E.g. "Account", "Contact", etc.
        id_ : str
            Salesforce record external ID.
        external_id_field : str
            External ID field name.
        data : dict | str | bytes | bytearray
            Data to upsert the record with.
            Either a dict or a JSON string/bytes representing a dict.
        validate : bool, default True
            If True, validates the request and removes the external ID field
            from the data if it's present. By default True.
            The reason for this is that Salesforce does not allow
            payload to contain an external ID field when upserting on it.
            Set this to False if you know you data is correct and
            you want to improve performance.

        Returns
        -------
        SobjectUpsertSubrequest
            Upsert subrequest.
            Exposes 'id' and 'created' properties.

        """
        if validate:
            if isinstance(data, (str, bytes, bytearray)):
                data = json_loads(data)
            if not isinstance(data, dict):
                raise TypeError(
                    f"data must be a dict, str, bytes, or bytearray, "
                    f"got {type(data).__name__}"
                )
            try:
                if data[external_id_field] != id_:
                    raise ValueError(
                        f"External ID field '{external_id_field}' in data "
                        f"{data[external_id_field]} does not match "
                        f"the provided external id {id_}"
                    )
                data.pop(external_id_field)
            except KeyError:
                pass

        subrequest = SobjectUpsertSubrequest(
            "PATCH",
            f"{self.base_path}/{sobject}/{external_id_field}/{id_}",
            rich_input=data if isinstance(data, dict) else json_loads(data),
        )
        self.composite_batch_request.subrequests.append(subrequest)
        return subrequest


class CompositeBatchRequest:
    """
    Composite Batch request.

    Parameters
    ----------
    salesforce_client : Salesforce
        Salesforce client.
    halt_on_error : bool, default False
        If True, unprocessed subrequests will be halted if any subrequest fails.
    autoraise : bool, default False
        If True, an exception will be raised if any subrequest fails.
    group_errors : bool, default False
        Ignored if `autoraise` is False.
        If True, raises an ExceptionGroup with all errors.
        Otherwise, raises the first exception.

    """

    salesforce_client: "Salesforce"
    halt_on_error: bool
    autoraise: bool
    group_errors: bool

    subrequests: list[Subrequest]

    def __init__(
        self,
        salesforce_client: "Salesforce",
        halt_on_error: bool = False,
        autoraise: bool = False,
        group_errors: bool = False,
    ) -> None:
        self.salesforce_client = salesforce_client
        self.halt_on_error = halt_on_error
        self.autoraise = autoraise
        self.group_errors = group_errors

        self.subrequests = []

    async def execute(self) -> None:
        """Execute composite batch request and set subrequests' responses."""
        if len(self.subrequests) == 0:
            return
        response = await self.salesforce_client.request(
            "POST",
            "/".join(
                [
                    self.salesforce_client.base_url,
                    "services",
                    "data",
                    f"v{self.salesforce_client.version}",
                    "composite",
                    "batch",
                ]
            ),
            content=json_dumps(
                {
                    "haltOnError": self.halt_on_error,
                    "batchRequests": [
                        subrequest.to_dict() for subrequest in self.subrequests
                    ],
                }
            ),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        for subrequest, subrequest_response in zip(
            self.subrequests,
            # Salesforce escapes characters in Composite JSON response as if it was HTML
            json_loads(unescape(response.content.decode("utf-8")))["results"],
        ):
            subrequest.response = subrequest_response
        if self.autoraise:
            errors: list[Exception] = []
            for subrequest in self.subrequests:
                try:
                    subrequest.raise_for_status()
                except Exception as exc:
                    errors.append(exc)
            if len(errors) > 0:
                if self.group_errors:
                    raise ExceptionGroup("Composite Batch request error", errors)
                raise errors[0]

    async def __aenter__(self) -> "CompositeBatchRequest":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        # Execute only if no exception occurred
        if exc is None:
            await self.execute()

    def query(self, query: str, include_all_records: bool = False) -> QuerySubrequest:
        """
        Execute a SOQL query.

        Parameters
        ----------
        query : str
            SOQL query.
        include_all_records : bool, default False
            If True, includes all (active/deleted/archived) records.

        Returns
        -------
        QuerySubrequest
            Query subrequest.
            Records can be accessed via the `records` property.

        """
        url = httpx.URL(
            "/".join(
                [
                    "",
                    "services",
                    "data",
                    f"v{self.salesforce_client.version}",
                    "query" if not include_all_records else "queryAll",
                ]
            )
        ).copy_add_param("q", query)
        subrequest = QuerySubrequest("GET", str(url))
        self.subrequests.append(subrequest)
        return subrequest

    @cached_property
    def sobject(self) -> SobjectSubrequestClient:
        """Perform sObject operations."""
        return SobjectSubrequestClient(self)
