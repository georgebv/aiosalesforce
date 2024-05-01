## Overview

Composite Batch allows executing up to 25 independent subrequests in a single request.
To execute a batch of subrequests, create a batch, add subrequests to it, and then
execute it:

```python
async with salesforce.composite.batch(halt_on_error=True) as batch:
    query = batch.query("SELECT Id, Name FROM Account LIMIT 10")
    contact = batch.sobject.create(
        "Contact",
        {"FirstName": "Jon", "LastName": "Doe"},
    )
print(query.records)
print(contact.id)
```

You can also execute the batch without using the context manager:

```python
batch = salesforce.composite.batch(halt_on_error=True)
query = batch.query("SELECT Id, Name FROM Account LIMIT 10")
contact = batch.sobject.create(
    "Contact",
    {"FirstName": "Jon", "LastName": "Doe"},
)
await batch.execute()
print(query.records)
print(contact.id)
```

You can control batch behavior using the following parameters:

- `halt_on_error` - if any subrequest fails, all subsequent subrequests are skipped and
  marked as failed. By default, `False`.
- `autoraise` - raise an exception if any subrequest fails. By default, `False`.
- `group_errors` - raise ExceptionGroup instead of the first exception
  if `autoraise` is `True`. By default, `False`.

Once a composite batch is executed, you can access the following attributes
for each of its subrequests:

- `response` - the response dictionary
- `done` - whether the subrequest has been executed
- `status_code` - HTTP status code
- `result` - the result of the subrequest (response body)
- `is_success` - whether the subrequest was successful

You can also raise an exception if the subrequest failed:

```python
subrequest.raise_for_status()
```

## Supported Subrequests

### Query

Execute SOQL query and get its results:

```python
async with salesforce.composite.batch() as batch:
    query_accounts = batch.query("SELECT Id, Name FROM Account LIMIT 10")
    query_contacts = batch.query("SELECT Id, Name FROM Contact LIMIT 10")
print(query_accounts.records)
print(query_contacts.records)
```

Subrequest results are available via the `records` attribute.

### sObject

Perform CRUD operations on sObjects using the same interface as the
[`salesforce.sobject`](../sobject.md) resource:

```python
async with salesforce.composite.batch() as batch:
    contact = batch.sobject.create(
        "Contact",
        {"FirstName": "Jon", "LastName": "Doe"},
    )
    account = batch.sobject.update(
        "Account",
        "0011R00001K1H2IQAV",
        {"Name": "New Name"},
    )
    opportunity = batch.sobject.upsert(
        "Opportunity",
        "ExternalId__c",
        {"ExternalId__c": "123", "Name": "New Opportunity"},
    )
print("Created contact:", contact.id)
print("Updated account:", account.id)
print("Upserted opportunity:", opportunity.id)
```

Depending on the operation, the subrequest result may contain the following attributes:

- `create`: `id`
- `get`: `record`
- `upsert`: `id`, `created`
