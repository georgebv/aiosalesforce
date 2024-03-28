from typing import Generator

import pytest

from aiosalesforce import Salesforce
from aiosalesforce.bulk.v2.client import BulkClientV2
from aiosalesforce.bulk.v2.ingest import BulkIngestClient


@pytest.fixture(scope="function")
def bulk_client(salesforce: Salesforce) -> Generator[BulkClientV2, None, None]:
    yield salesforce.bulk_v2


@pytest.fixture(scope="function")
def ingest_client(bulk_client: BulkClientV2) -> Generator[BulkIngestClient, None, None]:
    yield bulk_client.ingest
