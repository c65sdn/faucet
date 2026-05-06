Block-on-barrier
================

This document describes Faucet's barrier-aware send pipeline -- the
mechanism that pauses the controller after each ``OFPBarrierRequest``
until the matching ``OFPBarrierReply`` lands, instead of just queuing
the barrier and continuing. It supersedes the original "emit a barrier
and continue" behaviour, which was good enough under eventlet's
cooperative scheduling but not on os-ken's native (threading) hub.

Problem
-------

When Faucet pushes a config change it generates a list of
``OFPMeterMod`` / ``OFPGroupMod`` / ``OFPFlowMod`` messages. Those get
sorted into kinds by ``valve_of.valve_flowreorder()``, with an
``OFPBarrierRequest`` interleaved between kinds when the controller's
``USE_BARRIERS`` is true. The whole list is then handed off in order
to ``ryu_dp.send_msg()`` -- which simply queues each message on
os-ken's per-datapath ``send_q`` and returns. The ``_send_loop``
thread drains the queue and writes the bytes to the TCP socket
FIFO-style, so the datapath sees the messages in the right order on
the wire.

What that does **not** do is wait for OVS to actually acknowledge each
barrier before continuing. The OF spec only requires the switch to
*complete* the messages preceding a barrier before sending the
``OFPBarrierReply``; in particular it doesn't forbid the switch from
beginning to *process* messages that follow the barrier in parallel.
Userspace OVS in particular has been seen to admit an
``OFPT_FLOW_MOD`` whose ``OFPIT_METER`` instruction references a meter
installed earlier in the same batch, and reject it with
``OFPMMFC_INVALID_METER`` because the meter table commit hadn't landed
yet -- exactly the failure that ``FaucetUntaggedMeterModTest``
exercised once the eventlet hub stopped giving the implicit
cooperative-yield gap that masked the race.

Setting ``USE_BARRIERS = True`` interleaves barriers in the wire
stream, but does not by itself make the controller pause locally for
the reply before sending the next kind's messages. Genuine
pause-on-barrier semantics require the controller to stop pushing into
``send_q`` until it sees the matching ``OFPBarrierReply``.

Design
------

A worker-thread send pipeline, one thread per datapath. Two
constraints drive the shape:

1. ``Event.wait`` cannot run on the os-ken event-loop thread.
   ``os_ken.base.app_manager._event_loop`` dispatches every event for
   a Ryu app serially on a single thread. If a ``send_flows`` call
   parked there waiting for a reply, the ``EventOFPBarrierReply``
   handler -- which is the *only* code that can wake it -- could never
   run, and every barrier would time out.

2. The waiter must be in the per-datapath dict before
   ``send_msg`` returns, so a fast reply can find it. ``send_msg``
   returns as soon as bytes hit ``send_q``, and the receive path runs
   on its own thread; we cannot register the waiter after-the-fact.

The implementation therefore puts a daemon thread per datapath on the
controller side. The Faucet event handler hands a prepared message
list to the sender and returns immediately, leaving the os-ken event
loop free. The worker drains the batch, and on each
``OFPBarrierRequest`` it:

* assigns the xid itself (``ryu_dp.set_xid``) before submitting,
* registers a ``threading.Event`` against ``(dp_id, xid)`` in
  ``ValvesManager``,
* calls ``ryu_dp.send_msg`` to enqueue the barrier,
* parks on ``Event.wait(BARRIER_TIMEOUT)``.

The Faucet-app handler for ``ofp_event.EventOFPBarrierReply`` runs on
the os-ken loop thread, looks up ``(dp_id, xid)``, and ``Event.set()``
s the waiter. The handler does no other work, so the loop stays
responsive.

If a reply doesn't arrive inside ``BARRIER_TIMEOUT`` (default 5 s) the
worker logs the offence, calls ``ryu_dp.close()`` (the existing
reconnect/handshake path takes over and re-pushes config), and exits
the batch.

If the datapath disconnects while the worker is parked, the
``_datapath_disconnect`` handler calls
``ValvesManager.stop_sender(dp_id)``, which both releases all parked
waiters and stops the worker thread -- no 5 s sleep on the way out.

Component map
-------------

``faucet/valve_send.py`` (new)

  ``BarrierAwareSender`` -- per-DP daemon thread fed by
  ``queue.Queue``. ``submit(ofmsgs)`` enqueues an already-prepared
  (reordered) list. The worker drains in order, parks on each
  barrier, and exits cleanly when ``stop()`` is called.

``faucet/valves_manager.py``

  Owns the senders (``self._senders`` keyed by ``dp_id``) and the
  barrier-waiter registry (``self._barrier_waiters``). API:

  * ``submit_to_sender(valve, ryu_dp, ofmsgs)`` -- lazily creates the
    sender and dispatches.
  * ``stop_sender(dp_id)`` -- on disconnect: cancel waiters, stop
    thread, drop the entry.
  * ``register_barrier(dp_id, xid)`` / ``complete_barrier(dp_id,
    xid)`` / ``cancel_barriers(dp_id)`` / ``discard_barrier(dp_id,
    xid)`` -- the waiter primitives.

