In Salesforce sObject is any standard or custom object. Each object has records
which you can create, read, update, or delete. You can interact with sObjects using
the `SobjectClient` which is exposed via the `sobject` property of the `Salesforce`
client.

```python
account = await salesforce.sobject.get('Account', '0012v00002Q8f4QAAR')
```

!!! info "Information"

    When you create, update, delete, or upser a record, you must provide the `data`
    parameter. This parameter can be either a dictionary or a string/bytes/bytearray
    object which represents a dictionary serialized as JSON. Take advantage of this
    if you have custom data types that are not serializable by `orjson`.

## Create

To create a new record, you must provide the object name and the data for the new
record. The `create` method returns the ID of the newly created record.

```python
data = {
    "FirstName": "Jon",
    "LastName": "Doe",
    "Phone": "1234567890",
    "Email": "jon.doe@example.com",
}
contact_id = await salesforce.sobject.create('Contact', data)
```

## Read

To read a record, you must provide the object name and the ID of the record you
want to read. The `get` method returns the record as a dictionary.

```python
contact = await salesforce.sobject.get('Contact', contact_id)
```

By default the `get` method returns all fields for the record. If you want to get
only the specific fields you want to retrieve, you can provide a list of field names
in the `fields` parameter.

```python
contact = await salesforce.sobject.get(
    "Contact",
    contact_id,
    fields=["FirstName", "LastName", "Email"],
)
```

## Update

To update a record, you must provide the object name, the ID of the record you want
to update, and the data you want to update. The `update` method doesn't return anything.

```python
data = {
    "Phone": "0987654321",
}
await salesforce.sobject.update('Contact', contact_id, data)
```

## Delete

To delete a record, you must provide the object name and the ID of the record you want
to delete. The `delete` method doesn't return anything.

```python
await salesforce.sobject.delete('Contact', contact_id)
```

## Using External ID

You can use an external ID to read, delete, or upsert (create or update) a record.
To read or delete a record using an external ID, you must provide
the `external_id_field` parameter and set ID to the exteral ID value (instead of the
record ID):

```python
contact = await salesforce.sobject.get(
    "Contact",
    "123456",  # External ID value
    "ExternalId__c",  # External ID field
)

await salesforce.sobject.delete(
    "Contact",
    "123456",  # External ID value
    "ExternalId__c",  # External ID field
)
```

!!! warning "Warning"

    When using an external ID, make sure that the external ID field is unique.
    This can be configured in Salesforce by setting the field as unique.
    If the are multiple records with the same external ID, you will get a
    `MoreThanOneRecordError` error.

### Upsert

To upsert a record using an external ID, you must provide the object name, external ID
value and field name, and the data you want to upsert. The `upsert` method returns a
dataclass with two attributes:

- `id` - Salesforce ID (NOT external ID) of the upserted record
- `created` - boolean value indicating whether the record was created (`True`)
  or updated (`False`)

```python
data = {
    "FirstName": "Jon",
    "LastName": "Doe",
    "Phone": "1234567890",
    "Email": "jon.doe@example.com",
}
response = await salesforce.sobject.upsert(
    "Contact",
    "123456",  # External ID value
    "ExternalId__c",  # External ID field
    data,
)
operation = "created" if response.created else "updated"
print(f"{operation} record with ID {response.id}")
```

!!! info "Information"

    By default, the `upsert` method checks your payload for the external ID field.
    If the external ID field is present, it is removed from the payload before sending
    the request. This is because Salesforce doesn't allow external ID fields to be
    included in the payload when upserting a record. The default behavior results in
    a slight performance penalty because your payload is deserialized and serialized
    (if it's string/bytes) to remove the external ID field. If you know that your
    payload doesn't contain the external ID field, you can set the `validate`
    parameter to `False` to skip the check.
