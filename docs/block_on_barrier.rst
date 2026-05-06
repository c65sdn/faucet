Block-on-barrier follow-up
==========================

This is an engineering plan for replacing the current
"emit a barrier and continue" behaviour with a "wait for the barrier
ack before continuing" behaviour in Faucet's OFP send path. It
documents the follow-up work that the eventlet-removal PR
(``c65sdn/faucet#401``) deliberately did not take on.

Problem
-------

When Faucet pushes a config change it generates a list of
``OFPMeterMod`` / ``OFPGroupMod`` / ``OFPFlowMod`` messages. Those get
sorted into kinds by ``valve_of.valve_flowreorder()``, with an
``OFPBarrierRequest`` interleaved between kinds when the controller's
``USE_BARRIERS`` is true (set on ``OVSValve`` /
``OVSTfmValve`` in ``c65sdn/faucet#401``). The whole list is then
handed off in order to ``ryu_dp.send_msg()`` -- which simply queues
each message on os-ken's per-datapath ``send_q`` and returns. The
``_send_loop`` thread drains the queue and writes the bytes to the
TCP socket FIFO-style, so the datapath sees the messages in the right
order on the wire.

What the current code does **not** do is wait for OVS to actually
acknowledge each barrier before continuing. The OF spec only
requires the switch to *complete* the messages preceding a barrier
before sending the ``OFPBarrierReply``; in particular it doesn't
forbid the switch from beginning to *process* messages that follow
the barrier in parallel. Userspace OVS in particular has been seen
to admit a ``OFPT_FLOW_MOD`` whose ``OFPIT_METER`` instruction
references a meter installed earlier in the same batch, and reject it
with ``OFPMMFC_INVALID_METER`` because the meter table commit hadn't
landed yet -- exactly the failure that
``FaucetUntaggedMeterModTest.test_untagged`` exercised once the
eventlet hub stopped giving the implicit cooperative-yield gap that
masked the race.

Setting ``USE_BARRIERS = True`` reduces but does not eliminate the
window: the barrier is in the wire stream, but the controller does
not pause locally for the reply before sending the next kind's
messages. Genuine pause-on-barrier semantics require the controller
to stop pushing into ``send_q`` until it sees the matching
``OFPBarrierReply``.

Proposed fix
------------

A "barrier-aware" send pipeline. The contract:

* ``valve.send_flows()`` keeps producing the same ordered list, with
  ``OFPBarrierRequest`` markers between kinds.
* When the send loop encounters a barrier, it records the request's
  ``xid`` and **blocks** on a ``threading.Event`` that fires when the
  matching reply lands.
* An ``OFPBarrierReply`` handler (`@set_ev_cls` on
  ``ofp_event.EventOFPBarrierReply``) looks up the xid in a
  per-datapath dict and ``set()`` s the event.
* If the reply takes longer than ``BARRIER_TIMEOUT`` (suggested 5 s)
  the controller logs the offence and drops the connection -- the
  switch reconnect/handshake path already handles re-pushing config.

Implementation outline
----------------------

``faucet/faucet.py``

  * Register ``barrier_reply_handler`` for
    ``ofp_event.EventOFPBarrierReply, MAIN_DISPATCHER``. The handler
    looks up ``ryu_event.msg.xid`` against
    ``valves_manager.barrier_waiters[ryu_dp.id]`` and pops/sets the
    event.

``faucet/valves_manager.py``

  * Add ``self.barrier_waiters: dict[int, dict[int, threading.Event]]``,
    keyed by ``dp_id`` then ``xid``. Entries are added by the send
    side and removed by the reply handler.

``faucet/valve.py``

  * In ``send_flows()``, replace the inner ``ryu_send_flows`` loop
    with a barrier-aware variant::

        for flow_msg in self.prepare_send_flows(local_flow_msgs):
            flow_msg.datapath = ryu_dp
            ryu_dp.send_msg(flow_msg)
            if isinstance(flow_msg, parser.OFPBarrierRequest):
                self._wait_barrier(ryu_dp, flow_msg.xid)

  * ``_wait_barrier`` registers a ``threading.Event`` against the
    barrier's xid before the send completes, calls ``Event.wait(
    timeout=BARRIER_TIMEOUT)``, and tears down (close socket,
    schedule reconnect) on miss.

  * Subtlety: ``msg.xid`` is assigned inside ``Datapath.send_msg``
    (``set_xid()``), not when we construct the ``OFPBarrierRequest``,
    so ``_wait_barrier`` must read it *after* ``send_msg`` returns,
    and the registration must happen before that send returns to
    avoid a race where the reply arrives before the waiter is in the
    dict. The cleanest way is to ``set_xid`` ourselves before
    ``send_msg``.

``faucet/valve_of.py``

  * ``valve_flowreorder()`` already inserts ``barrier()`` between
    kinds. No change needed.

Test plan
---------

* New unit test: feed ``send_flows()`` a list with a barrier
  ``OFPBarrierRequest`` in the middle, mock ``ryu_dp.send_msg`` so
  the second post-barrier ``send_msg`` blocks until the test thread
  fires the matching ``OFPBarrierReply`` event. Verify the post-
  barrier message wasn't sent before the reply.

* New unit test: never fire the reply, verify ``send_flows`` aborts
  the channel after ``BARRIER_TIMEOUT``.

* Integration regression: ``FaucetUntaggedMeterModTest.test_untagged``
  passing under the native hub *without* the
  ``USE_BARRIERS = True`` workaround on ``OVSValve``. Once
  block-on-barrier lands, that ``USE_BARRIERS`` flip can be reverted.

* Soak test: run the integration matrix repeatedly under both
  eventlet and native hubs to confirm no per-batch performance
  regression. ``BARRIER_TIMEOUT`` must be high enough that healthy
  switches never hit it under load.

Risks and trade-offs
--------------------

* **Latency.** Each batch of OFMsgs now includes a synchronous round
  trip to the switch per barrier. Most config reloads have ~5
  barriers (config / deletes / tfm / groupadd / meteradd /
  flowaddmod), so reload latency grows by roughly 5 RTTs to the
  switch. On a 1 ms LAN that's nothing, on a stretched WAN it could
  be tens of ms. Acceptable for correctness.

* **Liveness.** Sitting in ``Event.wait`` blocks the event loop
  thread, so during a barrier wait Faucet does not progress *any*
  other event for that datapath. ``BARRIER_TIMEOUT`` puts a ceiling
  on the damage; combined with the existing controller-disconnect
  path on timeout this is comparable to the current "lose the switch
  and reconnect" failure mode for any other unresponsive op. Worth
  raising the alarm bell explicitly though -- the current code
  doesn't have any operation that can park the event loop.

* **Multiple datapaths.** os-ken dispatches events serially per app,
  not per datapath. A barrier on switch A blocks the loop and
  delays event delivery to switch B. If that becomes a problem the
  fix is to spawn a thread per ``send_flows`` invocation that owns
  the barrier wait, which is more code but isolates failures.

* **``USE_BARRIERS=False`` callers.** ``Valve`` /
  ``TfmValve`` have ``USE_BARRIERS = True`` already.
  ``OVSValve``/``OVSTfmValve`` were ``False`` historically and are
  now ``True`` (PR #401). If we expose new switch classes that
  legitimately want no barriers, the new send loop must skip the
  wait for them.

Out of scope
------------

* Changing ``valve_flowreorder()``'s output. Barriers are already
  emitted in the right places once ``USE_BARRIERS = True``; the work
  is on the consumer side.

* Replacing os-ken's ``send_q`` semantics. The TCP-FIFO ordering it
  gives is fine, the missing piece is purely the controller-side
  "did the switch finish?" rendezvous.

* Per-message acknowledgement (e.g. requesting a reply for every
  ``METER_MOD``). Barriers are the OF-standard rendezvous; per-msg
  acks would be a much larger redesign.
