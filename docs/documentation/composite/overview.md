Salesforce has a family of composite resources which allow executing multiple
operations within a single request. These are the composite resources available in
`aiosalesforce` (listed in the order of increasing complexity and capability):

- [Composite Batch](./batch.md) - execute up to 25 independent subrequests
- [Composite](./composite.md) - execute up to 25 subrequests with the ability
  to reference the results of previous subrequests in subsequent subrequests
- Composite graph - :construction: work in progress
- sObject Tree - :construction: work in progress
- sObject Collections - :construction: work in progress

Composite resources are exposed via the `composite` attribute of the `Salesforce`
client.

!!! warning "Warning"

    Composite subrequests are not treated as regular requests by `aiosalesforce`.
    This means that retries and events are applied only to the composite request itself
    and not to the subrequests it contains. This is consistent with how the Bulk API
    works.
