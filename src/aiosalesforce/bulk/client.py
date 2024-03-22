import logging

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiosalesforce.client import Salesforce

logger = logging.getLogger(__name__)


class BulkClient:
    salesforce_client: "Salesforce"
    base_url: str
    """Base URL in the format https://[subdomain(s)].my.salesforce.com/services/data/v[version]/bulk"""

    def __init__(self, salesforce_client: "Salesforce") -> None:
        self.salesforce_client = salesforce_client
        self.base_url = "/".join(
            [
                f"{self.salesforce_client.base_url}",
                "services",
                "data",
                f"v{self.salesforce_client.version}",
                "bulk",
            ]
        )
