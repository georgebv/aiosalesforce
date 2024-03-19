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
request-response lifecycle. For example, you can log requests and responses, monitor
retries, or track usage of different Salesforce APIs within your application.

To subscribe to events, you need to define a callback function and then pass it to
the `Salesforce` client. The callback function will be called when an event is emitted.
The callback function will receive an event object as the only argument and will not
return anything (any return value will be ignored by the client).

```python
async def callback(event):
    # Do something with the event
    ...
```

Once you have defined your callback functions, you can pass them to the `Salesforce`
client using the `event_hooks` parameter.

```python
salesforce = Salesforce(
    ...,
    event_hooks=[callback, ...],
)
```

You can also add or remove callbacks after the client has been created using the
`subscribe_callback` and `unsubscribe_callback` methods of the `event_loop` attribute
of the `Salesforce` client.

```python
salesforce.event_loop.subscribe_callback(callback)
salesforce.event_loop.unsubscribe_callback(callback)
```

!!! note "Note"

    Event hooks are executed concurrently and are not guaranteed to be called in
    the order they were added. Do not rely on the order of execution of your
    callback functions. If you need to perform certain operations in a specific order,
    declare them within the same callback function.

### Events

All events emitted by the `Salesforce` client are instances of the
[`Event`](/aiosalesforce/api-reference/events/#aiosalesforce.events.Event) class.
You can determine the type of event by checking the `type` attribute of the event
or by checking the type of the event object.

| Event                          | `type`                       | When emitted                                                            | Attributes                       |
| ------------------------------ | ---------------------------- | ----------------------------------------------------------------------- | -------------------------------- |
| `RequestEvent`                 | `request`                    | Before making a request to the Salesforce API                           | `request`                        |
| `RetryEvent`                   | `retry`                      | Before request is retried                                               | `request`, `response` (optional) |
| `ResponseEvent`                | `response`                   | After an OK (status code < 300) response is received                    | `response`                       |
| `RestApiCallConsumptionEvent`  | `rest_api_call_consumption`  | When a Salesforce API call is consumed (includes unsuccessful requests) | `response`                       |
| `BulkApiBatchConsumptionEvent` | `bulk_api_batch_consumption` | When a Bulk API (v1 or v2) batch is consumed                            | `response`                       |

!!! note "Note"

    All events which have the `response` attribute will contain
    `consumed` and `remaining` attributes. The `consumed` attribute is the number
    of API calls consumed and the `remaining` attribute is the number of API calls
    remaining in the current 24-hour period. Not all responses will have this
    information (for example, authentication responses) - in such cases,
    these attributes will have value `None`.

### Callback Function

The callback function will receive an event object as the only argument. You cannot
specify what type of event you want to subscribe to - your callback function will
receive all events emitted by the `Salesforce` client. You are responsible for
filtering out events you are not interested in.

Using the `type` attribute:

```python
from aiosalesforce import Event

async def callback(event: Event) -> None:
    match event.type:
        case "request":
            # Do something with the request event
            ...
        case "response":
            # Do something with the response event
            ...
        case _:
            # Do nothing for other events
            pass
```

Using the type of the event object:

```python
from aiosalesforce import RequestEvent, ResponseEvent

def callback(event) -> None:
    match event:
        case RequestEvent():
            # Do something with the request event
            ...
        case ResponseEvent():
            # Do something with the response event
            ...
        case _:
            # Do nothing for other events
            pass
```

!!! warning "Warning"

    Only use `async def` if your callback function is asynchronous. If it contains
    synchronous network calls, it will slow down the entire application by blocking
    the event loop. If you need to perform synchronous operations, declare your
    function as a regular function using `def` - such functions will be run in
    a separate thread to avoid blocking the event loop. You can mix asynchronous
    and synchronous functions when using event hooks - `aiosalesforce` will use
    an appropriate concurrency model for each of your callback functions.

### Examples

#### Keep Track of API Usage

An example below shows how you can use event hooks to keep track of the number
of requests made to the Salesforce API. This can be useful if you want to record and
monitor your API usage over time. For example, you can use send usage metrics to
a metrics service like AWS CloudWatch.

```python
from aiosalesforce import (
    Event,
    BulkApiBatchConsumptionEvent,
    RestApiCallConsumptionEvent,
)


def track_api_usage(event: Event):
    match event:
        case RestApiCallConsumptionEvent():
            # Write to a metrics service (e.g., AWS CloudWatch)
            ...
        case BulkApiBatchConsumptionEvent():
            # Write to a metrics service (e.g., AWS CloudWatch)
            ...
        case _:
            # Do nothing for other events
            pass
```

#### Log Retries

```python
from aiosalesforce import Event, RetryEvent


async def log_retries(event: Event):
    match event:
        case RetryEvent():
            # Log the request and response
            print(
                f"Retrying {event.request.method} request to {event.request.url}"
            )
        case _:
            # Do nothing for other events
            pass
```

### Best Practices

- Use asynchronous functions if you make asynchronous IO operations and synchronous
  functions if you make synchronous IO operations in your callback.
- Use the `match` or `if` statements to filter out events you are not interested in.
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
