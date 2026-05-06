#!/usr/bin/env python3

"""Test the barrier-aware send pipeline."""

# Copyright (C) 2015--2026 The Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# pylint: disable=protected-access
# Pylint can't infer the bound methods on a ValvesManager built via
# __new__ + manual attribute assignment, so it false-positives no-member
# on register_barrier/complete_barrier/cancel_barriers.
# pylint: disable=no-member

import logging
import threading
import time
import unittest
from collections import defaultdict

from faucet import valve_of
from faucet.valve_send import BarrierAwareSender
from faucet.valves_manager import ValvesManager


class FakeRyuDp:
    """Minimal stand-in for an os-ken Datapath."""

    def __init__(self, dp_id):
        """Initialise a fake datapath with monotonic xids and a sent log."""
        self.id = dp_id
        self._next_xid = 1000
        self._send_lock = threading.Lock()
        self.sent = []
        self.closed = False

    def set_xid(self, msg):
        """Assign and return the next xid for ``msg``."""
        with self._send_lock:
            xid = self._next_xid
            self._next_xid += 1
        msg.set_xid(xid)
        return xid

    def send_msg(self, msg):
        """Record ``msg`` in the sent log."""
        if msg.xid is None:
            self.set_xid(msg)
        with self._send_lock:
            self.sent.append(msg)
        return True

    def close(self):
        """Mark the channel closed."""
        self.closed = True


def _make_manager():
    """Return a ValvesManager initialised just enough to exercise the
    barrier-waiter API without needing real Faucet plumbing."""
    manager = ValvesManager.__new__(ValvesManager)
    manager._barrier_lock = threading.Lock()
    manager._barrier_waiters = defaultdict(dict)
    return manager


def _flow():
    """Return a placeholder OFPFlowMod to slot around barriers in tests."""
    return valve_of.flowmod(
        cookie=1,
        hard_timeout=0,
        idle_timeout=0,
        match_fields=None,
        out_port=None,
        table_id=0,
        inst=(),
        priority=0,
        command=valve_of.ofp.OFPFC_ADD,
        out_group=valve_of.ofp.OFPG_ANY,
    )


