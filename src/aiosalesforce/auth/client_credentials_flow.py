import asyncio
import itertools

from httpx import AsyncClient

from aiosalesforce.auth.base import Auth
from aiosalesforce.events import (
    EventBus,
    RequestEvent,
    ResponseEvent,
    RestApiCallConsumptionEvent,
    RetryEvent,
)
from aiosalesforce.exceptions import AuthenticationError
from aiosalesforce.retries import RetryPolicy
from aiosalesforce.utils import json_loads


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

    async def _acquire_new_access_token(
        self,
        client: AsyncClient,
        base_url: str,
        version: str,
        event_bus: EventBus,
        retry_policy: RetryPolicy,
    ) -> str:
        del version  # not used in this flow (this line is for linter)
        request = client.build_request(
            "POST",
            f"{base_url}/services/oauth2/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        await event_bus.publish_event(RequestEvent(type="request", request=request))
        retry_context = retry_policy.create_context()
        for attempt in itertools.count():
            try:
                response = await client.send(request)
            except Exception as exc:
                if await retry_context.should_retry(exc):
                    await asyncio.gather(
                        retry_policy.sleep(attempt),
                        event_bus.publish_event(
                            RetryEvent(
                                type="retry",
                                attempt=attempt + 1,
                                request=request,
                                exception=exc,
                            )
                        ),
                    )
                    continue
                raise
            await event_bus.publish_event(
                RestApiCallConsumptionEvent(
                    type="rest_api_call_consumption",
                    response=response,
                    count=1,
                )
            )
            if response.is_success:
                break
            if await retry_context.should_retry(response):
                await asyncio.gather(
                    retry_policy.sleep(attempt),
                    event_bus.publish_event(
                        RetryEvent(
                            type="retry",
                            attempt=attempt + 1,
                            request=request,
                            response=response,
                        )
                    ),
                )
                continue
            break
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
        await event_bus.publish_event(ResponseEvent(type="response", response=response))
        return json_loads(response.content)["access_token"]
