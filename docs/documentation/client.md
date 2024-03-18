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
    Value like `v60.0` is not valid and will result in an error.

## Event Hooks

When you use the `Salesforce` client, it emits certain events to which you can
subscribe. This allows you to perform custom actions at different stages of the
request-response lifecycle. For example, you can log requests and responses, or
track usage of the Salesforce API within your application.

You subscribe to events by declaring a function or a coroutine that will be
called when an event is emitted and then providing that function to the client.
The function will receive an event object as the only argument.
The event object will contain information about the event.

```python
async def callback(event):
    # Do something with the event
    ...
```

!!! note "Note"

    When subscribing to events, your function will receive all events emitted by the
    `Salesforce` client. You are responsible for filtering out events you are
    not interested in.

!!! warning "Warning"

    Only use `async def` if your callback function is asynchronous. If it contains
    synchronous network calls, it will slow down the entire application by blocking
    the event loop. If you need to perform synchronous operations, declare your
    function as a regular function using `def` - such functions will be run in
    a separate thread to avoid blocking the event loop.

An example below shows how you can use event hooks to keep track of the number
of requests made to the Salesforce API.

```python
from aiosalesforce import RestApiCallConsumptionEvent


def track_api_usage(event: RestApiCallConsumptionEvent):
    match event:
        case RestApiCallConsumptionEvent():
            # Do whatever you need to do with the event
            # For example, write to a metrics service (e.g., AWS CloudWatch)
            ...
        case _:
            # Do nothing for other events
            pass

salesforce = Salesforce(
    ...,
    event_hooks=[track_api_usage],
)
```

An alternative way of subscribing to events is to use the `subscribe_callback` method
of the `event_loop` attribute of the `Salesforce` client:

```python
salesforce.event_loop.subscribe_callback(track_api_usage)
```

Similarly, you can unsubscribe a callback by using the `unsubscribe_callback` method:

```python
salesforce.event_loop.unsubscribe_callback(track_api_usage)
```

When you subscribe multiple callbacks to the client they will be called concurrently.
This means that the order in which they are called is not guaranteed. Your callbacks
can be synchronous, asynchronous, or a mix of both - `aiosalesforce` knows what to do
in each case.

### Events

All events have the `type` attribute.

| Event                          | `type`                       | When emitted                                                            | Attributes                       |
| ------------------------------ | ---------------------------- | ----------------------------------------------------------------------- | -------------------------------- |
| `RequestEvent`                 | `request`                    | Before making a request to the Salesforce API                           | `request`                        |
| `RetryEvent`                   | `retry`                      | Before request is retried                                               | `request`, `response` (optional) |
| `ResponseEvent`                | `response`                   | After an OK (status code < 300) response is received                    | `response`                       |
| `RestApiCallConsumptionEvent`  | `rest_api_call_consumption`  | When a Salesforce API call is consumed (includes unsuccessful requests) | `response`                       |
| `BulkApiBatchConsumptionEvent` | `bulk_api_batch_consumption` | When a Bulk API (v1 or v2) batch is consumed                            | `response`                       |

All events which have the `response` attribute will contain `consumed` and `remaining`
attributes. The `consumed` attribute is the number of API calls consumed and the
`remaining` attribute is the number of API calls remaining in the current
24-hour period.

### Best Practices

- Use asynchronous functions if you make asynchronous IO operations and synchronous
  functions if you make synchronous IO operations in your callback.
- Use the `match` or `if` statement to filter out events you are not interested in.
- Declare one callback for each operation you want to perform. This will make
  your code run faster and be easier to understand.

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
