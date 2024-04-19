from typing import TYPE_CHECKING

from .batch import CompositeBatchRequest

if TYPE_CHECKING:
    from aiosalesforce.client import Salesforce


class CompositeClient:
    """
    Salesforce REST API Composite client.

    Parameters
    ----------
    salesforce_client : Salesforce
        Salesforce client.

    """

    salesforce_client: "Salesforce"
    base_url: str
    """Base URL in the format https://[subdomain(s)].my.salesforce.com/services/data/v[version]/composite"""

    def __init__(self, salesforce_client: "Salesforce") -> None:
        self.salesforce_client = salesforce_client
        self.base_url = "/".join(
            [
                self.salesforce_client.base_url,
                "services",
                "data",
                f"v{self.salesforce_client.version}",
                "composite",
            ]
        )

    def batch(
        self,
        halt_on_error: bool = False,
        autoraise: bool = False,
    ) -> "CompositeBatchRequest":
        """
        Start a Comsposite Batch operation.

        To execute a batch request, add subrequests to the batch and call `execute`.
        Alternatively, use a context manager to automatically execute the batch.

        Parameters
        ----------
        halt_on_error : bool, default False
            If True, the batch will be halted if any subrequests fail.
        autoraise : bool, default False
            If True, an exception will be raised if any subrequests fail.

        Returns
        -------
        CompositeBatchRequest
            Composite Batch request.

        Examples
        --------
        >>> async with salesforce.composite.batch(autoraise=True) as batch:
        ...     query = batch.query("SELECT Id, Name FROM Account LIMIT 10")
        ...     contact = batch.sobject.create(
        ...         "Contact",
        ...         {"FirstName": "Jon", "LastName": "Doe"},
        ...     )
        ... print(query.records)
        ... print(contact.id)

        """
        return CompositeBatchRequest(
            salesforce_client=self.salesforce_client,
            halt_on_error=halt_on_error,
            autoraise=autoraise,
        )
