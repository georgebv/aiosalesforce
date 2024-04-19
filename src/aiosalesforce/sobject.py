import logging

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

import httpx

from aiosalesforce.utils import json_dumps, json_loads

if TYPE_CHECKING:
    from .client import Salesforce

logger = logging.getLogger(__name__)


@dataclass
class UpsertResponse:
    id: str
    created: bool


class SobjectClient:
    """
    Salesforce REST API sObject client.

    Parameters
    ----------
    salesforce_client : Salesforce
        Salesforce client.

    """

    salesforce_client: "Salesforce"
    base_url: str
    """Base URL in the format https://[subdomain(s)].my.salesforce.com/services/data/v[version]/sobjects"""

    def __init__(self, salesforce_client: "Salesforce") -> None:
        self.salesforce_client = salesforce_client
        self.base_url = "/".join(
            [
                self.salesforce_client.base_url,
                "services",
                "data",
                f"v{self.salesforce_client.version}",
                "sobjects",
            ]
        )

    async def create(
        self,
        sobject: str,
        /,
        data: dict | str | bytes | bytearray,
    ) -> str:
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
        str
            ID of the created record.

        """
        response = await self.salesforce_client.request(
            "POST",
            f"{self.base_url}/{sobject}",
            content=json_dumps(data),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        return json_loads(response.content)["id"]

    async def get(
        self,
        sobject: str,
        id_: str,
        /,
        external_id_field: str | None = None,
        fields: Iterable[str] | None = None,
    ) -> dict:
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
        dict
            sObject data.

        """
        url = httpx.URL(
            "/".join(
                [
                    self.base_url,
                    sobject,
                    id_ if external_id_field is None else f"{external_id_field}/{id_}",
                ]
            )
        )
        if fields is not None:
            url = url.copy_add_param("fields", ",".join(fields))
        response = await self.salesforce_client.request(
            "GET",
            url,
            headers={"Accept": "application/json"},
        )
        return json_loads(response.content)

    async def update(
        self,
        sobject: str,
        id_: str,
        /,
        data: dict | str | bytes | bytearray,
    ) -> None:
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

        """
        await self.salesforce_client.request(
            "PATCH",
            f"{self.base_url}/{sobject}/{id_}",
            content=json_dumps(data),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )

    async def delete(
        self,
        sobject: str,
        id_: str,
        /,
        external_id_field: str | None = None,
    ) -> None:
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

        """
        await self.salesforce_client.request(
            "DELETE",
            "/".join(
                [
                    self.base_url,
                    sobject,
                    id_ if external_id_field is None else f"{external_id_field}/{id_}",
                ]
            ),
        )

    async def upsert(
        self,
        sobject: str,
        id_: str,
        /,
        external_id_field: str,
        data: dict | str | bytes | bytearray,
        validate: bool = True,
    ) -> UpsertResponse:
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
        UpsertResponse
            Dataclass with 'id' and 'created' fields.

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

        response = await self.salesforce_client.request(
            "PATCH",
            f"{self.base_url}/{sobject}/{external_id_field}/{id_}",
            content=json_dumps(data),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        response_json = json_loads(response.content)
        return UpsertResponse(
            id=response_json["id"],
            created=response_json["created"],
        )
