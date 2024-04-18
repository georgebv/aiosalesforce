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

| Method                                              | Connected App      | Server-to-Server   |
| --------------------------------------------------- | ------------------ | ------------------ |
| [SOAP Login](#soap-login)                           | :x:                | :heavy_check_mark: |
| [Client Credentials Flow](#client-credentials-flow) | :heavy_check_mark: | :heavy_check_mark: |
| [JWT Bearer Flow](#jwt-bearer-flow)                 | :heavy_check_mark: | :heavy_check_mark: |

### SOAP Login

Authenticate using `username`, `password`, and `security token`.

```python
from aiosalesforce import SoapLogin

auth = SoapLogin(
    username="username",
    password="password",
    security_token="security-token",
)
```

??? question "Where to find security token?"

    Security token can be obtained from the Salesforce UI by navigating to
    `Settings` > `Personal Information` > `Reset My Security Token`, clicking the
    `Reset Security Token` button, and then checking your email for the new token.

    :warning: When you update security token make sure to update all applications
    which are using the old token for this user.

### Client Credentials Flow

Authenticate using a connected app for server-to-server integrations.

```python
from aiosalesforce import ClientCredentials

auth = ClientCredentials(
    client_id="client-id",
    client_secret="client-secret",
)
```

??? question "How to create and configure a connected app?"

    First, you need to creat a connected app in Salesforce:

    1. Navigate to `Setup` > `Apps` > `App Manager` and click `New Connected App`
    2. Check `Enable OAuth Settings`
    3. Check `Enable for Device Flow`
    4. Check `Enable Client Credentials Flow`
    5. Select necessary scopes (generally, it's `Full access (full)`)

    Next, you need to enable the Client Credentials Flow for the connected app:

    1. Navigate to `Setup` > `Apps` > `App Manager` and find your connected app
    2. Click `Manage` and then `Edit Policies`
    3. Select `All users may self-authorize` in the `Permitted Users` section
    4. Select a user on behalf of which the connected app will authenticate and
       perform actions in the `Run As` field of the `Client Credentials Flow` section
    5. (optional) Set the `Timeout Value` field to whichever value is appropriate in
       your case
    6. Click `Save`

    Finally, you need to retrieve the `client_id` and `client_secret` for the connected
    app:

    1. Navigate to `Setup` > `Apps` > `App Manager` and find your connected app
    2. Click `View` and then click `Manage Consumer Details`
    3. Copy the `Consumer Key` (`client_id`) and `Consumer Secret` (`client_secret`)
       values. If you need to reset your credentials, you do it here as well.

If you configured timeout for the access token when creating the connected app,
you can use the `timeout` parameter to specify duration in seconds after which
the access token will be automatically refreshed. This way you can save a retry API
call which would normally be retried due to 401 (token expired) by pre-emptively
refreshing the token.

```python
auth = ClientCredentials(
    client_id="client-id",
    client_secret="client-secret",
    timeout=900,  # 15 minutes
)
```

### JWT Bearer Flow

Authenticate using connected app and RSA private key.

```python
from aiosalesforce import JwtBearerFlow

auth = JwtBearerFlow(
    client_id="client-id",
    username="username",
    private_key="path/to/private-key.pem",
)
```

Where:

- `client_id` is the connected app's consumer key
- `username` is the username of the user on behalf of which the connected app will
  authenticate and perform actions
- `private_key` is the path to the RSA private key file (must be in PEM format)

You can optionally provide `private_key_passphrase` (if the private key is encrypted)
and `timeout` (if you set connected app timeout) parameters.

!!! warning "Warning"

    The JWT Bearer Flow requires `PyJWT` and `cryptography` libraries to be installed.
    You can install them using `pip install aiosalesforce[jwt]`.

??? question "How to configure a connected app to use JWT Bearer Flow?"

    Follow the same steps as for the
    [Client Credentials Flow](#client-credentials-flow)
    to create a connected app.

    Create certificate and download certificate:

    1. Navitate to `Setup` > `Security` > `Certificate and Key Management`
    2. Click `Create Self-Signed Certificate`, give it label, name, select key size,
       check `Exportable Private Key`, and click `Save`
    3. Navigate back to `Certificate and Key Management` and click on
       `Export to Keystore` (password needs to contain special characters, otherwise
       Salesforce will tell you that you don't have sufficient privileges). Password
       is needed only to subsequently extract the private key so you can discard it
       after you are done with the process.
    4. Click `Export` and save it locally (e.g. `certificate.crt`)

    Extract private key:

    1. Run the following command to extract the private key from the keystore:
       ```bash
       keytool -importkeystore -srckeystore certificate.crt -destkeystore \
       certificate.p12 -deststoretype PKCS12
       ```
       Enter password when prompted
    2. Run the following command to extract the private key from the PKCS12 file:
       ```bash
       openssl pkcs12 -in certificate.p12 -nocerts -nodes -out private-key.pem
       ```
       The `private-key.pem` file is your RSA private key

    Connected app needs additional configuration to use JWT Bearer Flow:

    1. Navigate to `Setup` > `Apps` > `App Manager` and find your connected app
    2. Click `Manage` and then click `Edit Policies`
    3. Under `Permitted Users`, select `Admin approved users are pre-authorized`
    4. `Save`
    5. Navigate to `Setup` > `Apps` > `App Manager`, find your connected app,
       and click `Edit`
    6. Check `Use digital signatures` and upload the certificate (`certificate.crt`)
       you created and downloaded from Salesforce earlier
    7. `Save`

    Update profile assigned to user(s) configured for this connected app:

    1. Navigate to `Setup` > `Users` > `Profiles`
    2. Find profile assigned to the user (or create a new one) and click `Edit`
    3. Enable `Connected App Access` for the connected app you created

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

!!! info "Information"

    When implementing custom authentication, you are responsible for emitting
    [`RequestEvent`](../api-reference/events.md#aiosalesforce.events.RequestEvent)
    and
    [`ResponseEvent`](../api-reference/events.md#aiosalesforce.events.ResponseEvent)
    events using
    [`client.event_bus.publish_event`](../api-reference/events.md#aiosalesforce.events.EventBus.publish_event)
    method.
    If you don't do this, any client-side logic built around events (e.g., logging or
    metrics) will not receive request/response information related to authentication.

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
        super().expired
        # Your custom logic to check if access token has expired
        ...
```

!!! warning "Warning"

    You must follow these rules when making HTTP requests from your custom
    authentication class:

    - Requets to Salesforce must be made using the
      [`client.retry_policy.send_request_with_retries`](../api-reference/retries.md#aiosalesforce.retries.policy.RetryContext.send_request_with_retries) method
    - Requests to other services must be made using the
      [`client.httpx_client`](../api-reference/client.md) attribute

    **Under no circumstances** should you make HTTP
    requests using the
    [`client.request`](../api-reference/client.md#aiosalesforce.client.Salesforce.request)
    method - this method calls authentication methods
    and can lead to infinite recursion.

You can request any arguments in the `__init__` method of your custom authentication
class. The `__init__` method must call the `super().__init__()` method to initialize
the base class. After that, you can declare whatever attributes and methods you need.
