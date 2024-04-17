---
hide:
  - navigation
---

<style>
.md-content .md-typeset h1 { display: none; }
</style>

<p align="center" style="font-size:40px; margin:0px 10px 0px 10px">
    <em>⚡ aiosalesforce ⚡</em>
</p>
<p align="center">
    <em>Asynchronous Python client for Salesforce APIs</em>
</p>
<p align="center">
<a href="https://github.com/georgebv/aiosalesforce/actions/workflows/test.yml" target="_blank">
    <img src="https://github.com/georgebv/aiosalesforce/actions/workflows/test.yml/badge.svg?event=pull_request" alt="Test">
</a>
<a href="https://codecov.io/gh/georgebv/aiosalesforce" target="_blank">
    <img src="https://codecov.io/gh/georgebv/aiosalesforce/graph/badge.svg?token=KVMS7YVODO" alt="Coverage"/>
</a>
<a href="https://pypi.org/project/aiosalesforce" target="_blank">
    <img src="https://badge.fury.io/py/aiosalesforce.svg" alt="PyPI Package">
</a>
</p>

---

`aiosalesforce` is a modern, production-ready asynchronous Python client
for Salesforce APIs.
It is built on top of the `httpx` library and provides a simple and intuitive API
for interacting with Salesforce's APIs (such as REST and Bulk).

- **Fast:** designed from the ground up to be fully asynchronous :rocket:
- **Resilient:** flexible and robust retrying configuration :gear:
- **Fully typed:** every part of the library is fully typed and annotated :label:
- **Intuitive:** API follows naming conventions of Salesforce's APIs while
  staying idiomatic to Python :snake:
- **Salesforce first:** built with years of experience working with the Salesforce API
  it is configured to work out of the box and incorporates best practices and
  latest Salesforce API features :cloud:
- **Track your API usage:** built-in support for tracking Salesforce API usage
  :chart_with_upwards_trend:

---

## Requirements

`aiosalesforce` depends on:

- Python 3.11+
- [httpx](https://github.com/encode/httpx)
- [orjson](https://github.com/ijl/orjson)

Optional dependencies:

- [PyJWT](https://github.com/jpadilla/pyjwt)
- [cryptography](https://github.com/pyca/cryptography)

## Installation

```shell
pip install aiosalesforce
```

To use the JWT Bearer Flow authentication install with the `jwt` extra:

```shell
pip install aiosalesforce[jwt]
```

## Demo

Follow the steps below to create a simple script that authenticates against Salesforce
and performs basic operations such as creating a record, reading a record, and executing
a SOQL query.

### Authenticate

First, we need to authenticate against Salesforce. For this example,
we will use the `SoapLogin` authentication method.

```python linenums="1"
import asyncio

from aiosalesforce import Salesforce, SoapLogin
from httpx import AsyncClient

auth = SoapLogin(
    username="your-username",
    password="your-password",
    security_token="your-security-token",
)
```

### Create Salesforce client

Next, we create a new Salesforce client using the `Salesforce` class. Notice
two additional parameters:

- `client` - an instance of `httpx.AsyncClient` used to make HTTP requests
- `base_url` - the base URL of your Salesforce instance

Since we are writing an asynchronous application, we need to wrap everything
in an `async` function. Subsequent sections are written as a continuation of
the `main` function.

```python linenums="11"
async def main():
    async with AsyncClient() as client:
        salesforce = Salesforce(
            client,
            base_url="https://your-instance.my.salesforce.com",
            auth=auth,
        )
```

### Create a record

Let's create a new Contact in Salesforce. To do this, we will use the `create` method
of the `sobject` api:

```python linenums="18"
contact_id = await salesforce.sobject.create(
    "Contact",
    {
        "FirstName": "John",
        "LastName": "Doe",
        "Email": "john.doe@example.com",
    },
)
print(f"Created Contact with ID: {contact_id}")
```

This will output something like:

```shell
Created Contact with ID: 0035e00000Bv2tPAAR
```

### Read a record

To read a record by ID, we will use the `get` method of the `sobject` api:

```python linenums="27"
contact = await salesforce.sobject.get("Contact", contact_id)
print(contact)
```

This will return a dictionary with the Contact details (truncated for brevity):

```shell
{
    "Id": "0035e00000Bv2tPAAR",
    "FirstName": "John",
    "LastName": "Doe",
    "Email": "john.doe@example.com",
    ...
}
```

### Execute a SOQL query

Finally, let's execute a SOQL query to retrieve all Contacts:

```python linenums="29"
async for record in salesforce.query("SELECT Id, Name FROM Contact"):
    print(record)
```

This will create an asynchronous generator yielding records as a dictionaries:

```shell
{"Id": "0035e00000Bv2tPAAR", "Name": "John Doe"}
{"Id": "0035e00000Bv2tPAAQ", "Name": "Jane Doe"}
{"Id": "0035e00000Bv2tPAAP", "Name": "Alice Smith"}
...
```

### Putting it all together

Putting everything you learned above together, a simple script may look like this:

```python linenums="1"
import asyncio

from aiosalesforce import Salesforce
from aiosalesforce.auth import SoapLogin
from httpx import AsyncClient

# Reuse authentication session across multiple clients (refreshes automagically)
auth = SoapLogin(
    username="your-username",
    password="your-password",
    security_token="your-security-token",
)

async def main():
    async with AsyncClient() as client:
        # Create a Salesforce client
        salesforce = Salesforce(
            client,
            base_url="https://your-instance.my.salesforce.com",
            auth=auth,
        )

        # Create a new Contact
        contact_id = await salesforce.sobject.create(
            "Contact",
            {
                "FirstName": "John",
                "LastName": "Doe",
                "Email": "john.doe@example.com",
            },
        )
        print(f"Created Contact with ID: {contact_id}")

        # Read Contact by ID
        contact = await salesforce.sobject.get("Contact", contact_id)
        print(contact)

        # Execute a SOQL query
        async for record in salesforce.query("SELECT Id, Name FROM Contact"):
            print(record)


if __name__ == "__main__":
    asyncio.run(main())
```

## License

This project is licensed under the terms of the MIT license.
