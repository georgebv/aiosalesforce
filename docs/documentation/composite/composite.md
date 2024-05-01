## Overview

Composite allows executing up to 25 subrequests with the ability to reference
the results of previous subrequests in subsequent subrequests. To execute a
composite request, create a composite instance, add subrequests to it, and then execute
it:

```python
async with salesforce.composite(all_or_none=True) as composite:
    account = composite.sobject.create(
        "Account",
        {"Name": "Acme Corporation"},
    )
    contact = composite.sobject.create(
        "Contact",
        {"FirstName": "Jon", "LastName": "Doe", "AccountId": account.reference.id},
    )
print(account.id)
print(contact.id)
```

You can also execute the composite request without using the context manager:

```python
composite = salesforce.composite(all_or_none=True)
account = composite.sobject.create(
    "Account",
    {"Name": "Acme Corporation"},
)
contact = composite.sobject.create(
    "Contact",
    {
        "FirstName": "Jon",
        "LastName": "Doe",
        "AccountId": account.reference.id,
    },
)
await composite.execute()
print(account.id)
print(contact.id)
```

You can control composite behavior using the following parameters:

- `all_or_none` - if `True`, all subrequests are rolled back if any subrequest fails.
  By default, `False`.
- `collate_subrequests` - if `True`, independent subrequests are executed in parallel.
  By default, `True`.
- `autoraise` - raise an ExceptionGroup if any subrequest fails. By default, `False`.

Once a composite request is executed, you can access the following attributes for each
of its subrequests:

- `response` - the response dictionary
- `done` - whether the subrequest has been executed
- `response_body` - subrequest response body
- `response_http_headers` - subrequest response HTTP headers
- `status_code` - HTTP status code
- `is_success` - whether the subrequest was successful

You can also raise an exception if the subrequest failed:

```python
subrequest.raise_for_status()
```

## Referencing Subrequests

You can reference the results of previous subrequests in subsequent subrequests by
using the `reference` attribute of the subrequest result. The `reference` attribute
returns a special objects which supports item (`$[i]`) and attribute (`$.attr`) access.
For example, `subrequest.reference.children[0].id` references the `id` attribute of the
first subrequest result in the `children` attribute of the subrequest result.
Specific format of the reference depends on response body structure for the
referenced subrequest.

```python
async with salesforce.composite() as composite:
    query = composite.query("SELECT Id, Name FROM Account LIMIT 1")
    contact = composite.sobject.create(
        "Contact",
        {
            "FirstName": "Jon",
            "LastName": "Doe",
            "AccountId": query.reference.records[0].Id,
        },
    )
print("Created contact:", contact.id)
```

## Supported Subrequests

### Query

Execute SOQL query and get its results:

```python
async with salesforce.composite() as composite:
    query_accounts = composite.query("SELECT Id, Name FROM Account LIMIT 10")
    query_contacts = composite.query("SELECT Id, Name FROM Contact LIMIT 10")
print(query_accounts.records)
print(query_contacts.records)
```

Subrequest results are available via the `records` attribute.

### sObject

Perform CRUD operations on sObjects using the same interface as the
[`salesforce.sobject`](../sobject.md) resource:

```python
async with salesforce.composite(all_or_none=True) as composite:
    account = composite.sobject.update(
        "Account",
        "0011R00001K1H2IQAV",
        {"Name": "New Name"},
    )
    contact = composite.sobject.upsert(
        "Contact",
        "ExternalId__c",
        {
            "ExternalId__c": "123",
            "FirstName": "Jon",
            "LastName": "Doe",
            "AccountId": account.reference.id,
        },
    )
    appointment = composite.sobject.create(
        "Appointment__c",
        {
            "Name__c": "Treatment 123",
            "Contact__c": contact.reference.id,
        },
    )
print("Updated account:", account.id)
print("Upserted contact:", contact.id)
print("Created appointment:", appointment.id)
```

Depending on the operation, the subrequest result may contain the following attributes:

- `create`: `id`
- `get`: `record`
- `upsert`: `id`, `created`
