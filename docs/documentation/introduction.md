## Overview

`aiosalesforce` is an asynchronous Python client for the Salesforce API. It allows
performing the following operations against Salesforce:

- Authentication
- CRUD operations on Salesforce objects (also known as sobjects)
- Executing SOQL queries
- Bulk data operations

The general pattern for using `aiosalesforce` is to create an authentication
instance and pass it to the [`Salesforce` client](../documentation/client.md).
The client is then used to make requests to the Salesforce APIs.

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
        contact = salesforce.sobject.get("Contact", "0033h00000KzZ3AAAV")
        print(contact)


if __name__ == "__main__":
    asyncio.run(main())
```

!!! note "Note"

    Since `aiosalesforce` is an asynchronous library, you need to define your functions
    using `async def` and use the `await` keyword when calling asynchronous methods.
    In subsequent sections of this documentation the definition of the asynchronous
    function is often ommited for brevity and it is assumed that everything
    is written inside one.

## Recommended reading

As you are using `aiosalesforce`, you should familiarize yourself with the
Python's [`asyncio` library](https://docs.python.org/3/library/asyncio.html).

Relevant Salesforce API documentation:

- [Salesforce APIs](https://developer.salesforce.com/developer-centers/integration-apis)
- [Salesforce REST API](https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/intro_rest.htm)
- [Salesforce Bulk API](https://developer.salesforce.com/docs/atlas.en-us.api_asynch.meta/api_asynch/asynch_api_intro.htm)
