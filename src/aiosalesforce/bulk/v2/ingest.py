import asyncio
import dataclasses
import datetime
import math

from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Collection,
    Iterable,
    Literal,
    Self,
    TypeAlias,
)

from httpx import Response

from aiosalesforce.events import BulkApiBatchConsumptionEvent
from aiosalesforce.utils import json_dumps, json_loads

from ._csv import deserialize_ingest_results, serialize_ingest_data

if TYPE_CHECKING:
    from .client import BulkClientV2

OperationType: TypeAlias = Literal[
    "insert",
    "delete",
    "hardDelete",
    "update",
    "upsert",
]


@dataclasses.dataclass
class JobInfo:
    """Bulk API 2.0 ingest job information."""

    id: str
    operation: str
    object: str
    created_by_id: str
    created_date: datetime.datetime
    system_modstamp: datetime.datetime
    state: Literal[
        "Open",
        "UploadComplete",
        "InProgress",
        "JobComplete",
        "Aborted",
        "Failed",
    ]
    external_id_field_name: str | None
    concurrency_mode: Literal["Parallel"]
    content_type: Literal["CSV"]
    api_version: str
    job_type: Literal["V2Ingest"] | None
    content_url: str
    line_ending: Literal["LF", "CRLF"]
    column_delimiter: Literal[
        "BACKQUOTE",
        "CARET",
        "COMMA",
        "PIPE",
        "SEMICOLON",
        "TAB",
    ]

    @classmethod
    def from_json(cls, data: bytes) -> Self:
        job_info = cls(
            **{
                field.name: (_ := json_loads(data)).get(
                    "".join(
                        [
                            component.capitalize() if i > 0 else component
                            for i, component in enumerate(field.name.split("_"))
                        ]
                    ),
                    None,
                )
                for field in dataclasses.fields(cls)
            }
        )
        for attr in ["created_date", "system_modstamp"]:
            setattr(
                job_info,
                attr,
                datetime.datetime.fromisoformat(getattr(job_info, attr)),
            )
        return job_info


@dataclasses.dataclass
class JobResult:
    """Bulk API 2.0 ingest job result."""

    job_info: JobInfo
    successful_results: list[dict[str, str]]
    failed_results: list[dict[str, str]]
    unprocessed_records: list[dict[str, str]]


