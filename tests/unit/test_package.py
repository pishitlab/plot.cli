import plot


def test_package_exposes_version() -> None:
    assert plot.__version__ == "0.0.0"