``faucet/valve.py``

  ``Valve.send_flows`` now calls ``valves_manager.submit_to_sender``
  with the reordered list instead of writing to ``ryu_dp.send_msg``
  inline. The ``valves_manager=None`` fallback keeps the
  ``valve_test_lib`` path that drives ``prepare_send_flows``
  directly working unchanged.

``faucet/faucet.py``

  * ``barrier_reply_handler`` -- ``EventOFPBarrierReply,
    MAIN_DISPATCHER`` -- forwards to ``valves_manager.complete_barrier``.
  * ``_datapath_disconnect`` -- calls ``stop_sender`` before delegating
    to the existing valve disconnect path.
  * ``_send_flow_msgs`` -- passes ``valves_manager`` through to
    ``valve.send_flows``.

``faucet/valve_of.py``

  ``barrier()`` no longer ``@functools.lru_cache``-d. The send path
  mutates the request (xid, datapath) per use, so a cached singleton
  was only safe by accident.

``valve_flowreorder()`` is unchanged: it already inserts barriers
between kinds when ``use_barriers`` is true.

Tests
-----

Unit, in ``tests/unit/faucet/test_valve_send.py``:

* ordering -- post-barrier message held until ``complete_barrier``;
* timeout -- worker calls ``ryu_dp.close()`` and stops draining;
* cancel-on-disconnect -- ``cancel_barriers`` releases the worker
  immediately;
* two-datapath isolation -- replies route to the correct waiter, and
  one switch's barrier doesn't progress past the other's;
* no-barrier batch -- passes through without ever touching the waiter
  registry.

Integration: the three meter tests
(``FaucetUntaggedApplyMeterTest``, ``FaucetUntaggedMeterAddTest``,
``FaucetUntaggedMeterModTest``) **remain skipped** -- see below.

Limit: OVS userspace barrier vs. meter table
--------------------------------------------

Block-on-barrier is necessary for ordering correctness against
spec-compliant OF switches. It is **not** sufficient for the
``OFPMMFC_INVALID_METER`` race that the three meter integration tests
exercise on userspace OVS. Empirically -- with a debug log added to
the sender to record the round-trip on every barrier -- we observed:

* The controller sent the meter ADD (``OFPMC_ADD``) followed by a
  ``OFPBarrierRequest``.
* OVS replied to that barrier in 0.000s -- 0.030s.
* The waiter on the controller side unblocked and sent the next
  message kind: a ``OFPFlowMod`` whose ``OFPIT_METER`` instruction
  references that meter.
* OVS rejected that flow_mod with
  ``OFPMMFC_INVALID_METER``.

In other words, the barrier reply arrived *before* the meter table
commit had landed in OVS userspace's internal data structures. The OF
spec is unambiguous (the switch must complete preceding messages
before sending the reply); userspace OVS is treating the meter
pipeline as outside the barrier fence.

Block-on-barrier is the correct controller-side fix, and it does
gate every other kind of cross-table ordering hazard, but for the
specific OVS userspace + meter combination the only options are:

* skip the meter integration tests (current behaviour, with this
  document as the breadcrumb);
* run those tests against the OVS kernel datapath, which doesn't have
  the same separation; or
* fix OVS userspace to fence meter operations under the barrier
  contract -- the long-term resolution.

The diagnostic that confirmed this lives at ``logger.debug`` in
``BarrierAwareSender._send_barrier``; raise the faucet logger to
``DEBUG`` if you need to re-run the trace.

Risks and trade-offs
--------------------

* **Latency.** Each batch of OFMsgs now includes a synchronous round
  trip to the switch per barrier. Most config reloads have ~5
  barriers (config / deletes / tfm / groupadd / meteradd /
  flowaddmod), so reload latency grows by roughly 5 RTTs to the
  switch. On a 1 ms LAN that's nothing; on a stretched WAN it could
  be tens of ms. Acceptable for correctness; tune ``BARRIER_TIMEOUT``
  if real RTTs approach it.

* **Thread per datapath.** Daemon threads, lazily created, stopped on
  disconnect. The os-ken event loop never blocks on barrier waits, so
  switches stay independent.

* **``USE_BARRIERS=False`` callers.** Such switches just don't have
  ``OFPBarrierRequest`` instances in their batches, so the worker
  drains them as a passthrough -- no special-casing needed in the
  sender.

Out of scope
------------

* Changing ``valve_flowreorder()``'s output. Barriers are emitted in
  the right places once ``USE_BARRIERS = True``; the work is on the
  consumer side.

* Replacing os-ken's ``send_q`` semantics. The TCP-FIFO ordering it
  gives is fine, the missing piece was purely the controller-side
  "did the switch finish?" rendezvous.

* Per-message acknowledgement (e.g. requesting a reply for every
  ``METER_MOD``). Barriers are the OF-standard rendezvous; per-msg
  acks would be a much larger redesign.
