import re
import textwrap

from typing import AsyncGenerator, Generator

import httpx
import pytest
import respx


@pytest.fixture(scope="function")
def config() -> dict[str, str]:
    """Configuration shared across tests."""
    return {
        "base_url": "https://example.my.salesforce.com",
        "api_version": "60.0",
        "username": "user@example.org",
        "password": "super-secret-password",
        "security_token": "super-secret-security-token",
    }


@pytest.fixture(scope="function", autouse=True)
def httpx_mock_router() -> Generator[respx.MockRouter, None, None]:
    """Router used to intercept and mock httpx requests."""
    with respx.mock(
        assert_all_called=False,
        assert_all_mocked=True,
    ) as respx_mock:
        yield respx_mock


@pytest.fixture(scope="function")
async def httpx_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture(scope="function")
async def mock_soap_login(
    config: dict[str, str],
    httpx_mock_router: respx.MockRouter,
) -> AsyncGenerator[str, None]:
    session_id = "SUPER-SECRET-SESSION-ID"

    soap_response_on_success = f"""
    <?xml version="1.0" encoding="UTF-8"?>
    <soapenv:Envelope
        xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns="urn:partner.soap.sforce.com"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <soapenv:Body>
            <loginResponse>
                <result>
                    <metadataServerUrl>{config['base_url']}/services/Soap/m/{config['api_version']}/00D58000000arpq</metadataServerUrl>
                    <passwordExpired>false</passwordExpired>
                    <sandbox>false</sandbox>
                    <serverUrl>{config['base_url']}/services/Soap/u/{config['api_version']}/00D58000000arpq</serverUrl>
                    <sessionId>{session_id}</sessionId>
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

    soap_response_on_invalid_credentials = """
    <?xml version="1.0" encoding="UTF-8"?>
    <soapenv:Envelope
        xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
        xmlns:sf="urn:fault.partner.soap.sforce.com"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <soapenv:Body>
            <soapenv:Fault>
                <faultcode>sf:INVALID_LOGIN</faultcode>
                <faultstring>INVALID_LOGIN: Invalid username, password, security token; or user locked out.</faultstring>
                <detail>
                    <sf:LoginFault xsi:type="sf:LoginFault">
                        <sf:exceptionCode>INVALID_LOGIN</sf:exceptionCode>
                        <sf:exceptionMessage>Invalid username, password, security token; or user locked out.</sf:exceptionMessage>
                    </sf:LoginFault>
                </detail>
            </soapenv:Fault>
        </soapenv:Body>
    </soapenv:Envelope>
    """

    def validate_soap_login_request(request: httpx.Request) -> httpx.Response:
        soap_xml_payload = request.content.decode("utf-8")
        try:
            match_ = re.search(r"<n1:username>(.+)<\/n1:username>", soap_xml_payload)
            assert match_ is not None
            assert str(match_.groups()[0]) == config["username"]
            match_ = re.search(r"<n1:password>(.+)<\/n1:password>", soap_xml_payload)
            assert match_ is not None
            assert (
                str(match_.groups()[0])
                == f"{config['password']}{config['security_token']}"
            )
        except AssertionError:
            return httpx.Response(
                status_code=401,
                content=textwrap.dedent(soap_response_on_invalid_credentials)
                .strip()
                .encode("utf-8"),
            )
        return httpx.Response(
            status_code=200,
            content=textwrap.dedent(soap_response_on_success).strip().encode("utf-8"),
        )

    httpx_mock_router.post(
        f"{config['base_url']}/services/Soap/u/{config['api_version']}",
    ).mock(side_effect=validate_soap_login_request)

    yield session_id
