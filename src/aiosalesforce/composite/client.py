from typing import TYPE_CHECKING

from .batch import CompositeBatchRequest
from .composite import CompositeRequest

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

    def __init__(self, salesforce_client: "Salesforce") -> None:
        self.salesforce_client = salesforce_client

    def batch(
        self,
        halt_on_error: bool = False,
        autoraise: bool = False,
        group_errors: bool = False,
    ) -> CompositeBatchRequest:
        """
        Start a Comsposite Batch operation.

        To execute a batch request, add subrequests to the batch and call `execute`.
        Alternatively, use a context manager to automatically execute the batch.

        Parameters
        ----------
        halt_on_error : bool, default False
            If True, unprocessed subrequests will be halted if any subrequest fails.
        autoraise : bool, default False
            If True, an exception will be raised if any subrequest fails.
        group_errors : bool, default False
            Ignored if `autoraise` is False.
            If True, raises an ExceptionGroup with all errors.
            Otherwise, raises the first exception.

        Returns
        -------
        CompositeBatchRequest
            Composite Batch request.

        Examples
        --------
        >>> async with salesforce.composite.batch(halt_on_error=True) as batch:
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
            group_errors=group_errors,
        )

    def __call__(
        self,
        all_or_none: bool = False,
        collate_subrequests: bool = False,
        autoraise: bool = False,
    ) -> CompositeRequest:
        """
        Start a Comsposite operation.

        To execute a composite request, add subrequests to it and call `execute`.
        Alternatively, use a context manager to automatically execute the request.

        Parameters
        ----------
        all_or_none : bool, default False
            If True, all subrequests are rolled back if any subrequest fails.
        collate_subrequests : bool, default True
            If True, independent subrequests are executed by Salesforce in parallel.
        autoraise : bool, default False
            If True, raises an ExceptionGroup if any subrequest fails.

        Returns
        -------
        CompositeRequest
            Composite request.

        Examples
        --------
        >>> async with salesforce.composite(all_or_none=True) as batch:
        ...     account = composite.sobject.create(
        ...         "Account",
        ...         {...},
        ...     )
        ...     contact = composite.sobject.create(
        ...         "Contact",
        ...         {"Account": account.reference.id, ...}
        ...     )
        ... print(account.id)
        ... print(contact.id)

        """
        return CompositeRequest(
            salesforce_client=self.salesforce_client,
            all_or_none=all_or_none,
            collate_subrequests=collate_subrequests,
            autoraise=autoraise,
        )
