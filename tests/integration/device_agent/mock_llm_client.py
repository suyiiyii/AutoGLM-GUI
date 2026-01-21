"""Test client for Mock LLM Server.

Provides a convenient API for interacting with the Mock LLM Server
in integration tests.
"""

import httpx


class MockLLMTestClient:
    """Test client for Mock LLM Server.

    Example:
        >>> client = MockLLMTestClient("http://localhost:18003")
        >>> client.reset()
        >>> stats = client.get_stats()
        >>> print(stats["request_count"])
    """

    def __init__(self, base_url: str = "http://localhost:18003", timeout: float = 30.0):
        """Initialize the test client.

        Args:
            base_url: Base URL of the mock LLM server
            timeout: HTTP request timeout
        """
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    def get_stats(self) -> dict:
        """Get request statistics.

        Returns:
            Dict with 'request_count' and 'total_responses'
        """
        resp = self._client.get("/test/stats")
        resp.raise_for_status()
        return resp.json()

    def reset(self) -> dict:
        """Reset request counter.

        Returns:
            Dict with reset status
        """
        resp = self._client.post("/test/reset")
        resp.raise_for_status()
        return resp.json()

    def set_responses(self, responses: list[str]) -> dict:
        """Set custom responses.

        Args:
            responses: List of response strings to use in round-robin

        Returns:
            Dict with update status and response count
        """
        resp = self._client.post("/test/set_responses", json=responses)
        resp.raise_for_status()
        return resp.json()

    def assert_request_count(self, expected: int) -> None:
        """Assert request count matches expected.

        Args:
            expected: Expected request count

        Raises:
            AssertionError: If count doesn't match
        """
        stats = self.get_stats()
        actual = stats["request_count"]
        assert actual == expected, f"Expected {expected} requests, got {actual}"

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
