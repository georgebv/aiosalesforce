import dataclasses
import logging

from functools import cached_property
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from aiosalesforce.client import Salesforce

from .ingest import BulkIngestClient, JobInfo, OperationType

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class IngestResult:
    """Bulk API 2.0 ingest operation result."""

    jobs: list[JobInfo]
    successful_results: list[dict[str, str]]
    failed_results: list[dict[str, str]]
    unprocessed_records: list[dict[str, str]]


class BulkClientV2:
    """
    Salesforce Bulk API 2.0 client.

    Use this client to execute bulk ingest and query operations.

    Parameters
    ----------
    salesforce_client : Salesforce
        Salesforce client.

    """

    salesforce_client: "Salesforce"
    base_url: str
    """Base URL in the format https://[subdomain(s)].my.salesforce.com/services/data/v[version]/jobs"""

    def __init__(self, salesforce_client: "Salesforce") -> None:
        self.salesforce_client = salesforce_client
        self.base_url = "/".join(
            [
                self.salesforce_client.base_url,
                "services",
                "data",
                f"v{self.salesforce_client.version}",
                "jobs",
            ]
        )

    @cached_property
    def ingest(self) -> BulkIngestClient:
        """Manage ingest jobs at a low level."""
        return BulkIngestClient(self)

    async def __perform_operation(
        self,
        operation: OperationType,
        sobject: str,
        data: Iterable[dict[str, Any]],
        external_id_field: str | None = None,
        assignment_rule_id: str | None = None,
    ) -> IngestResult:
        result = IngestResult([], [], [], [])
        async for job_result in self.ingest.perform_operation(
            operation=operation,
            sobject=sobject,
            data=data,
            external_id_field=external_id_field,
            assignment_rule_id=assignment_rule_id,
        ):
            result.jobs.append(job_result.job_info)
            result.successful_results.extend(job_result.successful_results)
            result.failed_results.extend(job_result.failed_results)
            result.unprocessed_records.extend(job_result.unprocessed_records)
        return result

    async def insert(
        self,
        sobject: str,
        data: Iterable[dict[str, Any]],
        assignment_rule_id: str | None = None,
    ) -> IngestResult:
        """
        Create new records in Salesforce.

        Parameters
        ----------
        sobject : str
            Salesforce object name.
        data : Iterable[dict[str, Any]]
            Records to create.
        assignment_rule_id : str | None, default None
            The ID of an assignment rule to run for a Case or a Lead.

        Returns
        -------
        IngestResult
            Bulk API 2.0 ingest job results.

        """
        return await self.__perform_operation(
            "insert",
            sobject=sobject,
            data=data,
            assignment_rule_id=assignment_rule_id,
        )

    async def update(
        self,
        sobject: str,
        data: Iterable[dict[str, Any]],
        assignment_rule_id: str | None = None,
    ) -> IngestResult:
        """
        Update existing records in Salesforce.

        Parameters
        ----------
        sobject : str
            Salesforce object name.
        data : Iterable[dict[str, Any]]
            Records to update.
        assignment_rule_id : str | None, default None
            The ID of an assignment rule to run for a Case or a Lead.

        Returns
        -------
        IngestResult
            Bulk API 2.0 ingest job results.

        """
        return await self.__perform_operation(
            "update",
            sobject=sobject,
            data=data,
            assignment_rule_id=assignment_rule_id,
        )

    async def upsert(
        self,
        sobject: str,
        data: Iterable[dict[str, Any]],
        external_id_field: str,
        assignment_rule_id: str | None = None,
    ) -> IngestResult:
        """
        Create or update records in Salesforce.

        Parameters
        ----------
        sobject : str
            Salesforce object name.
        data : Iterable[dict[str, Any]]
            Records to create or update.
        external_id_field : str
            External ID field name.
        assignment_rule_id : str | None, default None
            The ID of an assignment rule to run for a Case or a Lead.

        Returns
        -------
        IngestResult
            Bulk API 2.0 ingest job results.

        """
        return await self.__perform_operation(
            "upsert",
            sobject=sobject,
            data=data,
            external_id_field=external_id_field,
            assignment_rule_id=assignment_rule_id,
        )

    async def delete(
        self,
        sobject: str,
        data: Iterable[dict[str, Any]],
        hard: bool = False,
    ) -> IngestResult:
        """
        Delete records from Salesforce.

        Parameters
        ----------
        sobject : str
            Salesforce object name.
        data : Iterable[dict[str, Any]]
            Records to delete.
        hard : bool, default False
            Whether to hard delete records.

        Returns
        -------
        IngestResult
            Bulk API 2.0 ingest job results.

        """
        return await self.__perform_operation(
            "hardDelete" if hard else "delete",
            sobject=sobject,
            data=data,
            assignment_rule_id=None,
        )
