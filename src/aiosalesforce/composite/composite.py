import itertools

from functools import cached_property
from html import unescape
from typing import TYPE_CHECKING, Iterable, Literal

import httpx

from aiosalesforce.composite.exceptions import InvalidStateError
from aiosalesforce.exceptions import raise_salesforce_error
from aiosalesforce.utils import json_dumps, json_loads

if TYPE_CHECKING:
    from aiosalesforce.client import Salesforce


class Reference(str):
    """
    Abstract reference to a subrequest result.

    Used to recursively traverse the reference chain using attribute access ($.attr)
    and item access ($[index]). For example, `ref.children[0].Id`.

    """

    def __init__(self, ref: str) -> None:
        self.ref = ref

    def __getattr__(self, attr: str) -> "Reference":
        return Reference(f"{self.ref}.{attr}")

    def __getitem__(self, index) -> "Reference":
        return Reference(f"{self.ref}[{index}]")

    def __repr__(self) -> str:
        return f"@{{{self.ref}}}"

    def __str__(self) -> str:
        return repr(self)


class Subrequest:
    """
    Composite subrequest.

    Parameters
    ----------
    reference_id : str
        Reference ID.
    method : Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
        HTTP method.
    url : str
        Request URL.
    body: dict, optional
        Request body.
    http_headers: dict, optional
        Request headers.

    """

    reference_id: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    url: str
    body: dict | None
    http_headers: dict | None

    __response: dict | None = None

    def __init__(
        self,
        reference_id: str,
        method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"],
        url: str,
        body: dict | None = None,
        http_headers: dict | None = None,
    ) -> None:
        self.reference_id = reference_id
        self.method = method
        self.url = url
        self.body = body
        self.http_headers = http_headers

        self.__response = None

    def to_dict(self) -> dict:
        payload = {
            "referenceId": self.reference_id,
            "method": self.method,
            "url": self.url,
            "body": self.body,
            "httpHeaders": self.http_headers,
        }
        return {key: value for key, value in payload.items() if value is not None}

    @property
    def reference(self) -> Reference:
        """
        Reference result of this subrequest in another subrequest.

        Examples
        --------
        >>> account = composite.sobject.create(
        ...     "Account",
        ...     {...},
        ... )
        ... contact = composite.sobject.create(
        ...     "Contact",
        ...     {"Account": account.reference.id, ...}
        ... )

        """
        return Reference(self.reference_id)

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
        return self.response is not None

    @property
    def response_body(self) -> dict | list | None:
        """Subrequest response body."""
        return self.response["body"]

    @property
    def response_http_headers(self) -> dict:
        """Subrequest response HTTP headers."""
        return self.response["httpHeaders"]

    @property
    def status_code(self) -> int:
        """HTTP status code of the subrequest response."""
        return self.response["httpStatusCode"]

    @property
    def is_success(self) -> bool:
        """Whether this subrequest was successful."""
        return 200 <= self.status_code < 300

    def raise_for_status(self) -> None:
        """Raise an exception if this subrequest failed."""
        if not self.is_success:
            raise_salesforce_error(
                httpx.Response(
                    self.status_code,
                    headers=self.response_http_headers,
                    json=self.response_body,
                )
            )


class QuerySubrequest(Subrequest):
    """SOQL query subrequest."""

    @property
    def records(self) -> list[dict]:
        """Query records."""
        self.raise_for_status()
        assert isinstance(self.response_body, dict)
        return self.response_body["records"]


class SobjectCreateSubrequest(Subrequest):
    """sObject create subrequest."""

    @property
    def id(self) -> str:
        """ID of the created record."""
        self.raise_for_status()
        assert isinstance(self.response_body, dict)
        return self.response_body["id"]


class SobjectGetSubrequest(Subrequest):
    """sObject get subrequest."""

    @property
    def record(self) -> dict:
        """Retrieved record."""
        self.raise_for_status()
        assert isinstance(self.response_body, dict)
        return self.response_body


class SobjectUpsertSubrequest(Subrequest):
    """sObject upsert subrequest."""

    @property
    def id(self) -> str:
        """ID of the upserted record."""
        self.raise_for_status()
        assert isinstance(self.response_body, dict)
        return self.response_body["id"]

    @property
    def created(self) -> bool:
        """Whether the record was created."""
        self.raise_for_status()
        assert isinstance(self.response_body, dict)
        return self.response_body["created"]


