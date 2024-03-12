__all__ = [
    "RetryPolicy",
    "ExceptionRule",
    "ResponseRule",
    "RULE_EXCEPTION_RETRY_TRANSPORT_ERRORS",
    "RULE_RESPONSE_RETRY_SERVER_ERRORS",
    "RULE_RESPONSE_RETRY_UNABLE_TO_LOCK_ROW",
    "RULE_RESPONSE_RETRY_TOO_MANY_REQUESTS",
    "POLICY_DEFAULT",
]

from httpx import TimeoutException, TransportError

from .policy import RetryPolicy
from .rules import ExceptionRule, ResponseRule

RULE_EXCEPTION_RETRY_TRANSPORT_ERRORS = ExceptionRule(
    TransportError,
    lambda exc: not isinstance(exc, TimeoutException),
    max_retries=3,
)
RULE_RESPONSE_RETRY_SERVER_ERRORS = ResponseRule(
    lambda response: response.status_code >= 500,
    max_retries=3,
)
RULE_RESPONSE_RETRY_UNABLE_TO_LOCK_ROW = ResponseRule(
    lambda response: "UNABLE_TO_LOCK_ROW" in response.text,
    max_retries=3,
)
RULE_RESPONSE_RETRY_TOO_MANY_REQUESTS = ResponseRule(
    lambda response: response.status_code == 429,
    max_retries=3,
)

POLICY_DEFAULT = RetryPolicy(
    response_rules=[
        RULE_RESPONSE_RETRY_SERVER_ERRORS,
        RULE_RESPONSE_RETRY_UNABLE_TO_LOCK_ROW,
        RULE_RESPONSE_RETRY_TOO_MANY_REQUESTS,
    ],
    exception_rules=[RULE_EXCEPTION_RETRY_TRANSPORT_ERRORS],
)
