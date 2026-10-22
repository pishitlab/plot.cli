"""Domain errors, one class per error code in SPEC §8.1.

Each class carries its stable ``code`` and the HTTP status the API maps it to,
so the API layer can render the error envelope without a lookup table.
"""

from typing import Any, ClassVar


class PlotError(Exception):
    code: ClassVar[str] = "INTERNAL_ERROR"
    http_status: ClassVar[int] = 500
    default_message: ClassVar[str] = "unexpected error"

    def __init__(self, message: str | None = None, **details: Any) -> None:
        self.message = message or self.default_message
        self.details: dict[str, Any] = details
        super().__init__(self.message)


# 400 — input breaks a rule
class BadRequestError(PlotError):
    http_status = 400


class InvalidName(BadRequestError):
    code = "INVALID_NAME"
    default_message = "invalid name"


class NotRegistrable(BadRequestError):
    code = "NOT_REGISTRABLE"
    default_message = "name is not registrable"


class TldNotSupported(BadRequestError):
    code = "TLD_NOT_SUPPORTED"
    default_message = "suffix is not supported"


class ReservedName(BadRequestError):
    code = "RESERVED_NAME"
    default_message = "name is reserved"


class InvalidPeriod(BadRequestError):
    code = "INVALID_PERIOD"
    default_message = "invalid registration period"


class InvalidStatus(BadRequestError):
    code = "INVALID_STATUS"
    default_message = "invalid status"


class InvalidAddress(BadRequestError):
    code = "INVALID_ADDRESS"
    default_message = "invalid address"


class InvalidNsCount(BadRequestError):
    code = "INVALID_NS_COUNT"
    default_message = "invalid number of nameservers"


class DuplicateNs(BadRequestError):
    code = "DUPLICATE_NS"
    default_message = "duplicate nameserver"


class HostAddrRequired(BadRequestError):
    code = "HOST_ADDR_REQUIRED"
    default_message = "subordinate host requires at least one address"


class HostAddrForbidden(BadRequestError):
    code = "HOST_ADDR_FORBIDDEN"
    default_message = "external host must not have addresses"


class GlueRequired(BadRequestError):
    code = "GLUE_REQUIRED"
    default_message = "in-bailiwick nameserver requires glue"


class ValidationFailed(BadRequestError):
    code = "VALIDATION_ERROR"
    default_message = "validation error"


# 401
class Unauthorized(PlotError):
    code = "UNAUTHORIZED"
    http_status = 401
    default_message = "missing or invalid API key"


# 404
class NotFoundError(PlotError):
    http_status = 404


class DomainNotFound(NotFoundError):
    code = "DOMAIN_NOT_FOUND"
    default_message = "domain not found"


class HostNotFound(NotFoundError):
    code = "HOST_NOT_FOUND"
    default_message = "host not found"


# 409
class ConflictError(PlotError):
    http_status = 409


class DomainExists(ConflictError):
    code = "DOMAIN_EXISTS"
    default_message = "domain already registered"


class HostExists(ConflictError):
    code = "HOST_EXISTS"
    default_message = "host already exists"


class HostInUse(ConflictError):
    code = "HOST_IN_USE"
    default_message = "host is in use as a nameserver"


class RenewLimit(ConflictError):
    code = "RENEW_LIMIT"
    default_message = "renewal would exceed the 10 year limit"


# 410
class DomainPurged(PlotError):
    code = "DOMAIN_PURGED"
    http_status = 410
    default_message = "domain has been purged"


# 500
class InternalError(PlotError):
    code = "INTERNAL_ERROR"
    http_status = 500
