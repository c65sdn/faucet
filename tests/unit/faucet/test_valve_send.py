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

import logging
import threading
import time
import unittest

from faucet import valve_of
from faucet.valve_send import BarrierAwareSender
from faucet.valves_manager import ValvesManager


class FakeRyuDp:
    """Minimal stand-in for an os-ken Datapath."""

    def __init__(self, dp_id):
        self.id = dp_id
        self._next_xid = 1000
        self._send_lock = threading.Lock()
        self.sent = []
        self.closed = False
        # Optional hook fired (with the msg) at the start of each send_msg
        # call -- lets a test suspend the sender thread mid-batch.
        self.on_send = None

    def set_xid(self, msg):
        with self._send_lock:
            xid = self._next_xid
            self._next_xid += 1
        msg.set_xid(xid)
        return xid

    def send_msg(self, msg):
        if self.on_send is not None:
            self.on_send(msg)
        if msg.xid is None:
            self.set_xid(msg)
        with self._send_lock:
            self.sent.append(msg)
        return True

    def close(self):
        self.closed = True


class _StubValvesManager:
    """Just the barrier-waiter API, no Faucet plumbing."""

    def __init__(self):
        self.real = ValvesManager.__new__(ValvesManager)
        # Initialise just the barrier-related attributes the sender uses.
        self.real._barrier_lock = threading.Lock()
        from collections import defaultdict

        self.real._barrier_waiters = defaultdict(dict)

    def register_barrier(self, dp_id, xid):
        return self.real.register_barrier(dp_id, xid)

    def complete_barrier(self, dp_id, xid):
        self.real.complete_barrier(dp_id, xid)

    def discard_barrier(self, dp_id, xid):
        self.real.discard_barrier(dp_id, xid)

    def cancel_barriers(self, dp_id):
        self.real.cancel_barriers(dp_id)


