import pathlib
import time

from typing import TYPE_CHECKING

try:
    import jwt

    from cryptography.hazmat.primitives import serialization
except ImportError:  # pragma: no cover
    jwt = None  # type: ignore
    serialization = None  # type: ignore

from aiosalesforce.auth.base import Auth
from aiosalesforce.events import RequestEvent, ResponseEvent
from aiosalesforce.exceptions import AuthenticationError
from aiosalesforce.utils import json_loads

if TYPE_CHECKING:
    from aiosalesforce.client import Salesforce


class JwtBearerFlow(Auth):
    """
    Authenticate using the OAuth 2.0 JWT Bearer Flow.

    https://help.salesforce.com/s/articleView?id=sf.remoteaccess_oauth_jwt_flow.htm&type=5

    Parameters
    ----------
    client_id : str
        Client ID.
    username: str
        Username.
    private_key_file: str | pathlib.Path
        Path to private key file.
    private_key_passphrase: str, optional
        Passphrase for private key file.
        By default assumed to be unencrypted.
    timeout : float, optional
        Timeout for the access token in seconds.
        By default assumed to never expire.

    """

    def __init__(
        self,
        client_id: str,
        username: str,
        private_key_file: str | pathlib.Path,
        private_key_passphrase: str | None = None,
        timeout: float | None = None,
    ) -> None:
        super().__init__()
        self.client_id = client_id
        self.username = username
        self.private_key_file = private_key_file
        self.private_key_passphrase = private_key_passphrase
        self.timeout = timeout

        self._expiration_time: float | None = None

        if jwt is None or serialization is None:  # pragma: no cover
            raise ImportError("Install aiosalesforce[jwt] to use the JwtBearerFlow.")

    async def _acquire_new_access_token(self, client: "Salesforce") -> str:
        payload = {
            "iss": self.client_id,
            "aud": "https://test.salesforce.com"
            if client.base_url.endswith(".sandbox.my.salesforce.com")
            else "https://login.salesforce.com",
            "sub": self.username,
            "exp": int(time.time()) + 300,
        }
        with open(self.private_key_file, "rb") as file:
            private_key = serialization.load_pem_private_key(
                data=file.read(),
                password=self.private_key_passphrase.encode("utf-8")
                if self.private_key_passphrase is not None
                else None,
            )
        assertion = jwt.encode(
            payload,
            private_key,  # type: ignore
            algorithm="RS256",
            headers={"alg": "RS256"},
        )
        request = client.httpx_client.build_request(
            "POST",
            f"{client.base_url}/services/oauth2/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
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
        if self.timeout is not None:
            self._expiration_time = time.time() + self.timeout
        return json_loads(response.content)["access_token"]

    @property
    def expired(self) -> bool:
        super().expired
        if self._expiration_time is None:  # pragma: no cover
            return False
        return self._expiration_time <= time.time()
