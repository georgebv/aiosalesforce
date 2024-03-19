## Overview

Before you can make requests to the Salesforce API, you need to authenticate
In `aiosalesforce` authentication is a dependency you provide
to the [`Salesforce` client](/aiosalesforce/documentation/client).
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
[`Auth`](/aiosalesforce/api-reference/auth/#aiosalesforce.auth.Auth)
class and implementing the `_acquire_new_access_token` and
(optionally) the `_refresh_access_token` methods.

When implementing custom authentication, you are responsible for emitting appropriate
events using the provided
[`EventBus`](/aiosalesforce/api-reference/events/#aiosalesforce.events.EventBus)
instance.

```python
from aiosalesforce.auth import Auth


class MyAuth(Auth):
    def __init__(self):
        super().__init__()
        # Your custom initialization logic

    async def _acquire_new_access_token(
        self,
        client: AsyncClient,
        base_url: str,
        version: str,
        event_bus: EventBus,
    ) -> str:
        # Your custom logic to acquire new access token
        ...

    async def _refresh_access_token(
        self,
        client: AsyncClient,
        base_url: str,
        version: str,
        event_bus: EventBus,
    ) -> str:
        # Your custom logic to refresh access token
        ...
```

You can request any arguments in the `__init__` method of your custom authentication
class. The `__init__` method should call the `super().__init__()` method to initialize
the base class. After that, you can declare whatever attributes and methods you need.

The `_acquire_new_access_token` method is required.

The `_refresh_access_token` method is optional. By default it calls the
`_acquire_new_access_token` method (meaning, you acquire a new access token every time
the old one expires or becomes invalid).
