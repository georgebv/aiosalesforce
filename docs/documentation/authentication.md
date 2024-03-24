## Overview

Before you can make requests to the Salesforce API, you need to authenticate
In `aiosalesforce` authentication is a dependency you provide
to the [`Salesforce` client](./client.md).
The typical usage pattern looks like this
(using the [`SoapLogin`](#soap-login) authentication method as an example):

```python
import asyncio

from aiosalesforce import Salesforce, SoapLogin
from httpx import AsyncClient

auth = SoapLogin(
    username="username",
    password="password",
    security_token="security-token",
)


async def main():
    async with AsyncClient() as client:
        salesforce = Salesforce(
            client=client,
            base_url="https://your-instance.my.salesforce.com",
            auth=auth,
        )


if __name__ == "__main__":
    asyncio.run(main())
```

!!! tip "Best Practice"

    Always declare your authentication instance as a global variable and reuse it
    across your application. You can have many clients using the same authentication
    instance. By doing so, you can avoid unnecessary re-authentication and
    reduce the number of requests to the Salesforce API.

!!! warning Warning

    Keep your credentials safe and never hardcode them in your application.
    Use third-party libraries to acquire credentials from environment variables,
    configuration files, or secret management services during runtime.

## Built-in Authentication Methods

### SOAP Login

Authenticate using `username`, `password`, and `security token`.

```python
from aiosalesforce.auth import SoapLogin

auth = SoapLogin(
    username="username",
    password="password",
    security_token="security-token",
)
```

??? question "Where do I find my security token?"

    Security token can be obtained from the Salesforce UI by navigating to
    `Settings` > `Personal Information` > `Reset My Security Token`, clicking the
    `Reset Security Token` button, and then checking your email for the new token.

    :warning: When you update security token make sure to update all applications
    which are using the old token for this user.

### Client Credentials Flow

Authenticate using a connected app for server-to-server integrations.

```python
from aiosalesforce.auth import ClientCredentials

auth = ClientCredentials(
    client_id="client-id",
    client_secret="client-secret",
)
```

## Custom Authentication

You can create a custom authentication class by subclassing the
[`Auth`](../api-reference/auth.md#aiosalesforce.auth.Auth) class.

You must implement the `_acquire_new_access_token` method which is responsible
for acquiring a new access token. This doesn't mean that you have to acquire a new
access token from Salesforce - only that calling this method should return a new
access token each time it is called. Examples of behavior:

- Fetch new token directly from Salesforce
- Fetch token from some service (e.g., centralized authentication service)
- Fetch token from cache and, if cache is empty/expired, fetch new token from Salesforce
  and update cache

You can optionally implement the `_refresh_access_token` method which is responsible
for refreshing the access token. If you don't implement this method, the
`_acquire_new_access_token` method will be called instead.

You can implement expiration mechanism by implementing the `expired` property in your
custom authentication class. This property should return a boolean value indicating
whether the access token has expired. Auth class will call the `_refresh_access_token`
method when the access token expires. By default the `expired` property always returns
`False`. You can declare whatever class attributes you need to implement the expiration
mechanism.

!!! warning "Warning"

    When implementing custom authentication, you are responsible for emitting
    [`RequestEvent`](../api-reference/events.md#aiosalesforce.events.RequestEvent)
    and
    [`ResponseEvent`](../api-reference/events.md#aiosalesforce.events.ResponseEvent)
    events using
    [`client.event_bus.publish_event`](../api-reference/events.md#aiosalesforce.events.EventBus.publish_event)
    method.

```python
from aiosalesforce.auth import Auth


class MyAuth(Auth):
    def __init__(
        self,
        # Your custom arguments
        ...
    ):
        super().__init__()
        # Your custom initialization logic
        ...

    async def _acquire_new_access_token(self, client: Salesforce) -> str:
        # Your custom logic to acquire new access token
        ...

    async def _refresh_access_token(self, client: Salesforce) -> str:
        # Your custom logic to refresh access token
        ...

    @property
    def expired(self) -> bool:
        # Your custom logic to check if access token has expired
        ...
```

!!! warning "Warning"

    You must follow these rules when making HTTP requests from your custom
    authentication class:

    - Requets to Salesforce must be made using the
    [`client.retry_policy.send_request_with_retries`](../api-reference/retries.md#aiosalesforce.retries.policy.RetryContext.send_request_with_retries) method
    - Requests to other services must be made using the `client.httpx_client` attribute

    **Under no circumstances** should you make HTTP
    requests using the `client.request` method - this method calls authentication
    methods and can lead to infinite recursion.

You can request any arguments in the `__init__` method of your custom authentication
class. The `__init__` method must call the `super().__init__()` method to initialize
the base class. After that, you can declare whatever attributes and methods you need.
