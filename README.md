<p align="center" style="font-size:40px; margin:0px 10px 0px 10px">
    <em>aiosalesforce</em>
</p>
<p align="center">
    <em>Python client for the Salesforce REST API</em>
</p>
<p align="center">
<a href="https://pypi.org/project/aiosalesforce" target="_blank">
    <img src="https://badge.fury.io/py/aiosalesforce.svg" alt="PyPI Package">
</a>
</p>

# About

**Documentation:** https://georgebv.github.io/aiosalesforce/

**License:** [MIT](https://opensource.org/licenses/MIT)

**aiosalesforce** is an asynchronous Python client for the Salesforce REST API.

# Installation

Get the latest version from PyPI:

```shell
pip install aiosalesforce
```

# Quickstart

```python
import asyncio

from aiosalesforce import Salesforce
from aiosalesforce.auth import SoapLogin
from httpx import AsyncClient

auth = SoapLogin(
    username="your-username",
    password="your-password",
    security_token="your-security-token",
)

async def main():
    async with AsyncClient() as client:
        salesforce = Salesforce(
            client,
            base_url="https://your-instance.my.salesforce.com",
            auth=auth,
        )
        async for record in salesforce.query("SELECT Id, Name FROM Account"):
            print(record)


if __name__ == "__main__":
    asyncio.run(main())
```
