from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from aiosalesforce.bulk.v2.client import BulkClientV2, IngestResult

if TYPE_CHECKING:
    from .conftest import VirtualIngestJob


@pytest.mark.parametrize("operation", ["insert", "update", "upsert", "delete"])
async def test_ingest_operation(
    bulk_client: BulkClientV2,
    virtual_ingest_job: "VirtualIngestJob",
    operation: str,
):
    # When deserialized from CSV returned by Salesforce everything is a string
    data = [
        {"FirstName": "John", "LastName": "Doe", "Age": "30", "EID__c": "abc"},
        {"FirstName": "Jane", "LastName": "Doe", "Age": "42", "EID__c": "def"},
    ]
    expected_results = [
        {"sf__Created": "true", "sf__Id": f"{i}-abc", **record}
        for i, record in enumerate(data)
    ]
    virtual_ingest_job.successful_results = expected_results

    # Mock sleeping when polling job status
    sleep_mock = AsyncMock()
    with patch("asyncio.sleep", sleep_mock):
        params = {}
        if operation == "upsert":
            params = {"external_id_field": "EID__c"}
        result: IngestResult = await getattr(bulk_client, operation)(
            "Contact", data, **params
        )
    # 2 transitions: UploadComplete -> InProgress -> JobComplete
    assert sleep_mock.await_count == 2

    assert len(result.jobs) == 1
    assert result.jobs[0] == virtual_ingest_job.job_info
    assert result.successful_results == expected_results
    assert result.failed_results == []
    assert result.unprocessed_records == []
