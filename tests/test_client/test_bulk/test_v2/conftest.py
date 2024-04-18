import dataclasses
import datetime
import random

from typing import Generator

import httpx
import orjson
import pytest
import respx

from aiosalesforce import Salesforce
from aiosalesforce.bulk.v2._csv import serialize_ingest_data
from aiosalesforce.bulk.v2.client import BulkClientV2
from aiosalesforce.bulk.v2.ingest import BulkIngestClient, JobInfo


@pytest.fixture(scope="function")
def bulk_client(salesforce: Salesforce) -> Generator[BulkClientV2, None, None]:
    yield salesforce.bulk_v2


@pytest.fixture(scope="function")
def ingest_client(bulk_client: BulkClientV2) -> Generator[BulkIngestClient, None, None]:
    yield bulk_client.ingest


class VirtualIngestJob:
    """
    Used to mock multiple httpx requests involved in managing
    a single Bulk API 2.0 ingest job.

    """

    def __init__(
        self,
        config: dict[str, str],
        httpx_mock_router: respx.MockRouter,
        ingest_client: BulkIngestClient,
        operation: str,
        sobject: str,
        external_id_field: str | None = None,
    ) -> None:
        self.config = config
        self.httpx_mock_router = httpx_mock_router
        self.ingest_client = ingest_client

        self.job_info = JobInfo(
            id="".join(random.choices("0123456789", k=18)),  # noqa: S311
            operation=operation,
            object=sobject,
            created_by_id="00558000000yFyDAAU",
            created_date=datetime.datetime.now(),
            system_modstamp=datetime.datetime.now(),
            state="Open",  # type: ignore
            external_id_field_name=external_id_field,
            concurrency_mode="Parallel",
            content_type="CSV",
            api_version=self.config["api_version"],
            job_type="V2Ingest",
            content_url=(
                f"/services/data/v{self.config['api_version']}/jobs"
                f"/ingest/7503h00000L0k2AAAR/batches"
            ),
            line_ending="LF",
            column_delimiter="COMMA",
        )
        self.data = b""
        self.successful_results: list[dict] = []
        self.failed_results: list[dict] = []
        self.unprocessed_records: list[dict] = []

        # Mock job creation
        self.httpx_mock_router.post(self.ingest_client.base_url).mock(
            return_value=httpx.Response(
                status_code=200,
                content=self.job_info_json,
            )
        )

        # Mock job data upload
        def upload_data(request: httpx.Request) -> httpx.Response:
            self.data = request.content
            return httpx.Response(status_code=200, content=self.job_info_json)

        self.httpx_mock_router.put(
            f"{self.ingest_client.base_url}/{self.job_info.id}/batches"
        ).mock(side_effect=upload_data)

        # Mock job state update
        def update_state(request: httpx.Request) -> httpx.Response:
            self.job_info.state = orjson.loads(request.content)["state"]
            return httpx.Response(status_code=200, content=self.job_info_json)

        self.httpx_mock_router.patch(
            f"{self.ingest_client.base_url}/{self.job_info.id}"
        ).mock(side_effect=update_state)

        # Mock job status polling (transitions status on each call)
        def get_job_status(request: httpx.Request) -> httpx.Response:
            if self.job_info.state == "UploadComplete":
                self.job_info.state = "InProgress"
            elif self.job_info.state == "InProgress":
                self.job_info.state = "JobComplete"
            return httpx.Response(status_code=200, content=self.job_info_json)

        self.httpx_mock_router.get(
            f"{self.ingest_client.base_url}/{self.job_info.id}"
        ).mock(side_effect=get_job_status)

        # Mock job results
        self.httpx_mock_router.get(
            f"{self.ingest_client.base_url}/{self.job_info.id}/successfulResults"
        ).mock(
            side_effect=lambda _: httpx.Response(
                status_code=200,
                content=next(iter(serialize_ingest_data(self.successful_results)))
                if len(self.successful_results) > 0
                else b"",
            )
        )
        self.httpx_mock_router.get(
            f"{self.ingest_client.base_url}/{self.job_info.id}/failedResults"
        ).mock(
            side_effect=lambda _: httpx.Response(
                status_code=200,
                content=next(iter(serialize_ingest_data(self.failed_results)))
                if len(self.failed_results) > 0
                else b"",
            )
        )
        self.httpx_mock_router.get(
            f"{self.ingest_client.base_url}/{self.job_info.id}/unprocessedrecords"
        ).mock(
            side_effect=lambda _: httpx.Response(
                status_code=200,
                content=next(iter(serialize_ingest_data(self.unprocessed_records)))
                if len(self.unprocessed_records) > 0
                else b"",
            )
        )

    @property
    def job_info_json(self) -> bytes:
        job_dict = dataclasses.asdict(self.job_info)

        def to_camel_case(s: str) -> str:
            v = "".join(part.capitalize() for part in s.split("_"))
            return v[0].lower() + v[1:]

        return orjson.dumps(
            {
                to_camel_case(field.name): job_dict[field.name]
                for field in dataclasses.fields(JobInfo)
            }
        )


@pytest.fixture(scope="function")
def virtual_ingest_job(
    config: dict[str, str],
    httpx_mock_router: respx.MockRouter,
    ingest_client: BulkIngestClient,
) -> Generator[VirtualIngestJob, None, None]:
    yield VirtualIngestJob(
        config=config,
        httpx_mock_router=httpx_mock_router,
        ingest_client=ingest_client,
        operation="insert",
        sobject="Account",
        external_id_field=None,
    )
