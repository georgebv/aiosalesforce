import urllib.parse

import httpx
import respx

from aiosalesforce import Salesforce
from aiosalesforce.utils import json_dumps


async def test_create(
    salesforce: Salesforce,
    httpx_mock_router: respx.MockRouter,
) -> None:
    data = {"FirstName": "John", "LastName": "Doe"}
    obj_id = "0015800000K7f2PAAR"

    def side_effect(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.content == json_dumps(data)
        return httpx.Response(200, json={"id": obj_id, "errors": [], "success": True})

    httpx_mock_router.post(f"{salesforce.sobject.base_url}/Account").mock(
        side_effect=side_effect
    )
    response = await salesforce.sobject.create("Account", data=data)
    assert response == obj_id


async def test_get_by_id(
    salesforce: Salesforce,
    httpx_mock_router: respx.MockRouter,
) -> None:
    obj_id = "0015800000K7f2PAAR"
    data = {"Id": obj_id, "FirstName": "John", "LastName": "Doe"}

    httpx_mock_router.get(f"{salesforce.sobject.base_url}/Account/{obj_id}").mock(
        return_value=httpx.Response(200, json=data)
    )

    response = await salesforce.sobject.get("Account", obj_id)
    assert response == data


async def test_get_by_external_id(
    salesforce: Salesforce,
    httpx_mock_router: respx.MockRouter,
) -> None:
    external_id = "123"
    external_id_field = "ESSN__c"
    data = {
        "Id": "0015800000K7f2PAAR",
        "FirstName": "John",
        "LastName": "Doe",
        external_id_field: external_id,
    }

    httpx_mock_router.get(
        f"{salesforce.sobject.base_url}/Account/{external_id_field}/{external_id}"
    ).mock(return_value=httpx.Response(200, json=data))

    response = await salesforce.sobject.get(
        "Account",
        external_id,
        external_id_field=external_id_field,
    )
    assert response == data


async def test_get_subset_of_fields(
    salesforce: Salesforce,
    httpx_mock_router: respx.MockRouter,
) -> None:
    obj_id = "0015800000K7f2PAAR"
    fields = ["LastName", "Email"]
    data = {
        "Id": obj_id,
        "FirstName": "John",
        "LastName": "Doe",
        "Email": "jdoe@example.com",
    }

    def side_effect(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.query.decode("utf-8") == urllib.parse.quote(
            f"fields={','.join(fields)}", safe="="
        )
        return httpx.Response(200, json={k: v for k, v in data.items() if k in fields})

    httpx_mock_router.get(f"{salesforce.sobject.base_url}/Account/{obj_id}").mock(
        side_effect=side_effect
    )

    response = await salesforce.sobject.get("Account", obj_id, fields=fields)
    assert response == {k: v for k, v in data.items() if k in fields}, response


async def test_update(
    salesforce: Salesforce,
    httpx_mock_router: respx.MockRouter,
) -> None:
    obj_id = "0015800000K7f2PAAR"
    data = {"FirstName": "John", "LastName": "Doe"}

    def side_effect(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert request.content == json_dumps(data)
        return httpx.Response(204)

    httpx_mock_router.patch(f"{salesforce.sobject.base_url}/Account/{obj_id}").mock(
        side_effect=side_effect
    )

    await salesforce.sobject.update("Account", obj_id, data=data)


async def test_delete(
    salesforce: Salesforce,
    httpx_mock_router: respx.MockRouter,
) -> None:
    obj_id = "0015800000K7f2PAAR"

    class SideEffect:
        def __init__(self) -> None:
            self.called = False

        def __call__(self, request: httpx.Request) -> httpx.Response:
            assert request.method == "DELETE"
            self.called = True
            return httpx.Response(204)

    side_effect = SideEffect()

    httpx_mock_router.delete(f"{salesforce.sobject.base_url}/Account/{obj_id}").mock(
        side_effect=side_effect
    )
    await salesforce.sobject.delete("Account", obj_id)
    assert side_effect.called


async def test_delete_by_external_id(
    salesforce: Salesforce,
    httpx_mock_router: respx.MockRouter,
) -> None:
    external_id = "123"
    external_id_field = "ESSN__c"

    class SideEffect:
        def __init__(self) -> None:
            self.called = False

        def __call__(self, request: httpx.Request) -> httpx.Response:
            assert request.method == "DELETE"
            self.called = True
            return httpx.Response(204)

    side_effect = SideEffect()

    httpx_mock_router.delete(
        f"{salesforce.sobject.base_url}/Account/{external_id_field}/{external_id}"
    ).mock(side_effect=side_effect)
    await salesforce.sobject.delete(
        "Account",
        external_id,
        external_id_field=external_id_field,
    )
    assert side_effect.called
