Dropping os-ken
===============

Why
---

os-ken is upstream-shedding surface faucet depends on, roughly once per
major release, and each shed has cost us a fix:

===========  =======================================  ====================================
os-ken       What went away                           What it cost us
===========  =======================================  ====================================
3.0          eventlet demoted, native hub added       ``94f01c28``, ``eeab08f9``, and the
                                                      whole block-on-barrier redesign
                                                      (``docs/block_on_barrier.rst``)
4.0          ``os_ken.cmd`` / ``osken-manager``       ``6ce083b2`` -- 300 lines of
                                                      ``faucet/__main__.py`` is now an
                                                      inlined copy of ``cmd/manager.py``
(earlier)    ``os_ken.app.wsgi``                      ``ofctl_rest/wsgi.py`` -- 309 lines
                                                      vendored in tree
===========  =======================================  ====================================

os-ken also drags oslo.config, eventlet, netaddr and packaging into
faucet's runtime dependency tree; faucet needs none of them on their own
merits.

The pattern to notice: **every break has been in the runtime/framework
layer, none in the wire layer.** OpenFlow 1.3 and the ethernet/IP packet
formats have been frozen since 2012 and upstream does not touch them.

Measured surface
----------------

139 ``os_ken`` references across 30 files: 17 modules under ``faucet/``,
3 under ``clib/``, 2 under ``ofctl_rest/``, 8 under ``tests/``. Faucet
uses 195 distinct ``ofproto_v1_3`` constants and ~50 ``ofproto_v1_3_parser``
classes.

The OF1.3-only import closure of everything faucet touches is 57 modules
and 24,426 lines, which splits cleanly by churn risk:

==========================  =====  ===============================  =========  =========
Layer                       LOC    os-ken modules                   Churns?    Replace
==========================  =====  ===============================  =========  =========
OF1.3 wire protocol         8,503  ``ofproto_v1_3``,                no         ~7,000
                                   ``ofproto_v1_3_parser``,
                                   ``ofproto_parser``,
                                   ``oxm_fields``, ``ether``,
                                   ``inet``, ``ofproto_common``