class SobjectSubrequestClient:
    """
    Client for sObject operations.

    Parameters
    ----------
    composite_request : CompositeRequest
        Composite request.

    """

    composite_request: "CompositeRequest"
    base_path: str
    """Base path in the format /services/data/v[version]/sobjects"""

    def __init__(self, composite_request: "CompositeRequest") -> None:
        self.composite_request = composite_request
        self.base_path = "/".join(
            [
                "",
                "services",
                "data",
                f"v{self.composite_request.salesforce_client.version}",
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
            self.composite_request.get_reference_id(f"{sobject}_create"),
            "POST",
            f"{self.base_path}/{sobject}",
            body=data if isinstance(data, dict) else json_loads(data),
        )
        self.composite_request.add_subrequest(subrequest)
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
        subrequest = SobjectGetSubrequest(
            self.composite_request.get_reference_id(f"{sobject}_get"),
            "GET",
            str(url),
        )
        self.composite_request.add_subrequest(subrequest)
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
            self.composite_request.get_reference_id(f"{sobject}_update"),
            "PATCH",
            f"{self.base_path}/{sobject}/{id_}",
            body=data if isinstance(data, dict) else json_loads(data),
        )
        self.composite_request.add_subrequest(subrequest)
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
        subrequest = Subrequest(
            self.composite_request.get_reference_id(f"{sobject}_delete"),
            "DELETE",
            url,
        )
        self.composite_request.add_subrequest(subrequest)
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
            self.composite_request.get_reference_id(f"{sobject}_upsert"),
            "PATCH",
            f"{self.base_path}/{sobject}/{external_id_field}/{id_}",
            body=data if isinstance(data, dict) else json_loads(data),
        )
        self.composite_request.add_subrequest(subrequest)
        return subrequest


class CompositeRequest:
    """
    Composite request.

    Parameters
    ----------
    salesforce_client : Salesforce
        Salesforce client.
    all_or_none : bool, default False
        If True, all subrequests are rolled back if any subrequest fails.
    collate_subrequests : bool, default True
        If True, independent subrequests are executed by Salesforce in parallel.
    autoraise : bool, default False
        If True, raises an ExceptionGroup if any subrequest fails.

    """

    salesforce_client: "Salesforce"
    all_or_none: bool
    collate_subrequests: bool
    autoraise: bool

    __subrequests: dict[str, Subrequest]
    __ref_counters: dict[str, itertools.count]

    def __init__(
        self,
        salesforce_client: "Salesforce",
        all_or_none: bool = False,
        collate_subrequests: bool = True,
        autoraise: bool = False,
    ) -> None:
        self.salesforce_client = salesforce_client
        self.all_or_none = all_or_none
        self.collate_subrequests = collate_subrequests
        self.autoraise = autoraise

        self.__subrequests = {}
        self.__ref_counters = {}

    def get_reference_id(self, name: str) -> str:
        """
        Get a unique reference ID for a subrequest.

        Parameters
        ----------
        name : str
            Subrequest name.
            E.g. 'Query' or 'Contact_create'.

        Returns
        -------
        str
            Unique reference ID.
            E.g., 'Query_0' or 'Contact_create_3'.

        """
        counter = self.__ref_counters.setdefault(name.lower(), itertools.count())
        return f"{name}_{next(counter)}"

    def add_subrequest(self, subrequest: Subrequest) -> None:
        if subrequest.reference_id in self.__subrequests:
            raise ValueError(
                f"Reference ID '{subrequest.reference_id}' is already in use."
            )
        self.__subrequests[subrequest.reference_id] = subrequest

    async def execute(self) -> None:
        """Execute composite request and set subrequests' responses."""
        if len(self.__subrequests) == 0:
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
                ]
            ),
            content=json_dumps(
                {
                    "allOrNone": self.all_or_none,
                    "collateSubrequests": self.collate_subrequests,
                    "compositeRequest": [
                        subrequest.to_dict()
                        for subrequest in self.__subrequests.values()
                    ],
                }
            ),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        for subrequest, subrequest_response in zip(
            self.__subrequests.values(),
            # Salesforce escapes characters in Composite JSON response as if it was HTML
            json_loads(unescape(response.content.decode("utf-8")))["compositeResponse"],
        ):
            subrequest.response = subrequest_response
        if self.autoraise:
            errors: list[Exception] = []
            for subrequest in self.__subrequests.values():
                try:
                    subrequest.raise_for_status()
                except Exception as exc:
                    errors.append(exc)
            if len(errors) > 0:
                raise ExceptionGroup("Composite request error", errors)

    async def __aenter__(self) -> "CompositeRequest":
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
        reference_id = self.get_reference_id("Query")
        subrequest = QuerySubrequest(reference_id, "GET", str(url))
        self.add_subrequest(subrequest)
        return subrequest

    @cached_property
    def sobject(self) -> SobjectSubrequestClient:
        """Perform sObject operations."""
        return SobjectSubrequestClient(self)
