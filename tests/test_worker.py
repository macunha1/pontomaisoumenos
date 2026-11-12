import httpx
import pytest

from pontomaisoumenos.pontomais import PermanentPunchError, RetryablePunchError, UncertainPunchError
from pontomaisoumenos.worker import retry_when


@pytest.mark.parametrize(
    "failure",
    [PermanentPunchError(), UncertainPunchError(), httpx.ReadTimeout("unknown outcome"), RuntimeError()],
)
def test_only_explicitly_safe_failures_retry(failure: Exception) -> None:
    assert not retry_when(0, failure)


def test_transient_retries_are_bounded() -> None:
    assert retry_when(4, RetryablePunchError())
    assert not retry_when(5, RetryablePunchError())
