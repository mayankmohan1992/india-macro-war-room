"""Regression tests for the DBIE client's retry/reset behaviour.

The 2026-11-09 daily refresh failed because RBI's WAF closed every connection for ~40s and the
client's whole retry budget was ~14s (3 attempts, backoff capped at 10s). These tests pin the
behaviour that failure was about, so a future "tidy-up" of the retry loop cannot quietly put the
14s window back, and so a dead connection pool is provably rebuilt instead of being retried.

Runs on the standard library alone:  python -m unittest discover -s tests -v
"""

import json
import pathlib
import sys
import time
import unittest
from unittest import mock

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import dbie_client                                                # noqa: E402


OK_BODY = json.dumps({"header": {"status": "ok"}, "body": {"rows": [1]}})


class FakeResponse:
    def __init__(self, text=OK_BODY, status_code=200):
        self.text, self.status_code = text, status_code


class FakeSession:
    """Fails the first `fails` POSTs the way a WAF drop does, then succeeds."""

    def __init__(self, fails=0):
        self.fails, self.calls, self.headers = fails, 0, {}

    def post(self, *a, **kw):
        self.calls += 1
        if self.calls <= self.fails:
            raise requests.ConnectionError(
                "('Connection aborted.', RemoteDisconnected('Remote end closed connection "
                "without response'))")
        return FakeResponse()

    def get(self, *a, **kw):
        return FakeResponse("", 200)

    def close(self):
        pass


class TestableClient(dbie_client.DBieClient):
    """Real retry loop, fake transport: no network, no real sleeps, reset is counted."""

    def __init__(self, session):
        super().__init__()
        self.session = session
        self.token, self.token_ts = "test-token", time.time()
        self.resets = 0

    def ensure_token(self) -> str:
        return str(self.token)

    def _reset_session(self):
        self.resets += 1


class RetryBehaviour(unittest.TestCase):
    def setUp(self):
        self._sleep = mock.patch.object(dbie_client.time, "sleep", lambda *_: None)
        self._sleep.start()
        self.addCleanup(self._sleep.stop)

    def test_recovers_from_a_waf_drop_without_giving_up(self):
        client = TestableClient(FakeSession(fails=3))
        out = client.call("dbie_test", {"body": {}})
        self.assertEqual(out["header"]["status"], "ok")
        self.assertEqual(client.session.calls, 4, "should have taken 4 attempts (3 failures)")

    def test_connection_errors_rebuild_the_connection_pool(self):
        client = TestableClient(FakeSession(fails=2))
        client.call("dbie_test", {"body": {}})
        self.assertEqual(client.resets, 2,
                         "each ConnectionError must reset the dead keep-alive pool")

    def test_gives_up_loudly_after_the_retry_budget(self):
        client = TestableClient(FakeSession(fails=99))
        with self.assertRaises(requests.ConnectionError):
            client.call("dbie_test", {"body": {}})
        self.assertEqual(client.session.calls, 6, "default budget is 6 attempts")

    def test_retry_window_survives_a_waf_outage_longer_than_15s(self):
        # The old settings were 3 attempts with backoff capped at 10s: a 14s total window.
        total = sum(dbie_client._backoff(a) for a in range(1, 6))
        self.assertGreaterEqual(total, 40.0,
                                f"retry window is only {total:.1f}s; a WAF drop outlasts it")
        self.assertLessEqual(total, 120.0, "window should not stall CI for minutes")

    def test_backoff_is_capped(self):
        self.assertLessEqual(dbie_client._backoff(20), 30.0)
        self.assertGreater(dbie_client._backoff(1), 0.0)


if __name__ == "__main__":
    unittest.main()
