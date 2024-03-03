import re

from httpx import AsyncClient

from .auth import Auth


class AsyncSalesforce:
    def __init__(
        self,
        http_client: AsyncClient,
        base_url: str,
        auth: Auth,
        version: str = "60.0",
    ) -> None:
        """
        Asynchronous Salesforce client.

        Parameters
        ----------
        http_client : AsyncClient
            Asynchronous HTTP client.
        base_url : str
            Base URL of the Salesforce instance.
            Must be in the format:
                - https://[MyDomainName].my.salesforce.com
                - https://[MyDomainName]-[SandboxName].sandbox.my.salesforce.com
        auth : Auth
            Authentication object.
        version : str, optional
            Salesforce API version.
            Uses the latest version

        """
        self.http_client = http_client
        self.auth = auth
        self.version = version

        # Validate url
        match_ = re.fullmatch(
            r"(https://[a-zA-Z0-9-]+(\.sandbox)?\.my\.salesforce\.com).*",
            base_url.strip(" ").lower(),
        )
        if not match_:
            raise ValueError(
                f"Invalid Salesforce URL in '{base_url}'. "
                f"Must be in the format "
                f"https://[MyDomainName].my.salesforce.com for production "
                f"or "
                f"https://[MyDomainName]-[SandboxName].sandbox.my.salesforce.com "
                f"for sandbox."
            )
        self.base_url = match_.groups()[0]