def _flow():
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

    def setUp(self):
        self.logger = logging.getLogger("test_valve_send")
        self.logger.addHandler(logging.NullHandler())

    def _make(self, ryu_dp, vm, timeout=2.0):
        sender = BarrierAwareSender(ryu_dp, vm, self.logger, barrier_timeout=timeout)
        self.addCleanup(sender.stop)
        return sender

    def test_post_barrier_msg_blocked_until_reply(self):
        """The post-barrier flow must not be sent before the reply lands."""
        ryu_dp = FakeRyuDp(0xDEADBEEF)
        vm = _StubValvesManager()
        sender = self._make(ryu_dp, vm)
        pre = _flow()
        post = _flow()
        sender.submit([pre, valve_of.barrier(), post])

        # Wait for the barrier to be sent. After that, the worker should
        # be parked waiting for the reply -- post must NOT be sent yet.
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            with ryu_dp._send_lock:
                got_barrier = any(
                    isinstance(m, valve_of.parser.OFPBarrierRequest)
                    for m in ryu_dp.sent
                )
            if got_barrier:
                break
            time.sleep(0.01)
        self.assertTrue(got_barrier, "barrier never reached the wire")

        # Give the worker a moment in case it's about to wrongly send post.
        time.sleep(0.05)
        with ryu_dp._send_lock:
            kinds = [type(m).__name__ for m in ryu_dp.sent]
        self.assertEqual(
            kinds,
            ["OFPFlowMod", "OFPBarrierRequest"],
            "post-barrier flow leaked through before reply",
        )

        # Find the barrier xid and complete it.
        with ryu_dp._send_lock:
            barrier_xid = next(
                m.xid
                for m in ryu_dp.sent
                if isinstance(m, valve_of.parser.OFPBarrierRequest)
            )
        vm.complete_barrier(ryu_dp.id, barrier_xid)

        # Now post should land.
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
        vm = _StubValvesManager()
        sender = self._make(ryu_dp, vm, timeout=0.1)
        pre = _flow()
        post = _flow()
        sender.submit([pre, valve_of.barrier(), post])

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not ryu_dp.closed:
            time.sleep(0.02)
        self.assertTrue(ryu_dp.closed, "expected channel close on timeout")
        with ryu_dp._send_lock:
            kinds = [type(m).__name__ for m in ryu_dp.sent]
        self.assertEqual(kinds, ["OFPFlowMod", "OFPBarrierRequest"])

    def test_cancel_barriers_releases_worker(self):
        """cancel_barriers must wake the worker so it doesn't sit out the
        timeout waiting for a reply that will never arrive."""
        ryu_dp = FakeRyuDp(0xFEEDFACE)
        vm = _StubValvesManager()
        sender = self._make(ryu_dp, vm, timeout=10.0)
        pre = _flow()
        post = _flow()
        sender.submit([pre, valve_of.barrier(), post])

        # Wait until the barrier has been sent (worker now blocked).
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            with ryu_dp._send_lock:
                if any(
                    isinstance(m, valve_of.parser.OFPBarrierRequest)
                    for m in ryu_dp.sent
                ):
                    break
            time.sleep(0.01)

        before_cancel = time.monotonic()
        vm.cancel_barriers(ryu_dp.id)
        # Worker treats the wake as success and continues. Either it
        # sends the post message or exits cleanly within a few ms --
        # either is fine, the requirement is *no* 10s wait.
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            with ryu_dp._send_lock:
                if len(ryu_dp.sent) >= 3 or ryu_dp.closed:
                    break
            time.sleep(0.01)
        elapsed = time.monotonic() - before_cancel
        self.assertLess(elapsed, 1.0, "cancel did not unstick worker")

    def test_two_datapaths_no_xid_crosstalk(self):
        """Concurrent barriers on two datapaths must not collide on
        xids -- the chief regression we get from dropping the cached
        OFPBarrierRequest singleton."""
        dp_a = FakeRyuDp(0xA000)
        dp_b = FakeRyuDp(0xB000)
        vm = _StubValvesManager()
        sender_a = self._make(dp_a, vm, timeout=2.0)
        sender_b = self._make(dp_b, vm, timeout=2.0)

        sender_a.submit([_flow(), valve_of.barrier(), _flow()])
        sender_b.submit([_flow(), valve_of.barrier(), _flow()])

        # Wait for both barriers to hit the wire.
        deadline = time.monotonic() + 1.0
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
        # Different instances and -- because dp_a and dp_b each issue
        # their own xids -- no expectation that the values differ; what
        # matters is replies route to the right waiter.
        self.assertIsNot(barrier_a, barrier_b)

        # Reply on B first; A must still be parked.
        vm.complete_barrier(dp_b.id, barrier_b.xid)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and len(dp_b.sent) < 3:
            time.sleep(0.01)
        self.assertEqual(len(dp_b.sent), 3, "B did not progress past barrier")
        # A still pending.
        self.assertEqual(
            len(dp_a.sent),
            2,
            "A leaked past its barrier when B's reply arrived",
        )

        vm.complete_barrier(dp_a.id, barrier_a.xid)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and len(dp_a.sent) < 3:
            time.sleep(0.01)
        self.assertEqual(len(dp_a.sent), 3, "A did not progress past barrier")

    def test_no_barriers_passthrough(self):
        """A batch with no barriers should drain without ever touching
        the waiter dict."""
        ryu_dp = FakeRyuDp(0x1234)
        vm = _StubValvesManager()
        sender = self._make(ryu_dp, vm)
        flows = [_flow() for _ in range(5)]
        sender.submit(flows)

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and len(ryu_dp.sent) < 5:
            time.sleep(0.01)
        self.assertEqual(len(ryu_dp.sent), 5)
        # No waiters were ever registered.
        self.assertEqual(dict(vm.real._barrier_waiters), {})


class BarrierWaiterRegistryTestCase(unittest.TestCase):
    """Smaller direct exercise of the ValvesManager waiter API."""

    def setUp(self):
        self.vm = _StubValvesManager().real

    def test_register_and_complete(self):
        ev = self.vm.register_barrier(1, 7)
        self.vm.complete_barrier(1, 7)
        self.assertTrue(ev.is_set())

    def test_complete_unknown_is_noop(self):
        # Should not raise even if no waiter is registered.
        self.vm.complete_barrier(1, 99)

    def test_cancel_releases_all(self):
        ev1 = self.vm.register_barrier(1, 1)
        ev2 = self.vm.register_barrier(1, 2)
        ev3 = self.vm.register_barrier(2, 1)
        self.vm.cancel_barriers(1)
        self.assertTrue(ev1.is_set())
        self.assertTrue(ev2.is_set())
        self.assertFalse(ev3.is_set())


if __name__ == "__main__":
    unittest.main()  # pytype: disable=module-attr
