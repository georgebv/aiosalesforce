import dataclasses
import datetime

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import httpx
import orjson
import pytest
import respx

from aiosalesforce.bulk.v2.ingest import BulkIngestClient, JobInfo, JobResult

if TYPE_CHECKING:
    from .conftest import VirtualIngestJob


def job_info_to_json(job: JobInfo) -> bytes:
    job_dict = dataclasses.asdict(job)

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
def dummy_job(config: dict[str, str]) -> JobInfo:
    return JobInfo(
        id="7503h00000L0k2AAAR",
        operation="insert",
        object="Account",
        created_by_id="00558000000yFyDAAU",
        created_date=datetime.datetime.now(),
        system_modstamp=datetime.datetime.now(),
        state="Open",
        external_id_field_name=None,
        concurrency_mode="Parallel",
        content_type="CSV",
        api_version=config["api_version"],
        job_type="V2Ingest",
        content_url=(
            f"/services/data/v{config['api_version']}/jobs"
            f"/ingest/7503h00000L0k2AAAR/batches"
        ),
        line_ending="LF",
        column_delimiter="COMMA",
    )


async def test_create_job(
    httpx_mock_router: respx.MockRouter,
    ingest_client: BulkIngestClient,
    dummy_job: JobInfo,
):
    dummy_job.operation = "upsert"
    dummy_job.external_id_field_name = "ExternalId__c"
    httpx_mock_router.post(ingest_client.base_url).mock(
        return_value=httpx.Response(
            status_code=200,
            content=job_info_to_json(dummy_job),
        )
    )
    job = await ingest_client.create_job(
        operation="upsert",
        sobject=dummy_job.object,
        external_id_field=dummy_job.external_id_field_name,
        assignment_rule_id="7503h00000L0k2AAAR",
    )
    assert job == dummy_job


async def test_get_job(
    httpx_mock_router: respx.MockRouter,
    ingest_client: BulkIngestClient,
    dummy_job: JobInfo,
):
    job_id = "7503h00000L0k2AAAR"
    httpx_mock_router.get(f"{ingest_client.base_url}/{job_id}").mock(
        return_value=httpx.Response(
            status_code=200,
            content=job_info_to_json(dummy_job),
        )
    )
    job = await ingest_client.get_job(job_id)
    assert job == dummy_job


async def test_list_jobs(
    config: dict[str, str],
    httpx_mock_router: respx.MockRouter,
    ingest_client: BulkIngestClient,
    dummy_job: JobInfo,
):
    dummy_jobs = [
        dataclasses.replace(dummy_job, id=f"7503h00000L0k2AAAR{i}") for i in range(10)
    ]
    next_url = "/".join(
        [
            "",
            "services",
            "data",
            f"v{config['api_version']}",
            "jobs",
            "ingest?isPkChunkingEnabled=false&offset=5",
        ]
    )
    httpx_mock_router.get(f"{ingest_client.base_url}?isPkChunkingEnabled=false").mock(
        return_value=httpx.Response(
            status_code=200,
            content=orjson.dumps(
                {
                    "records": [
                        orjson.loads(job_info_to_json(job)) for job in dummy_jobs[:5]
                    ],
                    "nextRecordsUrl": next_url,
                }
            ),
        )
    )
    httpx_mock_router.get(
        f"{ingest_client.bulk_client.salesforce_client.base_url}{next_url}"
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            content=orjson.dumps(
                {
                    "records": [
                        orjson.loads(job_info_to_json(job)) for job in dummy_jobs[5:]
                    ]
                }
            ),
        )
    )
    jobs = []
    async for job in ingest_client.list_jobs(is_pk_chunking_enabled=False):
        jobs.append(job)
    assert jobs == dummy_jobs


async def test_abort_job(
    httpx_mock_router: respx.MockRouter,
    ingest_client: BulkIngestClient,
    dummy_job: JobInfo,
):
    job_id = "7503h00000L0k2AAAR"
    dummy_job.id = job_id
    dummy_job.state = "Aborted"

    async def side_effect(request: httpx.Request) -> httpx.Response:
        payload = orjson.loads(request.content)
        assert payload == {"state": "Aborted"}
        return httpx.Response(
            status_code=200,
            content=job_info_to_json(dummy_job),
        )

    httpx_mock_router.patch(f"{ingest_client.base_url}/{job_id}").mock(
        side_effect=side_effect
    )

    job = await ingest_client.abort_job(job_id)
    assert job == dummy_job


async def test_delete_job(
    httpx_mock_router: respx.MockRouter,
    ingest_client: BulkIngestClient,
):
    job_id = "7503h00000L0k2AAAR"
    httpx_mock_router.delete(f"{ingest_client.base_url}/{job_id}").mock(
        return_value=httpx.Response(status_code=204)
    )
    await ingest_client.delete_job(job_id)


async def test_upload_job_data(
    httpx_mock_router: respx.MockRouter,
    ingest_client: BulkIngestClient,
    dummy_job: JobInfo,
):
    job_id = "7503h00000L0k2AAAR"
    data = b"hello world"

    dummy_job.id = job_id
    dummy_job.state = "UploadComplete"

    async def upload_data(request: httpx.Request) -> httpx.Response:
        assert request.content == data
        return httpx.Response(status_code=200)

    async def upload_complete(request: httpx.Request) -> httpx.Response:
        assert orjson.loads(request.content) == {"state": "UploadComplete"}
        return httpx.Response(
            status_code=200,
            content=job_info_to_json(dummy_job),
        )

    httpx_mock_router.put(f"{ingest_client.base_url}/{job_id}/batches").mock(
        side_effect=upload_data
    )
    httpx_mock_router.patch(f"{ingest_client.base_url}/{job_id}").mock(
        side_effect=upload_complete
    )

    job = await ingest_client.upload_job_data(job_id, data)
    assert job == dummy_job


async def test_perform_operation(
    ingest_client: BulkIngestClient,
    virtual_ingest_job: "VirtualIngestJob",
):
    # When deserialized from CSV returned by Salesforce everything is a string
    data = [
        {"FirstName": "John", "LastName": "Doe", "Age": "30"},
        {"FirstName": "Jane", "LastName": "Doe", "Age": "42"},
    ]
    result = [
        {"sf__Created": "true", "sf__Id": f"{i}-abc", **record}
        for i, record in enumerate(data)
    ]
    virtual_ingest_job.mock_results("successfulResults", result)

    # Mock sleeping when polling job status
    sleep_mock = AsyncMock()
    with patch("asyncio.sleep", sleep_mock):
        results: list[JobResult] = []
        async for _result in ingest_client.perform_operation("insert", "Contact", data):
            results.append(_result)
    # 2 transitions: UploadComplete -> InProgress -> JobComplete
    assert sleep_mock.await_count == 2

    assert len(results) == 1
    assert results[0].job_info == virtual_ingest_job.job_info
    assert results[0].successful_results == result
    assert results[0].failed_results == []
    assert results[0].unprocessed_records == []
