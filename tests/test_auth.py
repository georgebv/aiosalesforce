import textwrap
import time

import httpx
import pytest
import respx

from aiosalesforce.auth import SoapLogin
from aiosalesforce.events import EventBus
from aiosalesforce.exceptions import AuthenticationError


class TestAuth:
    async def test_soap_login(
        self,
        httpx_client: httpx.AsyncClient,
        httpx_mock_router: respx.MockRouter,
    ):
        base_url = "https://example.my.salesforce.com"
        api_version = "60.0"
        expected_session_id = "VERY_LONG_SECRET_STRING"

        # Mock the login request
        soap_response = f"""
        <?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope
            xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns="urn:partner.soap.sforce.com"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <soapenv:Body>
                <loginResponse>
                    <result>
                        <metadataServerUrl>{base_url}/services/Soap/m/{api_version}/00D58000000arpq</metadataServerUrl>
                        <passwordExpired>false</passwordExpired>
                        <sandbox>false</sandbox>
                        <serverUrl>{base_url}/services/Soap/u/{api_version}/00D58000000arpq</serverUrl>
                        <sessionId>{expected_session_id}</sessionId>
                        <userId>00558000000yFyDAAU</userId>
                        <userInfo>
                            <accessibilityMode>false</accessibilityMode>
                            <chatterExternal>false</chatterExternal>
                            <currencySymbol>$</currencySymbol>
                            <orgAttachmentFileSizeLimit>26214400</orgAttachmentFileSizeLimit>
                            <orgDefaultCurrencyIsoCode>USD</orgDefaultCurrencyIsoCode>
                            <orgDefaultCurrencyLocale>en_US_USD</orgDefaultCurrencyLocale>
                            <orgDisallowHtmlAttachments>false</orgDisallowHtmlAttachments>
                            <orgHasPersonAccounts>false</orgHasPersonAccounts>
                            <organizationId>00D58000000arpqEAA</organizationId>
                            <organizationMultiCurrency>false</organizationMultiCurrency>
                            <organizationName>Example Org</organizationName>
                            <profileId>00e58000000wYTOAA2</profileId>
                            <roleId xsi:nil="true"/>
                            <sessionSecondsValid>7200</sessionSecondsValid>
                            <userDefaultCurrencyIsoCode xsi:nil="true"/>
                            <userEmail>demo@example.com</userEmail>
                            <userFullName>John Doe</userFullName>
                            <userId>00558000000yFyDAAU</userId>
                            <userLanguage>en_US</userLanguage>
                            <userLocale>en_US</userLocale>
                            <userName>demo@example.com</userName>
                            <userTimeZone>America/Los Angeles</userTimeZone>
                            <userType>Standard</userType>
                            <userUiSkin>Theme3</userUiSkin>
                        </userInfo>
                    </result>
                </loginResponse>
            </soapenv:Body>
        </soapenv:Envelope>
        """
        login_route = httpx_mock_router.post(
            f"{base_url}/services/Soap/u/{api_version}",
        )
        login_route.return_value = httpx.Response(
            status_code=200,
            content=textwrap.dedent(soap_response).strip().encode("utf-8"),
        )

        # Perform the login
        auth = SoapLogin(
            username="username",
            password="password",  # noqa: S106
            security_token="security_token",  # noqa: S106
        )
        received_session_id = await auth.get_access_token(
            client=httpx_client,
            base_url=base_url,
            version=api_version,
            event_bus=EventBus(),
        )
        assert received_session_id == expected_session_id
        assert not auth.expired
        assert auth._expiration_time is not None and auth._expiration_time > time.time()

    @pytest.mark.parametrize(
        "reason, provide_error_message",
        [
            ("invalid credentials", False),
            ("invalid credentials", True),
            ("invalid response", None),
        ],
    )
    async def test_soap_login_failure(
        self,
        reason: str,
        provide_error_message: bool | None,
        httpx_client: httpx.AsyncClient,
        httpx_mock_router: respx.MockRouter,
    ):
        base_url = "https://example.my.salesforce.com"
        api_version = "60.0"
        error_message = "Invalid credentials"

        # Mock the login request
        login_route = httpx_mock_router.post(
            f"{base_url}/services/Soap/u/{api_version}",
        )
        if reason == "invalid credentials":
            if provide_error_message:
                regex_pattern = rf"^SOAP login failed: {error_message}$"
                login_route.return_value = httpx.Response(
                    status_code=401,
                    content=(
                        f"<sf:exceptionMessage>{error_message}</sf:exceptionMessage>"
                    ).encode("utf-8"),
                )
            else:
                regex_pattern = r"^SOAP login failed: $"
                login_route.return_value = httpx.Response(status_code=401)
        else:
            regex_pattern = (
                r"^Failed to parse sessionId from the SOAP response: invalid$"
            )
            login_route.return_value = httpx.Response(
                status_code=200,
                content=b"invalid",
            )

        # Perform the login
        auth = SoapLogin(
            username="username",
            password="password",  # noqa: S106
            security_token="security_token",  # noqa: S106
        )
        with pytest.raises(AuthenticationError, match=regex_pattern):
            await auth.get_access_token(
                client=httpx_client,
                base_url=base_url,
                version=api_version,
                event_bus=EventBus(),
            )
