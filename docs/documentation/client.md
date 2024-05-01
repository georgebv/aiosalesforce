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

Valid version values looks like `XX`, `XX.`, `XX.0`, `vXX`, `vXX.`, `vXX.0`, where
`XX` is a number. For example, `52.0` is a valid version but `52.1` is not.

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
`subscribe_callback` and `unsubscribe_callback` methods of the `event_bus` attribute
of the `Salesforce` client.

```python
salesforce.event_bus.subscribe_callback(callback)
salesforce.event_bus.unsubscribe_callback(callback)
```

!!! note "Note"

    Event hooks are executed concurrently and are not guaranteed to be called in
    the order they were added. Do not rely on the order of execution of your
    callback functions. If you need to perform certain operations in a specific order,
    declare them within the same callback function.

### Events

All events emitted by the `Salesforce` client are instances of the
[`Event`](../api-reference/events.md#aiosalesforce.events.Event) class.
You can determine the type of event by checking the `type` attribute of the event
or by checking the type of the event object.

| Event                          | `type`                       | When emitted                                                                                       | Attributes                                                          |
| ------------------------------ | ---------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `RequestEvent`                 | `request`                    | Before making a request to the Salesforce API                                                      | `request`                                                           |
| `RetryEvent`                   | `retry`                      | Before request is retried. Depending on the cause, has either `response` or `exception` attributes | `request`, `attempt`, `response` (optional), `exception` (optional) |
| `ResponseEvent`                | `response`                   | After an OK (status code < 300) response is received                                               | `response`                                                          |
| `RestApiCallConsumptionEvent`  | `rest_api_call_consumption`  | When a Salesforce API call is consumed (includes unsuccessful requests)                            | `response`, `count`                                                 |
| `BulkApiBatchConsumptionEvent` | `bulk_api_batch_consumption` | When a Bulk API (v1 or v2) batch is consumed                                                       | `response`, `count`                                                 |

!!! note "Note"

    The `attempt` attribute of the `RetryEvent` indicates sequential number
    of the retry attempt. The first retry attempt is `1`, the second is `2`, and so on.
    Attempt `0` is the initial request and is not a retry.

!!! note "Note"

    All events which have the `response` attribute will contain
    `consumed` and `remaining` attributes. The `consumed` attribute is the number
    of API calls consumed and the `remaining` attribute is the number of API calls
    remaining in the current 24-hour period. Not all responses will have this
    information (for example, authentication responses) - in such cases,
    these attributes will have value `None`.

!!! warning "Warning"

    `BulkApiBatchConsumptionEvent` is best-effort and is not guaranteed to accurately
    reflect the number of consumed batches when using Bulk API 2.0. This is because
    Salesforce does not provide a way to track the number of consumed batches and
    `aiosalesforce` uses heuristics to estimate the number of consumed batches.

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
            my_metrics_service.put_metric_data(
                Namespace="Salesforce",
                MetricData=[
                    {
                        "MetricName": "Salesforce REST API Call Count",
                        "Value": event.count,
                        "Unit": "Count",
                    },
                ],
            )
        case BulkApiBatchConsumptionEvent():
            my_metrics_service.put_metric_data(
                Namespace="Salesforce",
                MetricData=[
                    {
                        "MetricName": "Salesforce Bulk API Batch Count",
                        "Value": event.count,
                        "Unit": "Count",
                    },
                ],
            )


salesforce.event_bus.subscribe_callback(track_api_usage)
```

#### Log Retries

```python
from aiosalesforce import Event, RetryEvent


async def log_retries(event: Event):
    match event:
        case RetryEvent():
            print(
                f"Retrying {event.request.method} request to {event.request.url} "
                f"due to: {event.response or type(event.exception).__name__}. "
                f"This is attempt {event.attempt}"
            )


salesforce.event_bus.subscribe_callback(log_retries)
```

#### Log Requests

```python
from aiosalesforce import Event, RequestEvent


async def log_requests(event: Event):
    match event:
        case RequestEvent():
            logger.info("%s %s", event.request.method, event.request.url)


salesforce.event_bus.subscribe_callback(log_requests)
```

### Best Practices

- Use asynchronous functions if you make asynchronous IO operations and synchronous
  functions if you make synchronous IO operations in your callback.
- Use the `match` or `if` statements to filter out events you are not interested in.
- Declare one callback for each operation you want to perform. This will make
  your code simpler to understand and may make it run faster if you have IO operations
  inside your callbacks.

## Retrying Requests

You can configure the `Salesforce` client to automatically retry requests that fail
for various reasons. This can be useful for handling transient errors which are
expected to succeed under normal circumstances. For example, you may want to retry
server errors caued by temporary instabilities in a Salesforce processing node
working on your request.

You can control the retry behavior by passing a `RetryPolicy` instance to the
`retry_policy` parameter of the `Salesforce` client. A `RetryPolicy` instance
defines the conditions under which a request should be retried, how many times
it should be retried, and how long to wait between retries.

```python
from aiosalesforce import RetryPolicy, ExceptionRule, ResponseRule

retry_policy = RetryPolicy(
    response_rules=[
        ResponseRule(lambda response: response.status_code >= 500, max_retries=5),
        ResponseRule(lambda response: "UNABLE_TO_LOCK_ROW" in response.text),
    ],
    exception_rules=[
        ExceptionRule(httpx.TransportError, max_retries=3),
    ],
    max_retries=10,
)

salesforce = Salesforce(
    ...
    retry_policy=retry_policy,
)
```

After the maximum number of retries or when a timeout is reached, the client will
raise an exception.

!!! note "Note"

    By default, the `Salesforce` client will retry requests up to 3 times when caused
    by the following errors:

    - `httpx.TransportError` (excluding `httpx.TimeoutException`) - network issues
    - Server errors (status code >= 500)
    - `UNABLE_TO_LOCK_ROW` error
    - Rate limits errors (status code 429 or `REQUEST_LIMIT_EXCEEDED` in response)

### Retry Policy

A `RetryPolicy` instance is used to define the conditions under which a request
should be retried, how many times it should be retried, and how long to wait between
retries. There are two reasons why a request can fail:

- Status code of the response is not OK (status code >= 300)
- An exception is raised during the request

To handle these two cases, you need to define `response_rules` and `exception_rules`
and pass them to the `RetryPolicy` instance.

```python
retry_policy = RetryPolicy(
    response_rules=[...],
    exception_rules=[...],
    max_retries=10,
    timeout=60,
)
```

The logic when deciding if a request should be retried is as follows:

1.  Check if `max_retries` or `timeout` is reached for the request retrying context
    in accordance with the client's `retry_policy` - if so, raise an exception.
2.  Evaluate rules in the order they were provided. If a rule:
    <!-- prettier-ignore -->
    - Doesn't match - move to the next rule
    - Matches
        - Its `max_retries` is exhausted - raise an exception
        - Its `max_retries` is not exhausted - increment its retry count, sleep,
          and retry the request
3.  If none of the rules match - raise an exception.

You can find more information about the `RetryPolicy` class in the
[API Reference](../api-reference/retries.md#aiosalesforce.retries.RetryPolicy).

### Response Rule

A response rule is evaluated when a request fails due to a status code
not being OK (status code >= 300). A response rule needs a function which
it calls with the response object. If the function returns `True`, the rule
matches and the request will be retried.
You can also specify the maximum number of retries for the rule (by default 3).

```python
from aiosalesforce import ResponseRule

response_rule = ResponseRule(
    lambda response: response.status_code >= 500,
    max_retries=5,
)
```

Function used in response rule can be asynchronous. This can be useful if you
need to make an asynchronous IO operation to determine if the request should
be retried. If, however, you need to make a synchronous IO operation, you should
use a regular function - it will be run in a separate thread to avoid blocking
the event loop.

### Exception Rule

An exception rule is evaluated when a request fails due to an exception being raised
by `httpx`. An exception rule needs an exception type on which it retries the request.
By default, it will always retry on this exception. If you need to have more control
over when the request should be retried, you can specify a function which it calls
with the exception object. If the function returns `True`, the rule matches and the
request will be retried. You can also specify the maximum number of retries
for the rule (by default 3).

```python
from aiosalesforce import ExceptionRule

exception_rule = ExceptionRule(
    httpx.TransportError,
    lambda exc: not isinstance(exc, httpx.TimeoutException),
    max_retries=3,
)
```

Similar to response rules, the function used in exception rules can be asynchronous
or synchronous.

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
