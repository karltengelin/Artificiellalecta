"""SDK-gräns för diagnostikens Claude Managed Agents-prov."""

from contextlib import contextmanager

from anthropic import APIError, Anthropic


class ManagedAPIError(Exception):
    def __init__(self, error_type, status_code, request_id, detail):
        super().__init__(error_type)
        self.status_code = status_code
        self.request_id = request_id
        self.detail = detail


@contextmanager
def managed_client(api_key):
    try:
        with Anthropic(api_key=api_key, timeout=15, max_retries=0) as client:
            yield client.beta
    except APIError as exc:
        status = getattr(exc, "status_code", None)
        body = getattr(exc, "body", None)
        detail = body.get("error", {}).get("message", "") if status == 400 and isinstance(body, dict) else ""
        raise ManagedAPIError(type(exc).__name__, status, getattr(exc, "request_id", None), detail) from None
