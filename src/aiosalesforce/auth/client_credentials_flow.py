from typing import TYPE_CHECKING

from aiosalesforce.auth.base import Auth
from aiosalesforce.events import (
    RequestEvent,
    ResponseEvent,
)
from aiosalesforce.exceptions import AuthenticationError
from aiosalesforce.utils import json_loads

if TYPE_CHECKING:
    from aiosalesforce.client import Salesforce


class ClientCredentialsFlow(Auth):
    """
    Authenticate using the OAuth 2.0 Client Credentials Flow.

    https://help.salesforce.com/s/articleView?id=sf.remoteaccess_oauth_client_credentials_flow.htm&type=5

    Parameters
    ----------
    client_id : str
        Client ID.
    client_secret : str
        Client secret.

    """

    def __init__(self, client_id: str, client_secret: str) -> None:
        super().__init__()
        self.client_id = client_id
        self.client_secret = client_secret

    async def _acquire_new_access_token(self, client: "Salesforce") -> str:
        request = client.httpx_client.build_request(
            "POST",
            f"{client.base_url}/services/oauth2/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        await client.event_bus.publish_event(
            RequestEvent(
                type="request",
                request=request,
            )
        )
        retry_context = client.retry_policy.create_context()
        response = await retry_context.send_request_with_retries(
            httpx_client=client.httpx_client,
            event_bus=client.event_bus,
            semaphore=client._semaphore,
            request=request,
        )
        if not response.is_success:
            try:
                response_json = json_loads(response.content)
                error_code = response_json["error"]
                error_message = response_json["error_description"]
            except Exception:  # pragma: no cover
                error_code = None
                error_message = response.text
            raise AuthenticationError(
                f"[{error_code}] {error_message}" if error_code else error_message,
                response=response,
                error_code=error_code,
                error_message=error_message,
            )
        await client.event_bus.publish_event(
            ResponseEvent(
                type="response",
                response=response,
            )
        )
        return json_loads(response.content)["access_token"]
