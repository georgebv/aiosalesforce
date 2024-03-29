You can perform SOQL queries by using the `query` method of the `Salesforce` client.
This method accepts a SOQL query string and return an asynchronous generator that
yields records returned by the query.

```python
records = []
async for record in client.query("SELECT Id, Name FROM Account"):
    records.append(record)
```

!!! warning "Warning"

    The `query` method returns an asynchronous generator. You must use it with the
    `async for` statement to iterate over the records returned by the query.

By default, query method returns only active records. If you need to also include
archived or deleted records, you must pass the `include_all_records` parameter:

```python
records = []
async for record in client.query(
    "SELECT Id, Name FROM Account",
    include_all_records=True,
):
    records.append(record)
```

## Formatting SOQL Queries

If your query contains dynamic parameters, you should use the
[`format_soql`](../api-reference/utils.md/#aiosalesforce.utils.format_soql) function
to format your query string. SOQL is generally safe by design - it is not possible
to mutate (create/update/delete) records using SOQL queries. However, you may still
be vulnerable to SQL injection attacks where malicious input can result in fetching
data which the caller should not have access to. Therefore, it is a good practice
to always use the `format_soql` function to format your query string when using
dynamic parameters.

### Basic Usage

```python
query = format_soql(
    "SELECT Id, Name FROM Account WHERE Name = {name}",
    name="My Account",
)
async for record in client.query(query):
    ...
```

The above would produce the following query string:

```sql
SELECT Id, Name FROM Account WHERE Name = 'My Account'
```

By default, the `format_soql` function adds single quotes around the parameter value(s)
when appropriate (there are exceptions like bools, dates, numbers). You should not
add your own quotes around the parameter value.

### Collections

You can also pass an array of values (can be `list`, `tuple`, or `set`):

```python
query = format_soql(
    "SELECT Id, Name FROM Account WHERE Name IN {names}",
    names=["My Account", "Another Account"],
)
```

The above would produce the following query string:

```sql
SELECT Id, Name FROM Account WHERE Name IN ('My Account', 'Another Account')
```

### LIKE Operator

When formatting expressions containing the `LIKE` operator, you should use the special
format spec `{:like}`:

```python
query = format_soql(
    "SELECT Id, Name FROM User WHERE Name LIKE '%{name:like}",
    name="Jon%",
)
```

The above would produce the following query string:

```sql
SELECT Id, Name FROM User WHERE Name LIKE '%Jon\%'
```

Notice that when using the `{:like}` format spec, single quotes are not added around
the parameter value.
