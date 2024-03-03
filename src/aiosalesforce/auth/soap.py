import re
import textwrap

from httpx import AsyncClient

from aiosalesforce.auth.base import Auth
from aiosalesforce.exceptions import AuthenticationError


class SoapLogin(Auth):
    """
    Authenticate using the SOAP login method.

    https://developer.salesforce.com/docs/atlas.en-us.api.meta/api/sforce_api_calls_login.htm

    """

    def __init__(
        self,
        username: str,
        password: str,
        security_token: str,
    ):
        super().__init__()
        self.username = username
        self.password = password
        self.security_token = security_token

    async def _acquire_new_access_token(
        self,
        client: AsyncClient,
        base_url: str,
        version: str,
    ) -> str:
        soap_xml_payload = f"""
        <?xml version="1.0" encoding="utf-8" ?>
        <env:Envelope
            xmlns:xsd="http://www.w3.org/2001/XMLSchema"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
            <env:Body>
                <n1:login xmlns:n1="urn:partner.soap.sforce.com">
                    <n1:username>{self.username}</n1:username>
                    <n1:password>{self.password}{self.security_token}</n1:password>
                </n1:login>
            </env:Body>
        </env:Envelope>
        """
        response = await client.post(
            f"{base_url}/services/Soap/u/{version}",
            content=textwrap.dedent(soap_xml_payload).strip(),
            headers={
                "Content-Type": "text/xml",
                "Charset": "UTF-8",
                "SOAPAction": "login",
            },
        )
        response_text = response.text
        if not response.is_success:
            match_ = re.search(
                r"<sf:exceptionMessage>(.+)<\/sf:exceptionMessage>",
                response_text,
            )
            if match_ is None:
                message = f"SOAP login failed: {response_text}"
            else:
                message = f"SOAP login failed: {match_.groups()[0]}"
            raise AuthenticationError(message, response)
        match_ = re.search(r"<sessionId>(.+)<\/sessionId>", response_text)
        if match_ is None:
            raise AuthenticationError(
                f"Failed to parse sessionId from the SOAP response: {response_text}",
                response,
            )
        return match_.groups()[0]

    async def _refresh_access_token(
        self,
        client: AsyncClient,
        base_url: str,
        version: str,
    ) -> str:
        return await self._acquire_new_access_token(client, base_url, version)