class BarrierAwareSenderTestCase(unittest.TestCase):
    """Verify the per-DP sender thread holds messages at each barrier."""

    def setUp(self):
        """Configure a logger that swallows expected error output."""
        self.logger = logging.getLogger("test_valve_send")
        self.logger.addHandler(logging.NullHandler())

    def _spawn(self, ryu_dp, manager, timeout=2.0):
        """Spawn a sender bound to ``ryu_dp`` and clean it up at teardown."""
        sender = BarrierAwareSender(
            ryu_dp, manager, self.logger, barrier_timeout=timeout
        )
        self.addCleanup(sender.stop)
        return sender

    def _wait_for_barrier(self, ryu_dp, deadline_s=1.0):
        """Block until ``ryu_dp`` has seen an OFPBarrierRequest, or fail."""
        deadline = time.monotonic() + deadline_s
        while time.monotonic() < deadline:
            with ryu_dp._send_lock:
                got_barrier = any(
                    isinstance(m, valve_of.parser.OFPBarrierRequest)
                    for m in ryu_dp.sent
                )
            if got_barrier:
                return
            time.sleep(0.01)
        self.fail("barrier never reached the wire")

    def test_post_barrier_msg_blocked_until_reply(self):
        """The post-barrier flow must not be sent before the reply lands."""
        ryu_dp = FakeRyuDp(0xDEADBEEF)
        manager = _make_manager()
        sender = self._spawn(ryu_dp, manager)
        sender.submit([_flow(), valve_of.barrier(), _flow()])
        self._wait_for_barrier(ryu_dp)

        # Give the worker a moment in case it's about to wrongly send post.
        time.sleep(0.05)
        with ryu_dp._send_lock:
            kinds = [type(m).__name__ for m in ryu_dp.sent]
        self.assertEqual(
            kinds,
            ["OFPFlowMod", "OFPBarrierRequest"],
            "post-barrier flow leaked through before reply",
        )

        with ryu_dp._send_lock:
            barrier_xid = next(
                m.xid
                for m in ryu_dp.sent
                if isinstance(m, valve_of.parser.OFPBarrierRequest)
            )
        manager.complete_barrier(ryu_dp.id, barrier_xid)

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            with ryu_dp._send_lock:
                if len(ryu_dp.sent) == 3:
                    break
            time.sleep(0.01)
        with ryu_dp._send_lock:
            self.assertEqual(len(ryu_dp.sent), 3)
            self.assertIsInstance(ryu_dp.sent[2], valve_of.parser.OFPFlowMod)
        self.assertFalse(ryu_dp.closed)

    def test_timeout_drops_channel(self):
        """If no reply arrives, sender must close the dp and stop draining."""
        ryu_dp = FakeRyuDp(0xCAFEBABE)
        manager = _make_manager()
        sender = self._spawn(ryu_dp, manager, timeout=0.1)
        sender.submit([_flow(), valve_of.barrier(), _flow()])

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not ryu_dp.closed:
            time.sleep(0.02)
        self.assertTrue(ryu_dp.closed, "expected channel close on timeout")
        with ryu_dp._send_lock:
            kinds = [type(m).__name__ for m in ryu_dp.sent]
        self.assertEqual(kinds, ["OFPFlowMod", "OFPBarrierRequest"])

    def test_cancel_barriers_releases_worker(self):
        """cancel_barriers must wake the worker quickly, not at the timeout."""
        ryu_dp = FakeRyuDp(0xFEEDFACE)
        manager = _make_manager()
        sender = self._spawn(ryu_dp, manager, timeout=10.0)
        sender.submit([_flow(), valve_of.barrier(), _flow()])
        self._wait_for_barrier(ryu_dp)

        before_cancel = time.monotonic()
        manager.cancel_barriers(ryu_dp.id)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            with ryu_dp._send_lock:
                if len(ryu_dp.sent) >= 3 or ryu_dp.closed:
                    break
            time.sleep(0.01)
        elapsed = time.monotonic() - before_cancel
        self.assertLess(elapsed, 1.0, "cancel did not unstick worker")

    def test_two_datapaths_no_xid_crosstalk(self):
        """Concurrent barriers on two datapaths must not collide on xids."""
        dp_a = FakeRyuDp(0xA000)
        dp_b = FakeRyuDp(0xB000)
        manager = _make_manager()
        sender_a = self._spawn(dp_a, manager, timeout=2.0)
        sender_b = self._spawn(dp_b, manager, timeout=2.0)
        sender_a.submit([_flow(), valve_of.barrier(), _flow()])
        sender_b.submit([_flow(), valve_of.barrier(), _flow()])

        deadline = time.monotonic() + 1.0
        barrier_a = barrier_b = None
        while time.monotonic() < deadline:
            barrier_a = next(
                (
                    m
                    for m in dp_a.sent
                    if isinstance(m, valve_of.parser.OFPBarrierRequest)
                ),
                None,
            )
            barrier_b = next(
                (
                    m
                    for m in dp_b.sent
                    if isinstance(m, valve_of.parser.OFPBarrierRequest)
                ),
                None,
            )
            if barrier_a is not None and barrier_b is not None:
                break
            time.sleep(0.01)
        self.assertIsNotNone(barrier_a)
        self.assertIsNotNone(barrier_b)
        self.assertIsNot(barrier_a, barrier_b)

        manager.complete_barrier(dp_b.id, barrier_b.xid)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and len(dp_b.sent) < 3:
            time.sleep(0.01)
        self.assertEqual(len(dp_b.sent), 3, "B did not progress past barrier")
        self.assertEqual(
            len(dp_a.sent),
            2,
            "A leaked past its barrier when B's reply arrived",
        )

        manager.complete_barrier(dp_a.id, barrier_a.xid)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and len(dp_a.sent) < 3:
            time.sleep(0.01)
        self.assertEqual(len(dp_a.sent), 3, "A did not progress past barrier")

    def test_no_barriers_passthrough(self):
        """A batch with no barriers should drain without ever blocking."""
        ryu_dp = FakeRyuDp(0x1234)
        manager = _make_manager()
        sender = self._spawn(ryu_dp, manager)
        sender.submit([_flow() for _ in range(5)])

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and len(ryu_dp.sent) < 5:
            time.sleep(0.01)
        self.assertEqual(len(ryu_dp.sent), 5)
        self.assertEqual(dict(manager._barrier_waiters), {})


class BarrierWaiterRegistryTestCase(unittest.TestCase):
    """Smaller direct exercise of the ValvesManager waiter API."""

    def setUp(self):
        """Build a stripped-down ValvesManager with only the waiter dict."""
        self.manager = _make_manager()

    def test_register_and_complete(self):
        """A registered waiter is signalled by complete_barrier."""
        event = self.manager.register_barrier(1, 7)
        self.manager.complete_barrier(1, 7)
        self.assertTrue(event.is_set())

    def test_complete_unknown_is_noop(self):
        """complete_barrier for an unknown xid must not raise."""
        self.manager.complete_barrier(1, 99)

    def test_cancel_releases_all(self):
        """cancel_barriers signals every waiter for the given dp_id only."""
        event1 = self.manager.register_barrier(1, 1)
        event2 = self.manager.register_barrier(1, 2)
        event3 = self.manager.register_barrier(2, 1)
        self.manager.cancel_barriers(1)
        self.assertTrue(event1.is_set())
        self.assertTrue(event2.is_set())
        self.assertFalse(event3.is_set())


if __name__ == "__main__":
    unittest.main()  # pytype: disable=module-attr
