Asynchronous Python client for the Salesforce REST API.

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
