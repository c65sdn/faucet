#!/usr/bin/env python3

"""Unit tests for the port-polling helpers in clib.mininet_test_base."""

from unittest import TestCase, main
from unittest import mock

from clib.mininet_test_base import FaucetTestBase


class WaitForTcpListenOrNoneTest(TestCase):
    """wait_for_tcp_listen_or_none must stop on first listen, else time out."""

    def _base(self, polls):
        base = FaucetTestBase.__new__(FaucetTestBase)
        responses = list(polls)

        def tcp_port_free(_host, _port, _ipv=4):
            return responses.pop(0) if responses else None

        base.tcp_port_free = tcp_port_free
        return base

    def test_listening_immediately(self):
        """A host already listening returns without sleeping"""
        base = self._base(["listening"])
        with mock.patch("clib.mininet_test_base.time.sleep") as sleep:
            self.assertTrue(base.wait_for_tcp_listen_or_none("h", 1))
        sleep.assert_not_called()

    def test_listens_after_delay(self):
        """A host that starts listening later still returns True"""
        base = self._base([None, None, "listening"])
        with mock.patch("clib.mininet_test_base.time.sleep") as sleep:
            self.assertTrue(base.wait_for_tcp_listen_or_none("h", 1))
        self.assertEqual(sleep.call_count, 2)

    def test_never_listening_times_out_false(self):
        """A host that never listens returns False after the timeout"""
        base = self._base([None, None, None])
        with mock.patch("clib.mininet_test_base.time.sleep") as sleep:
            self.assertFalse(base.wait_for_tcp_listen_or_none("h", 1, timeout=3))
        self.assertEqual(sleep.call_count, 2)


if __name__ == "__main__":
    main()