Packet library              5,944  ``lib/packet/*`` (13 protos),    no         ~4,700
                                   ``addrconv``, ``mac``,
                                   ``stringify``, ``type_desc``
Nicira extensions           5,168  ``nx_actions``, ``nx_match``,    no         ~350
                                   ``nicira_ext``
ofctl helpers               1,656  ``ofctl_v1_3``, ``ofctl_utils``  no         ~200 +
                                                                               ~700 test
App framework               1,562  ``app_manager``, ``handler``,    **yes**    ~400
                                   ``event``, ``ofp_event``,
                                   ``dpset``, ``ofp_handler``
hub / cfg / log             1,037  ``lib/hub``, ``cfg``,            **yes**    ~200
                                   ``flags``, ``log``, ``utils``
OF channel                    556  ``controller/controller``        **yes**    ~350
==========================  =====  ===============================  =========  =========

3,155 lines of that closure -- 13% -- account for 100% of the historical
breakage.

Proposal
--------

A top-level ``c65of`` package alongside ``faucet/`` and ``clib/``, shipped
in the same distribution. Top-level, not under ``faucet/``, because
``tests/run_unit_tests.sh`` runs ``coverage --source faucet/`` at
``--fail-under=91``; ported wire-format code has no business competing
with faucet's own coverage budget.

Module layout mirrors the os-ken paths it replaces, so each call site
changes by exactly one import line::

    c65of/ofproto/__init__.py   OF1.3 constants          (ofproto_v1_3)
    c65of/ofproto/parser.py     OF1.3 messages           (ofproto_v1_3_parser)
    c65of/ofproto/base.py       MsgBase, StringifyMixin, ofp_msg_from_jsondict
    c65of/ofproto/nx.py         NXActionCT/NAT/CTClear + ct_* OXM
    c65of/ofproto/ether.py      ether, inet
    c65of/packet/               11 protocols + packet, stream_parser
    c65of/lib/                  addrconv, mac, stringify, type_desc
    c65of/ofctl.py              to_match_*, OFCtlUtil, mod_meter_entry
    c65of/app.py                OFApp base, set_ev_cls, event dispatch
    c65of/channel.py            OF listener, Datapath, dpset

Both projects are Apache-2.0, so the frozen-format layers are a
license-clean verbatim port with copyright headers and NOTICE preserved --
the same move already made for ``ofctl_rest/wsgi.py``.

What was done
=============

All of it, in one pass rather than the phased retreat the analysis allowed
for. c65of covers the OpenFlow 1.3 wire protocol, the packet formats a
controller parses, the application framework, the OpenFlow channel and the
Nicira conntrack actions, and has no runtime dependencies at all.

Wire formats are declared rather than hand written: a class states its struct
layout and a codec compiles the constructor, the packer and the JSON dict
form, so only structures with a variable length tail need any code. That is
why os-ken's OF1.3 parser is 6,676 lines and c65of's equivalent is not.

os-ken remains a **test** dependency of c65of, used as a differential oracle:
same bytes out, same values back, same JSON dict, same ``str()``. That is
what made this a verifiable port rather than a reimplementation to be
eyeballed.

What the differential tests did not catch
=========================================

Eight bugs survived c65of's own passing tests. Three were found by running
faucet end to end:

* The datapath was not named before its features reply reached observers.
  os-ken sets the id inside its own handler and gets away with it because it
  runs that handler inline on the read thread; c65of runs every observer
  concurrently, so faucet raced it, saw ``id`` as ``None``, and dropped the
  channel. Intermittent, and fatal.
* A message queued immediately before ``close()`` was dropped, because the
  send loop tested the datapath state before dequeuing. A switch offering an
  incompatible version got a bare disconnect instead of the error explaining
  why.
* An application given as a file path would not load, which is how the
  integration tests start ``ofctl_rest``.

Five more were found only by driving faucet against real Open vSwitch:

* A switch could not connect at all. Open vSwitch opens with a hello
  announcing OpenFlow 1.5 and expects to be negotiated down to 1.3; the
  hello was rejected at the parser. Every test here sent a 1.3 hello, so
  every test passed.
* Message events carried no timestamp, so every packet-in raised
  ``AttributeError`` inside the handler.
* The controller started silently, and faucet judges a controller healthy
  only once its log is non-empty -- so a working controller with a connected
  switch and a programmed pipeline looked dead.
* An address written with a prefix length lost its host bits, so the two
  spellings of the same match disagreed with each other.
* A malformed address raised ``OSError`` where config validation catches
  ``ValueError``, crashing the parser instead of reporting the bad address.

The lesson is not that differential testing was the wrong tool -- it is what
made the 24,000 line port tractable -- but that it only ever compares one
implementation against another on inputs someone thought to write down. It
cannot see a race between two observers, a launch path nothing exercises, or
a switch that opens the conversation differently from the way the tests do.

Two of those tests were worse than absent: they asserted the behaviour the
implementation already had. The hello tests all sent version 1.3, and the
prefix tests all used canonical networks. A test written to confirm an
assumption cannot falsify it.

Latent bugs this exposed in faucet
==================================

* ``netaddr``, ``routes`` and ``six`` were imported directly but never
  declared; all three only resolved because os-ken pulled them in.
* ``clib/valve_test_lib.py`` read ``icmp_pkt.type_`` on an ICMPv4 packet,
  which raises ``AttributeError`` against os-ken. os-ken stores
  ``icmp.icmp.type`` but ``icmpv6.icmpv6.type_``; c65of is consistent, and
  the rename fixes the call site.
* ``Faucet._export_ryu_config`` read ``self.CONF``, which only exists under
  oslo.config. It runs from ``start()``, so no unit test reached it.

What remains
============

``debian/control`` names ``python3-c65of``, which nobody has packaged, in the
same way ``python3-beka`` and ``python3-chewie`` are named but not packaged.
The Debian build needs that before it can work.