class BulkIngestClient:
    """
    Salesforce Bulk API 2.0 ingest client.

    This is a low-level client used to manage ingest jobs.

    Parameters
    ----------
    bulk_client : BulkClientV2
        Bulk API 2.0 client from this client is invoked.

    """

    bulk_client: "BulkClientV2"
    base_url: str
    """Base URL in the format https://[subdomain(s)].my.salesforce.com/services/data/v[version]/jobs/ingest"""

    def __init__(self, bulk_client: "BulkClientV2") -> None:
        self.bulk_client = bulk_client
        self.base_url = f"{self.bulk_client.base_url}/ingest"

    async def create_job(
        self,
        operation: OperationType,
        sobject: str,
        external_id_field: str | None = None,
        assignment_rule_id: str | None = None,
    ) -> JobInfo:
        """
        Create a new ingest job.

        Parameters
        ----------
        operation : {"insert", "delete", "hardDelete", "update", "upsert"}
            Operation to perform.
        sobject : str
            Salesforce object name.
        external_id_field : str | None, optional
            External ID field name, by default None.
            Used for upsert operations.
        assignment_rule_id : str | None, optional
            The ID of an assignment rule to run for a Case or a Lead.
            By default None.

        Returns
        -------
        JobInfo
            _description_
        """
        payload: dict[str, str] = {
            "columnDelimiter": "COMMA",
            "contentType": "CSV",
            "lineEnding": "LF",
            "object": sobject,
            "operation": operation,
        }
        if assignment_rule_id is not None:
            payload["assignmentRuleId"] = assignment_rule_id
        if external_id_field is not None:
            payload["externalIdFieldName"] = external_id_field
        response = await self.bulk_client.salesforce_client.request(
            "POST",
            self.base_url,
            content=json_dumps(payload),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        return JobInfo.from_json(response.content)

    async def get_job(self, job_id: str) -> JobInfo:
        """
        Get information about ingest job.

        Parameters
        ----------
        job_id : str
            Ingest job ID.

        Returns
        -------
        JobInfo
            Job information.

        """
        response = await self.bulk_client.salesforce_client.request(
            "GET",
            f"{self.base_url}/{job_id}",
            headers={"Accept": "application/json"},
        )
        return JobInfo.from_json(response.content)

    async def list_jobs(
        self,
        is_pk_chunking_enabled: bool | None = None,
    ) -> AsyncIterator[JobInfo]:
        """
        List all ingest jobs.

        Parameters
        ----------
        is_pk_chunking_enabled : bool | None, optional
            Filter by primary key chunking enabled, by default None.

        Yields
        ------
        JobInfo
            Job information.

        """
        params: dict[str, bool] | None = None
        if is_pk_chunking_enabled is not None:
            params = {"isPkChunkingEnabled": is_pk_chunking_enabled}

        next_url: str | None = None
        while True:
            if next_url is None:
                response = await self.bulk_client.salesforce_client.request(
                    "GET",
                    self.base_url,
                    params=params,
                    headers={"Accept": "application/json"},
                )
            else:
                response = await self.bulk_client.salesforce_client.request(
                    "GET",
                    f"{self.bulk_client.salesforce_client.base_url}{next_url}",
                    headers={"Accept": "application/json"},
                )
            response_json: dict = json_loads(response.content)
            for record in response_json["records"]:
                yield JobInfo.from_json(json_dumps(record))
            next_url = response_json.get("nextRecordsUrl", None)
            if next_url is None:
                break

    async def abort_job(self, job_id: str) -> JobInfo:
        """
        Abort ingest job.

        Parameters
        ----------
        job_id : str
            Ingest job ID.

        Returns
        -------
        JobInfo
            Job information.

        """
        response = await self.bulk_client.salesforce_client.request(
            "PATCH",
            f"{self.base_url}/{job_id}",
            content=json_dumps({"state": "Aborted"}),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        return JobInfo.from_json(response.content)

    async def delete_job(self, job_id: str) -> None:
        """
        Delete ingest job.

        Parameters
        ----------
        job_id : str
            Ingest job ID.

        """
        await self.bulk_client.salesforce_client.request(
            "DELETE",
            f"{self.base_url}/{job_id}",
        )

    async def upload_job_data(
        self,
        job_id: str,
        data: bytes,
    ) -> JobInfo:
        """
        Upload data for an ingest job.

        Job must be in the "Open" state.

        Parameters
        ----------
        job_id : str
            Ingest job ID.
        data : bytes
            CSV data to upload.

        Returns
        -------
        JobInfo
            Job information.

        """
        await self.bulk_client.salesforce_client.request(
            "PUT",
            f"{self.base_url}/{job_id}/batches",
            content=data,
            headers={"Content-Type": "text/csv"},
        )
        response = await self.bulk_client.salesforce_client.request(
            "PATCH",
            f"{self.base_url}/{job_id}",
            content=json_dumps({"state": "UploadComplete"}),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        await self.bulk_client.salesforce_client.event_bus.publish_event(
            BulkApiBatchConsumptionEvent(
                type="bulk_api_batch_consumption",
                response=response,
                # WARN Bulk API 2.0 does not provide a way to get the number of batches
                #      consumed in a job. Number of batches is estimated based on the
                #      Salesforce docs saying that a separate batch is created for every
                #      10,000 records in data. First row is header and is not counted.
                count=math.ceil((len(data.strip(b"\n").split(b"\n")) - 1) / 10_000),
            )
        )
        return JobInfo.from_json(response.content)

    async def __perform_operation(
        self,
        operation: OperationType,
        sobject: str,
        data: bytes,
        external_id_field: str | None = None,
        assignment_rule_id: str | None = None,
        polling_interval: float = 5.0,
    ) -> JobResult:
        job = await self.create_job(
            operation,
            sobject,
            external_id_field=external_id_field,
            assignment_rule_id=assignment_rule_id,
        )
        job = await self.upload_job_data(job.id, data)
        while job.state.lower().strip(" ") in {"open", "uploadcomplete", "inprogress"}:
            await asyncio.sleep(polling_interval)
            job = await self.get_job(job.id)

        tasks: list[asyncio.Task[Response]] = []
        async with asyncio.TaskGroup() as tg:
            for type_ in [
                "successfulResults",
                "failedResults",
                "unprocessedrecords",
            ]:
                tasks.append(
                    tg.create_task(
                        self.bulk_client.salesforce_client.request(
                            "GET",
                            f"{self.base_url}/{job.id}/{type_}",
                        )
                    )
                )

        return JobResult(
            job_info=job,
            successful_results=deserialize_ingest_results(
                tasks[0].result().content,
            ),
            failed_results=deserialize_ingest_results(
                tasks[1].result().content,
            ),
            unprocessed_records=deserialize_ingest_results(
                tasks[2].result().content,
            ),
        )

    async def perform_operation(
        self,
        operation: OperationType,
        sobject: str,
        data: Iterable[dict[str, Any]],
        fieldnames: Collection[str] | None = None,
        max_size_bytes: int = 100_000_000,
        max_records: int = 150_000_000,
        external_id_field: str | None = None,
        assignment_rule_id: str | None = None,
        polling_interval: float = 5.0,
    ) -> AsyncIterator[JobResult]:
        """
        Perform a bulk ingest operation.

        Parameters
        ----------
        operation : {"insert", "delete", "hardDelete", "update", "upsert"}
            Operation to perform.
        sobject : str
            Salesforce object name.
        data : Iterable[dict[str, Any]]
            Sequence of records to ingest.
        fieldnames : Collection[str], optional
            Field names, determines order of fields in the CSV file.
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
        external_id_field : str | None, optional
            External ID field name, by default None.
            Used for upsert operations.
        assignment_rule_id : str | None, optional
            The ID of an assignment rule to run for a Case or a Lead.
            By default None.
        polling_interval : float, optional
            Interval in seconds to poll the job status.
            By default 5.0 seconds.

        Yields
        ------
        JobResult
            Job result containing job information and successful, failed,
            and unprocessed records.

        """
        tasks: list[asyncio.Task[JobResult]] = []
        for csv_payload in serialize_ingest_data(
            data,
            fieldnames=fieldnames,
            max_size_bytes=max_size_bytes,
            max_records=max_records,
        ):
            tasks.append(
                asyncio.create_task(
                    self.__perform_operation(
                        operation,
                        sobject,
                        csv_payload,
                        external_id_field=external_id_field,
                        assignment_rule_id=assignment_rule_id,
                        polling_interval=polling_interval,
                    )
                )
            )
        for future in asyncio.as_completed(tasks):
            yield await future
