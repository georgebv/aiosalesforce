import time
from html import unescape
from typing import TYPE_CHECKING

import jwt

from aiosalesforce.auth.base import Auth
from aiosalesforce.events import RequestEvent, ResponseEvent
from aiosalesforce.exceptions import AuthenticationError
from aiosalesforce.utils import json_loads

if TYPE_CHECKING:
    from aiosalesforce.client import Salesforce


class JwtFlow(Auth):
    """
    Authenticate using JWT

    https://help.salesforce.com/s/articleView?id=sf.remoteaccess_oauth_jwt_flow.htm&type=5

    Parameters
    ----------
    client_id : str
        Client ID.
    subject: str
        Username to authenticate with.
    priv_key_file: str
        Private key file.
    priv_key_passphrase: str | None
        Passphrase for private key file, if required

    """

    def __init__(
        self,
        client_id: str,
        subject: str,
        priv_key_file: str,
        priv_key_passphrase: str | None = None,
    ) -> None:
        super().__init__()
        self.client_id = client_id
        self.subject = subject
        self.priv_key_file = priv_key_file
        self.priv_key_passphrase = priv_key_passphrase

    async def _acquire_new_access_token(self, client: "Salesforce") -> str:
        expiration = int(time.time()) + 300
        sandbox = "sandbox." in client.base_url.lower()
        payload = {
            "iss": self.client_id,
            "sub": unescape(self.subject),
            "aud": f"https://{'test' if sandbox else 'login'}.salesforce.com",
            "exp": f"{expiration:.0f}",
        }
        with open(self.priv_key_file, "rb") as file:
            priv_key = file.read()

        if self.priv_key_passphrase:
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import serialization

            passphrase = self.priv_key_passphrase.encode("utf-8")
            private_key = serialization.load_pem_private_key(
                priv_key, password=passphrase, backend=default_backend()
            )
        else:
            private_key = priv_key

        assertion = jwt.encode(
            payload, private_key, algorithm="RS256", headers={"alg": "RS256"}
        )
        token_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }

        request = client.httpx_client.build_request(
            "POST",
            f"{client.base_url}/services/oauth2/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=token_data,
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
