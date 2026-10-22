import pytest

from plot.core import errors

# SPEC §8.1: HTTP status -> error codes
SPEC_CODES = {
    400: {
        "INVALID_NAME",
        "NOT_REGISTRABLE",
        "TLD_NOT_SUPPORTED",
        "RESERVED_NAME",
        "INVALID_PERIOD",
        "INVALID_STATUS",
        "INVALID_ADDRESS",
        "INVALID_NS_COUNT",
        "DUPLICATE_NS",
        "HOST_ADDR_REQUIRED",
        "HOST_ADDR_FORBIDDEN",
        "GLUE_REQUIRED",
        "VALIDATION_ERROR",
    },
    401: {"UNAUTHORIZED"},
    404: {"DOMAIN_NOT_FOUND", "HOST_NOT_FOUND"},
    409: {"DOMAIN_EXISTS", "HOST_EXISTS", "HOST_IN_USE", "RENEW_LIMIT"},
    410: {"DOMAIN_PURGED"},
    500: {"INTERNAL_ERROR"},
}


def _leaf_error_classes() -> list[type[errors.PlotError]]:
    found: list[type[errors.PlotError]] = []
    stack: list[type[errors.PlotError]] = [errors.PlotError]
    while stack:
        cls = stack.pop()
        subs = cls.__subclasses__()
        if not subs:
            found.append(cls)
        stack.extend(subs)
    return found


def test_every_spec_code_has_exactly_one_class_with_matching_status() -> None:
    by_code: dict[str, list[type[errors.PlotError]]] = {}
    for cls in _leaf_error_classes():
        by_code.setdefault(cls.code, []).append(cls)
    expected = {code: status for status, codes in SPEC_CODES.items() for code in codes}
    assert set(by_code) == set(expected)
    for code, classes in by_code.items():
        assert len(classes) == 1, code
        assert classes[0].http_status == expected[code], code


def test_error_carries_message_and_details() -> None:
    err = errors.DomainExists(name="shop.com")
    assert err.code == "DOMAIN_EXISTS"
    assert err.message == "domain already registered"
    assert err.details == {"name": "shop.com"}
    custom = errors.InvalidName("label too long", label="x")
    assert str(custom) == "label too long"


def test_errors_are_catchable_by_category() -> None:
    with pytest.raises(errors.ConflictError):
        raise errors.HostInUse()
    with pytest.raises(errors.BadRequestError):
        raise errors.GlueRequired()
