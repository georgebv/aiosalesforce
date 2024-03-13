import re
import textwrap
import time

from httpx import AsyncClient

from aiosalesforce.auth.base import Auth
from aiosalesforce.events import EventBus, RestApiCallConsumptionEvent
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

        self._expiration_time: float | None = None

    async def _acquire_new_access_token(
        self,
        client: AsyncClient,
        base_url: str,
        version: str,
        event_bus: EventBus,
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
                "Content-Type": "text/xml; charset=UTF-8",
                "SOAPAction": "login",
                "Accept": "text/xml",
            },
        )
        await event_bus.publish_event(
            RestApiCallConsumptionEvent(
                type="rest_api_call_consumption",
                response=response,
            )
        )
        response_text = response.text
        if not response.is_success:
            try:
                exception_code = str(
                    re.search(
                        r"<sf:exceptionCode>(.+)<\/sf:exceptionCode>",
                        response_text,
                    ).groups()[0]  # type: ignore
                )
            except AttributeError:  # pragma: no cover
                exception_code = None
            try:
                exception_message = str(
                    re.search(
                        r"<sf:exceptionMessage>(.+)<\/sf:exceptionMessage>",
                        response_text,
                    ).groups()[0]  # type: ignore
                )
            except AttributeError:  # pragma: no cover
                exception_message = response_text
            raise AuthenticationError(
                message=(
                    f"[{exception_code}] {exception_message}"
                    if exception_code
                    else exception_message
                ),
                response=response,
                error_code=exception_code,
                error_message=exception_message,
            )
        match_ = re.search(r"<sessionId>(.+)<\/sessionId>", response_text)
        if match_ is None:  # pragma: no cover
            raise AuthenticationError(
                f"Failed to parse sessionId from the SOAP response: {response_text}",
                response,
            )
        session_id = match_.groups()[0]

        # Parse expiration time
        match_ = re.search(
            r"<sessionSecondsValid>(.+)<\/sessionSecondsValid>",
            response_text,
        )
        self._expiration_time = None
        if match_ is not None:
            try:
                self._expiration_time = time.time() + int(match_.groups()[0])
            except ValueError:  # pragma: no cover
                pass

        return session_id

    @property
    def expired(self) -> bool:
        super().expired
        if self._expiration_time is None:  # pragma: no cover
            return False
        return self._expiration_time <= time.time()
