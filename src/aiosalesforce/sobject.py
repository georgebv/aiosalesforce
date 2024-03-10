import json
import logging

from dataclasses import dataclass
from typing import TYPE_CHECKING

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
                f"{self.salesforce_client.base_url}",
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
        data: dict | str | bytes,
    ) -> str:
        """
        Create a new record.

        Parameters
        ----------
        sobject : str
            Salesforce object name.
            E.g. "Account", "Contact", etc.
        data : dict | str | bytes
            Data to create the record with.

        Returns
        -------
        str
            ID of the created record.

        """
        response = await self.salesforce_client.request(
            "POST",
            f"{self.base_url}/{sobject}",
            json=data,
        )
        return response.json()["id"]

    async def get(
        self,
        sobject: str,
        id_: str,
        /,
        external_id_field: str | None = None,
        fields: list[str] | None = None,
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
        fields : list[str], optional
            Fields to get for the record, by default None (all fields).

        Returns
        -------
        dict
            _description_
        """
        url = f"{self.base_url}/{sobject}"
        if external_id_field is None:
            url += f"/{id_}"
        else:
            url += f"/{external_id_field}/{id_}"

        params: dict = {}
        if fields is not None:
            params["fields"] = ",".join(fields)

        response = await self.salesforce_client.request("GET", url, params=params)
        return response.json()

    async def update(
        self,
        sobject: str,
        id_: str,
        /,
        data: dict | str | bytes,
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
        data : dict | str | bytes
            Data to update the record with.

        """
        await self.salesforce_client.request(
            "PATCH",
            f"{self.base_url}/{sobject}/{id_}",
            json=data,
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
            External ID field name, by default None.

        """
        url = f"{self.base_url}/{sobject}"
        if external_id_field is None:
            url += f"/{id_}"
        else:
            url += f"/{external_id_field}/{id_}"
        await self.salesforce_client.request("DELETE", url)

    async def upsert(
        self,
        sobject: str,
        id_: str,
        external_id_field: str,
        /,
        data: dict | str | bytes,
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
        data : dict | str | bytes
            Data to upsert the record with.

        Returns
        -------
        UpsertResponse
            Dataclass with 'id' and 'created' fields.

        """
        if isinstance(data, dict):
            data.pop(external_id_field, None)
        elif (
            external_id_field in data
            if isinstance(data, str)
            else external_id_field in data.decode("utf-8")
        ):
            data = json.loads(data)
            if not isinstance(data, dict):
                raise TypeError(
                    "data must be a dict or a JSON string representing a dict"
                )
            data.pop(external_id_field, None)

        response = await self.salesforce_client.request(
            "PATCH",
            f"{self.base_url}/{sobject}/{external_id_field}/{id_}",
            json=data,
        )
        response_json = response.json()
        return UpsertResponse(
            id=response_json["id"],
            created=response_json["created"],
        )
