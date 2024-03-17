## Overview

When working with `aiosalesforce` you will always start by creating a `Salesforce`
client. The minimum required parameters are:

- `client` - an instance of `httpx.AsyncClient` used to make HTTP requests
- `base_url` - URL of your Salesforce instance. Examples of valid URLs are:
- `auth` - you need to provide credentials for your Salesforce instance

```python
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

        # Your code here
        ...
```

!!! note "Note"

    Base URL can be any URL that points to your Salesforce instance login page,
    which ends with `.my.salesforce.com`. Depending on the type of your Salesforce
    instance, the URL will have this structure:

    - Production : `https://[MyDomainName].my.salesforce.com`
    - Sandbox : `https://[MyDomainName]-[SandboxName].sandbox.my.salesforce.com`
    - Developer org : `https://[MyDomainName].develop.my.salesforce.com`

    Everything after `.my.salesforce.com` is ignored, so you can pass any URL
    that begins with one of the patterns above. For example, a URL like
    `https://acme.my.salesforce.com/any/path?or=query` would be perfectly valid.

You can specify the version of the Salesforce API you want to use via the `version`
parameter. The default value is the latest version at the time of the library release.

```python
salesforce = Salesforce(
    client=client,
    base_url="https://your-instance.my.salesforce.com",
    auth=auth,
    version="52.0",
)
```

!!! warning "Warning"

    Version must be a string in the format of `XX.0` (e.g., `60.0`).
    Value like `v60.0` is not valid and will result in an error
    when using the client later.

## Event Hooks

!!! info "WIP"

    :construction: Work in progress

## Retrying Requests

!!! info "WIP"

    :construction: Work in progress

## Concurrency Limit

To limit the number of simultaneous requests to the Salesforce API, you can use
the `concurrency_limit` parameter. Salesforce doesn't have a limit on the number
of concurrent requests for short operations (less than 20 seconds), but generally
it's a good practice to limit the number of simultaneous requests to avoid
congestion-related issues.

By default, the `concurrency_limit` is set to `100`. You can change it by passing
a different value when instantiating the `Salesforce` client.

```python
salesforce = Salesforce(
    client=client,
    base_url="https://your-instance.my.salesforce.com",
    auth=auth,
    concurrency_limit=25,
)
```
