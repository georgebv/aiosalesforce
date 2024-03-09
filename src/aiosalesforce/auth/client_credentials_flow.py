from httpx import AsyncClient

from aiosalesforce.auth.base import Auth
from aiosalesforce.exceptions import AuthenticationError


class ClientCredentialsFlow(Auth):
    """
    Authenticate using the OAuth 2.0 Client Credentials Flow.

    https://help.salesforce.com/s/articleView?id=sf.remoteaccess_oauth_client_credentials_flow.htm&type=5

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
    ) -> str:
        del version  # not used in this flow (this line is for linter)
        response = await client.post(
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
        if not response.is_success:
            raise AuthenticationError(response.text, response)
        return response.json()["access_token"]
