#!/usr/bin/env python3

"""Test the ofctl_rest application's OpenFlow 1.3 JSON rendering.

``OSKEN`` holds values captured from os-ken 4.2.2's ``lib.ofctl_v1_3`` on these
same inputs: the contract the vendored ofctl must meet, frozen rather than
recomputed. Regenerating them from ofctl or c65of would assert nothing.
"""

# Copyright (C) 2026 The c65sdn Contributors
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

import importlib.util
import logging
import os
import unittest

from c65of import ofproto as c65_ofproto
from c65of.ofproto import parser as c65_parser

# pylint: disable=too-many-lines  # most of the module is the golden table

DPID = 0xDEADBEEF

# The deliberately invalid inputs are expected to warn.
logging.disable(logging.CRITICAL)


def _load_ofctl():
    """Import ofctl_rest/ofctl.py, which is not on the path as a package."""
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        os.pardir,
        os.pardir,
        os.pardir,
        "ofctl_rest",
        "ofctl.py",
    )
    spec = importlib.util.spec_from_file_location("ofctl_rest_ofctl", path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ofctl = _load_ofctl()

# Captured from os-ken 4.2.2; see the module docstring before editing.
OSKEN = {
    "desc_stats": {
        "3735928559": {
            "mfr_desc": "mfr",
            "hw_desc": "hw",
            "sw_desc": "sw",
            "serial_num": "serial",
            "dp_desc": "dp",
        }
    },
    "port_desc": {
        "3735928559": [
            {
                "hw_addr": "0e:00:00:00:00:01",
                "name": "port1",
                "config": 0,
                "state": 4,
                "curr": 2080,
                "advertised": 2080,
                "supported": 2080,
                "peer": 0,
                "curr_speed": 10000000,
                "max_speed": 10000000,
                "port_no": 1,
            },
            {
                "hw_addr": "0e:00:00:00:00:02",
                "name": "br0",
                "config": 1,
                "state": 1,
                "curr": 0,
                "advertised": 0,
                "supported": 0,
                "peer": 0,
                "curr_speed": 0,
                "max_speed": 0,
                "port_no": "LOCAL",
            },
        ]
    },
    "port_desc_not_to_user": {
        3735928559: [
            {
                "hw_addr": "0e:00:00:00:00:01",
                "name": "port1",
                "config": 0,
                "state": 4,
                "curr": 2080,
                "advertised": 2080,
                "supported": 2080,
                "peer": 0,
                "curr_speed": 10000000,
                "max_speed": 10000000,
                "port_no": 1,
            },
            {
                "hw_addr": "0e:00:00:00:00:02",
                "name": "br0",
                "config": 1,
                "state": 1,
                "curr": 0,
                "advertised": 0,
                "supported": 0,
                "peer": 0,
                "curr_speed": 0,
                "max_speed": 0,
                "port_no": 4294967294,
            },
        ]
    },
    "port_stats": {
        "3735928559": [
            {
                "rx_packets": 2,
                "tx_packets": 3,
                "rx_bytes": 4,
                "tx_bytes": 5,
                "rx_dropped": 6,
                "tx_dropped": 7,
                "rx_errors": 8,
                "tx_errors": 9,
                "rx_frame_err": 10,
                "rx_over_err": 11,
                "rx_crc_err": 12,
                "collisions": 13,
                "duration_sec": 14,
                "duration_nsec": 15,
                "port_no": 1,
            },
            {
                "rx_packets": 2,
                "tx_packets": 3,
                "rx_bytes": 4,
                "tx_bytes": 5,
                "rx_dropped": 6,
                "tx_dropped": 7,
                "rx_errors": 8,
                "tx_errors": 9,
                "rx_frame_err": 10,
                "rx_over_err": 11,
                "rx_crc_err": 12,
                "collisions": 13,
                "duration_sec": 14,
                "duration_nsec": 15,
                "port_no": 2,
            },
        ]
    },
    "table_stats": {
        "3735928559": [
            {"active_count": 1, "lookup_count": 2, "matched_count": 3, "table_id": 0},
            {"active_count": 4, "lookup_count": 5, "matched_count": 6, "table_id": 1},
        ]
    },
    "flow_stats": {
        "3735928559": [
            {
                "priority": 100,
                "cookie": 24301,
                "idle_timeout": 0,
                "hard_timeout": 0,
                "byte_count": 13,
                "duration_sec": 10,
                "duration_nsec": 11,
                "packet_count": 12,
                "length": 200,
                "flags": 0,
                "actions": [
                    "OUTPUT:2",
                    "SET_FIELD: {eth_dst:0e:00:00:00:00:02}",
                    "POP_VLAN",
                    "GROUP:7",
                    "SET_QUEUE:3",
                    {"WRITE_ACTIONS": ["DEC_NW_TTL"]},
                    "CLEAR_ACTIONS",
                    "GOTO_TABLE:3",
                    "WRITE_METADATA:0x1234/0xffff",
                    "METER:5",
                ],
                "match": {
                    "in_port": 1,
                    "dl_dst": "0e:00:00:00:00:01",
                    "dl_type": 2048,
                    "dl_vlan": "0x1064/0x1fff",
                    "nw_proto": 6,
                    "nw_src": "10.0.0.0/255.0.0.0",
                    "tp_dst": 443,
                },
                "table_id": 1,
            },
            {
                "priority": 1,
                "cookie": 0,
                "idle_timeout": 0,
                "hard_timeout": 0,
                "byte_count": 0,
                "duration_sec": 1,
                "duration_nsec": 2,
                "packet_count": 0,
                "length": 80,
                "flags": 0,
                "actions": [],
                "match": {},
                "table_id": 1,
            },
        ]
    },
    "flow_stats_priority_filter": {
        "3735928559": [
            {
                "priority": 1,
                "cookie": 0,
                "idle_timeout": 0,
                "hard_timeout": 0,
                "byte_count": 0,
                "duration_sec": 1,
                "duration_nsec": 2,
                "packet_count": 0,
                "length": 80,
                "flags": 0,
                "actions": [],
                "match": {},
                "table_id": 1,
            }
        ]
    },
    "aggregate_flow_stats": {
        "3735928559": [{"packet_count": 1, "byte_count": 2, "flow_count": 3}]
    },
    "queue_stats": {
        "3735928559": [
            {
                "duration_nsec": 7,
                "duration_sec": 6,
                "port_no": 1,
                "queue_id": 2,
                "tx_bytes": 3,
                "tx_errors": 5,
                "tx_packets": 4,
            }
        ]
    },
    "queue_config": {
        "3735928559": [
            {
                "queues": [
                    {
                        "properties": [
                            {"property": "MIN_RATE", "rate": 300},
                            {"property": "MAX_RATE", "rate": 900},
                        ],
                        "port": 2,
                        "queue_id": 1,
                    }
                ],
                "port": 2,
            }
        ]
    },
    "meter_stats": {
        "3735928559": [
            {
                "len": 0,
                "flow_count": 2,
                "packet_in_count": 3,
                "byte_in_count": 4,
                "duration_sec": 5,
                "duration_nsec": 6,
                "band_stats": [{"packet_band_count": 7, "byte_band_count": 8}],
                "meter_id": 1,
            }
        ]
    },
    "meter_config": {
        "3735928559": [
            {
                "flags": ["KBPS", "BURST"],
                "bands": [
                    {"rate": 1000, "burst_size": 100, "type": "DROP"},
                    {
                        "rate": 2000,
                        "burst_size": 200,
                        "type": "DSCP_REMARK",
                        "prec_level": 3,
                    },
                ],
                "meter_id": 1,
            }
        ]
    },
    "meter_features": {
        "3735928559": [
            {
                "max_meter": 4096,
                "band_types": ["DROP", "DSCP_REMARK"],
                "capabilities": ["KBPS", "STATS"],
                "max_bands": 2,
                "max_color": 3,
            }
        ]
    },
    "group_stats": {
        "3735928559": [
            {
                "length": 56,
                "ref_count": 2,
                "packet_count": 3,
                "byte_count": 4,
                "duration_sec": 5,
                "duration_nsec": 6,
                "bucket_stats": [{"packet_count": 7, "byte_count": 8}],
                "group_id": 1,
            }
        ]
    },
    "group_features": {
        "3735928559": [
            {
                "types": ["ALL", "SELECT"],
                "capabilities": ["CHAINING"],
                "max_groups": [
                    {"ALL": 10},
                    {"SELECT": 20},
                    {"INDIRECT": 30},
                    {"FF": 40},
                ],
                "actions": [
                    {"ALL": ["OUTPUT"]},
                    {"SELECT": ["OUTPUT"]},
                    {"INDIRECT": ["OUTPUT"]},
                    {"FF": ["OUTPUT"]},
                ],
            }
        ]
    },
    "group_desc": {
        "3735928559": [
            {
                "buckets": [
                    {
                        "weight": 0,
                        "watch_port": 1,
                        "watch_group": 2,
                        "actions": ["OUTPUT:3"],
                    }
                ],
                "group_id": 1,
                "type": "ALL",
            }
        ]
    },
    "table_features": {
        "3735928559": [
            {
                "name": "table0",
                "metadata_match": 0,
                "metadata_write": 0,
                "config": 0,
                "max_entries": 4096,
                "properties": [
                    {
                        "type": "INSTRUCTIONS",
                        "instruction_ids": [{"len": None, "type": 6}],
                    },
                    {"type": "NEXT_TABLES", "table_ids": [1, 2]},
                    {"type": "APPLY_ACTIONS", "action_ids": [{"len": None, "type": 0}]},
                    {
                        "type": "MATCH",
                        "oxm_ids": [
                            {"hasmask": False, "length": None, "type": "in_port"}
                        ],
                    },
                ],
                "table_id": 0,
            }
        ]
    },
    "role": {"3735928559": [{"generation_id": 3, "role": "MASTER"}]},
    "to_match": {
        "OFPMatch": {
            "oxm_fields": [
                {"OXMTlv": {"field": "in_port", "value": 4294967293, "mask": None}},
                {"OXMTlv": {"field": "metadata", "value": 16, "mask": 255}},
                {
                    "OXMTlv": {
                        "field": "eth_src",
                        "value": "0e:00:00:00:00:00",
                        "mask": "ff:ff:ff:ff:ff:00",
                    }
                },
                {"OXMTlv": {"field": "eth_type", "value": 2048, "mask": None}},
                {"OXMTlv": {"field": "vlan_vid", "value": 4196, "mask": None}},
                {"OXMTlv": {"field": "ip_proto", "value": 6, "mask": None}},
                {
                    "OXMTlv": {
                        "field": "ipv4_dst",
                        "value": "192.0.2.0",
                        "mask": "255.255.255.0",
                    }
                },
                {"OXMTlv": {"field": "tcp_src", "value": 80, "mask": None}},
                {"OXMTlv": {"field": "ipv6_flabel", "value": 7, "mask": None}},
            ],
            "length": None,
            "type": 1,
        }
    },
    "to_match_arp": {
        "OFPMatch": {
            "oxm_fields": [
                {"OXMTlv": {"field": "eth_type", "value": 2054, "mask": None}},
                {"OXMTlv": {"field": "arp_spa", "value": "10.0.0.1", "mask": None}},
                {"OXMTlv": {"field": "arp_tpa", "value": "10.0.0.2", "mask": None}},
            ],
            "length": None,
            "type": 1,
        }
    },
    "action_to_str": [
        "OUTPUT:CONTROLLER",
        "COPY_TTL_OUT",
        "COPY_TTL_IN",
        "SET_MPLS_TTL:5",
        "DEC_MPLS_TTL",
        "PUSH_VLAN:33024",
        "POP_VLAN",
        "PUSH_MPLS:34887",
        "POP_MPLS:2048",
        "SET_QUEUE:3",
        "GROUP:ALL",
        "SET_NW_TTL:6",
        "DEC_NW_TTL",
        "SET_FIELD: {ipv4_dst:10.0.0.1}",
        "PUSH_PBB:35047",
        "POP_PBB",
    ],
    "nicira_action_to_str": [
        "NX_CT: {flags: 0, zone: [1..17], table: 0, alg: 0, actions: []}",
        "NX_CT: {flags: 1, zone: reg0, table: 1, alg: 0, actions: []}",
        "NX_NAT: {flags: 1, range_ipv4_min: 10.0.0.1, "
        "range_ipv4_max: 10.0.0.2, range_ipv6_min: , "
        "range_ipv6_max: , range_proto_min: None, "
        "range_proto_max: None}",
    ],
    "match_vid_to_str": ["100", "0x0064", "0x1064/0x1fff"],
    "to_user": {
        "ofp_port_to_user": [1, "FLOOD", "CONTROLLER", "ANY"],
        "ofp_table_to_user": [0, "MAX", "ALL"],
        "ofp_group_to_user": [1, "ALL", "ANY"],
        "ofp_meter_to_user": [1, "CONTROLLER", "ALL"],
        "ofp_queue_to_user": [1, "ALL"],
        "ofp_role_to_user": ["NOCHANGE", "EQUAL", "MASTER", "SLAVE"],
    },
    "from_user": {
        "ofp_port_from_user": [4294967293, 4294967292, "MASTER", 3, 3],
        "ofp_table_from_user": ["CONTROLLER", 255, "MASTER", 3, 3],
        "ofp_role_from_user": ["CONTROLLER", "ALL", 2, 3, 3],
    },
    "absent_from_osken": ["get_flow_desc", "get_meter_desc", "get_queue_desc"],
    "wire": {
        "mod_flow_entry": (
            "040e00d0000000010000000000005eed00000000000000000100001e003c0064ffffffffffffffff"
            "ffffffff000000000001001e800000040000000180000a020800800017080a000000ff0000000000"
            "00030010000000000018000800000000000500080000000000010008020000000002001800000000"
            "0000000000000010ffffffffffffffff000600080000000500040040000000000000001000000002"
            "ffff00000000000000190010800006060e0000000001000000110008810000000015000800000003"
            "0016000800000004"
        ),
        "mod_flow_entry_experimenter": (
            "040e005000000001000000000000000000000000000000000000000000000000ffffffffffffffff"
            "ffffffff0000000000010004000000000004001800000000ffff0010000023200001020304050607"
        ),
        "mod_group_entry": (
            "040f00300000000100000100000000010020000a0000000100000000000000000000001000000002"
            "ffe5000000000000"
        ),
        "mod_meter_entry": (
            "041d003000000001000000050000000100010010000003e8000000640000000000020010000007d0"
            "000000c803000000"
        ),
        "mod_port_behavior": (
            "041000280000000100000001000000000e0000000001000000000001000000010000000000000000"
        ),
        "set_role": "041800180000000100000002000000000000000000000000",
        "send_experimenter": "0404001500000001000023200000000168656c6c6f",
        "send_experimenter_base64": "0404001500000001000023200000000168656c6c6f",
    },
}


def _reparse(parser, action):
    """An action as it comes back off the wire, which is how the REST API sees it."""
    buf = bytearray()
    action.serialize(buf, 0)
    return parser.OFPAction.parser(bytes(buf), 0)


class _StubReply:  # pylint: disable=too-few-public-methods
    """A stats reply: the rendering functions read only its body."""

    def __init__(self, body):
        self.body = body


class _StubDatapath:
    """A datapath that answers each request with canned replies.

    ``send_msg`` completes the waiter the way ofctl_rest's reply handler does,
    so a rendering function never blocks.
    """

    def __init__(self, ofproto, parser, replies=()):
        self.id = DPID  # pylint: disable=invalid-name
        self.ofproto = ofproto
        self.ofproto_parser = parser
        self.replies = list(replies)
        self.waiters = {}
        self.sent = []
        self.xid = 0

    def set_xid(self, msg):
        """Assign the next xid, as a real datapath does."""
        self.xid += 1
        msg.xid = self.xid
        return msg.xid

    def send_msg(self, msg):
        """Record the message, then deliver any canned replies to it."""
        self.sent.append(msg)
        if not self.replies:
            return
        entry = self.waiters.get(self.id, {}).pop(msg.xid, None)
        if entry is None:
            return
        lock, msgs = entry
        msgs.extend(self.replies)
        lock.set()


class OfctlRestTestCase(unittest.TestCase):  # pytype: disable=module-attr
    """The vendored ofctl renders what os-ken's ofctl_v1_3 rendered."""

    # pylint: disable=too-many-public-methods

    def _render(self, name, build, golden, *args, **kwargs):
        """Run ``name`` and assert it renders ``OSKEN[golden]``."""
        datapath = _StubDatapath(
            c65_ofproto, c65_parser, build(c65_parser, c65_ofproto)
        )
        waiters = {}
        datapath.waiters = waiters
        result = getattr(ofctl, name)(datapath, waiters, *args, **kwargs)
        self.assertEqual(OSKEN[golden], result, golden)
        return result

    def _send(self, name, golden, *args, **kwargs):
        """Run a mod and assert it puts ``OSKEN["wire"][golden]`` on the wire."""
        datapath = _StubDatapath(c65_ofproto, c65_parser)
        getattr(ofctl, name)(datapath, *args, **kwargs)
        self.assertEqual(1, len(datapath.sent), golden)
        msg = datapath.sent[0]
        msg.serialize()
        buf = bytes(msg.buf)
        self.assertEqual(OSKEN["wire"][golden], buf.hex(), golden)
        return buf

    # -- stats rendering ----------------------------------------------------

    def test_desc_stats(self):
        """The switch description is rendered from the reply body's fields."""

        def build(parser, _ofproto):
            return [_StubReply(parser.OFPDescStats("mfr", "hw", "sw", "serial", "dp"))]

        desc = self._render("get_desc_stats", build, "desc_stats")
        self.assertEqual({str(DPID)}, set(desc))
        self.assertEqual("mfr", desc[str(DPID)]["mfr_desc"])

    def _port_desc_replies(self, parser, ofproto):
        """Two ports: an ordinary one, and the reserved LOCAL port."""
        return [
            _StubReply(
                [
                    parser.OFPPort(
                        1,
                        "0e:00:00:00:00:01",
                        b"port1",
                        0,
                        4,
                        0x820,
                        0x820,
                        0x820,
                        0,
                        10000000,
                        10000000,
                    ),
                    parser.OFPPort(
                        ofproto.OFPP_LOCAL,
                        "0e:00:00:00:00:02",
                        b"br0",
                        1,
                        1,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                    ),
                ]
            )
        ]

    def test_port_desc(self):
        """Port descriptions carry the keys the integration tests index."""
        descs = self._render("get_port_desc", self._port_desc_replies, "port_desc")[
            str(DPID)
        ]
        self.assertEqual(2, len(descs))
        self.assertEqual("port1", descs[0]["name"])
        self.assertEqual(1, descs[0]["port_no"])
        self.assertEqual(4, descs[0]["state"])
        self.assertEqual(0, descs[0]["config"])
        self.assertEqual(10000000, descs[0]["curr_speed"])
        self.assertEqual("0e:00:00:00:00:01", descs[0]["hw_addr"])
        # A reserved port number is reported by name.
        self.assertEqual("LOCAL", descs[1]["port_no"])

    def test_port_desc_not_to_user(self):
        """With to_user off, ids stay numeric and the dpid key stays an int."""
        descs = self._render(
            "get_port_desc",
            self._port_desc_replies,
            "port_desc_not_to_user",
            to_user=False,
        )
        self.assertEqual({DPID}, set(descs))
        self.assertEqual(c65_ofproto.OFPP_LOCAL, descs[DPID][1]["port_no"])

    def test_port_stats(self):
        """Port counters are rendered for every port in the reply."""

        def build(parser, _ofproto):
            return [
                _StubReply(
                    [parser.OFPPortStats(1, *range(2, 16))],
                ),
                _StubReply([parser.OFPPortStats(2, *range(2, 16))]),
            ]

        stats = self._render("get_port_stats", build, "port_stats")[str(DPID)]
        self.assertEqual([1, 2], [stat["port_no"] for stat in stats])
        self.assertEqual(2, stats[0]["rx_packets"])
        self.assertEqual(15, stats[0]["duration_nsec"])

    def test_table_stats(self):
        """Table counters are rendered per table."""

        def build(parser, _ofproto):
            return [
                _StubReply(
                    [parser.OFPTableStats(0, 1, 2, 3), parser.OFPTableStats(1, 4, 5, 6)]
                )
            ]

        tables = self._render("get_table_stats", build, "table_stats")[str(DPID)]
        self.assertEqual([0, 1], [table["table_id"] for table in tables])
        self.assertEqual(2, tables[0]["lookup_count"])

    @staticmethod
    def _flow_match(parser):
        """A match exercising the renamed, masked and port fields."""
        return parser.OFPMatch(
            in_port=1,
            eth_type=0x0800,
            ipv4_src=("10.0.0.0", "255.0.0.0"),
            ip_proto=6,
            tcp_dst=443,
            vlan_vid=(0x1064, 0x1FFF),
            eth_dst="0e:00:00:00:00:01",
        )

    @staticmethod
    def _flow_instructions(parser, ofproto):
        """Instructions covering every branch of actions_to_str."""
        return [
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                [
                    parser.OFPActionOutput(2),
                    parser.OFPActionSetField(eth_dst="0e:00:00:00:00:02"),
                    parser.OFPActionPopVlan(),
                    parser.OFPActionGroup(7),
                    parser.OFPActionSetQueue(3),
                ],
            ),
            parser.OFPInstructionActions(
                ofproto.OFPIT_WRITE_ACTIONS, [parser.OFPActionDecNwTtl()]
            ),
            parser.OFPInstructionActions(ofproto.OFPIT_CLEAR_ACTIONS, []),
            parser.OFPInstructionGotoTable(3),
            parser.OFPInstructionWriteMetadata(0x1234, 0xFFFF),
            parser.OFPInstructionMeter(5),
        ]

    def _flow_replies(self, parser, ofproto):
        """Two flows of differing priority, in one reply."""
        return [
            _StubReply(
                [
                    parser.OFPFlowStats(
                        table_id=1,
                        duration_sec=10,
                        duration_nsec=11,
                        priority=100,
                        idle_timeout=0,
                        hard_timeout=0,
                        flags=0,
                        cookie=0x5EED,
                        packet_count=12,
                        byte_count=13,
                        match=self._flow_match(parser),
                        instructions=self._flow_instructions(parser, ofproto),
                        length=200,
                    ),
                    parser.OFPFlowStats(
                        table_id=1,
                        duration_sec=1,
                        duration_nsec=2,
                        priority=1,
                        idle_timeout=0,
                        hard_timeout=0,
                        flags=0,
                        cookie=0,
                        packet_count=0,
                        byte_count=0,
                        match=parser.OFPMatch(),
                        instructions=[],
                        length=80,
                    ),
                ]
            )
        ]

    def test_flow_stats(self):
        """Flows render with old style match keys and action strings."""
        flows = self._render("get_flow_stats", self._flow_replies, "flow_stats")[
            str(DPID)
        ]
        self.assertEqual(2, len(flows))
        self.assertEqual(
            {
                "in_port": 1,
                "dl_type": 2048,
                "nw_src": "10.0.0.0/255.0.0.0",
                "nw_proto": 6,
                "tp_dst": 443,
                "dl_vlan": "0x1064/0x1fff",
                "dl_dst": "0e:00:00:00:00:01",
            },
            flows[0]["match"],
        )
        self.assertEqual(
            [
                "OUTPUT:2",
                "SET_FIELD: {eth_dst:0e:00:00:00:00:02}",
                "POP_VLAN",
                "GROUP:7",
                "SET_QUEUE:3",
                {"WRITE_ACTIONS": ["DEC_NW_TTL"]},
                "CLEAR_ACTIONS",
                "GOTO_TABLE:3",
                "WRITE_METADATA:0x1234/0xffff",
                "METER:5",
            ],
            flows[0]["actions"],
        )
        self.assertEqual(0x5EED, flows[0]["cookie"])

    def test_flow_stats_priority_filter(self):
        """ofctl filters by priority itself, since OpenFlow cannot."""
        flows = self._render(
            "get_flow_stats",
            self._flow_replies,
            "flow_stats_priority_filter",
            {"priority": 1},
        )
        self.assertEqual([1], [flow["priority"] for flow in flows[str(DPID)]])

    def test_flow_stats_not_to_user(self):
        """With to_user off, the structures are passed through unrendered.

        No golden: the reply carries c65of objects, not JSON.
        """
        datapath = _StubDatapath(
            c65_ofproto, c65_parser, self._flow_replies(c65_parser, c65_ofproto)
        )
        waiters = {}
        datapath.waiters = waiters
        flows = ofctl.get_flow_stats(datapath, waiters, to_user=False)
        flow = flows[DPID][0]
        self.assertIs(flow["actions"], flow["instructions"])
        self.assertEqual(1, flow["table_id"])
        self.assertIsInstance(flow["match"], c65_parser.OFPMatch)

    def test_aggregate_flow_stats(self):
        """The aggregate reply renders as a single element list."""

        def build(parser, _ofproto):
            return [_StubReply(parser.OFPAggregateStats(1, 2, 3))]

        flows = self._render("get_aggregate_flow_stats", build, "aggregate_flow_stats")[
            str(DPID)
        ]
        self.assertEqual([{"packet_count": 1, "byte_count": 2, "flow_count": 3}], flows)

    def test_queue_stats(self):
        """Queue counters render for the requested port and queue."""

        def build(parser, _ofproto):
            return [_StubReply([parser.OFPQueueStats(1, 2, 3, 4, 5, 6, 7)])]

        stats = self._render("get_queue_stats", build, "queue_stats", "1", "2")[
            str(DPID)
        ]
        self.assertEqual(1, stats[0]["port_no"])
        self.assertEqual(2, stats[0]["queue_id"])
        self.assertEqual(7, stats[0]["duration_nsec"])

    def test_queue_config(self):
        """Queue properties render by name, with their rates."""

        def build(parser, _ofproto):
            queue = parser.OFPPacketQueue(
                1,
                2,
                [parser.OFPQueuePropMinRate(300), parser.OFPQueuePropMaxRate(900)],
            )
            return [parser.OFPQueueGetConfigReply(None, queues=[queue], port=2)]

        configs = self._render("get_queue_config", build, "queue_config", "2")[
            str(DPID)
        ]
        self.assertEqual(2, configs[0]["port"])
        self.assertEqual(
            [
                {"property": "MIN_RATE", "rate": 300},
                {"property": "MAX_RATE", "rate": 900},
            ],
            configs[0]["queues"][0]["properties"],
        )

    def test_meter_stats(self):
        """Meter counters render with their per band counters."""

        def build(parser, _ofproto):
            return [
                _StubReply(
                    [
                        parser.OFPMeterStats(
                            meter_id=1,
                            flow_count=2,
                            packet_in_count=3,
                            byte_in_count=4,
                            duration_sec=5,
                            duration_nsec=6,
                            band_stats=[parser.OFPMeterBandStats(7, 8)],
                            len_=40,
                        )
                    ]
                )
            ]

        meters = self._render("get_meter_stats", build, "meter_stats")[str(DPID)]
        self.assertEqual(1, meters[0]["meter_id"])
        self.assertEqual(
            [{"packet_band_count": 7, "byte_band_count": 8}], meters[0]["band_stats"]
        )

    def test_meter_config(self):
        """Meter flags and band types render by name."""

        def build(parser, ofproto):
            bands = [
                parser.OFPMeterBandDrop(1000, 100),
                parser.OFPMeterBandDscpRemark(2000, 200, 3),
            ]
            return [
                _StubReply(
                    [
                        parser.OFPMeterConfigStats(
                            flags=ofproto.OFPMF_KBPS | ofproto.OFPMF_BURST,
                            meter_id=1,
                            bands=bands,
                        )
                    ]
                )
            ]

        configs = self._render("get_meter_config", build, "meter_config")[str(DPID)]
        self.assertEqual(["KBPS", "BURST"], configs[0]["flags"])
        self.assertEqual("DROP", configs[0]["bands"][0]["type"])
        self.assertEqual(3, configs[0]["bands"][1]["prec_level"])

    def test_meter_features(self):
        """Meter band types and capabilities render as name lists."""

        def build(parser, ofproto):
            return [
                _StubReply(
                    [
                        parser.OFPMeterFeaturesStats(
                            4096,
                            (1 << ofproto.OFPMBT_DROP)
                            | (1 << ofproto.OFPMBT_DSCP_REMARK),
                            ofproto.OFPMF_KBPS | ofproto.OFPMF_STATS,
                            2,
                            3,
                        )
                    ]
                )
            ]

        features = self._render("get_meter_features", build, "meter_features")[
            str(DPID)
        ]
        self.assertEqual(["DROP", "DSCP_REMARK"], features[0]["band_types"])
        self.assertEqual(["KBPS", "STATS"], features[0]["capabilities"])
        self.assertEqual(4096, features[0]["max_meter"])

    def test_group_stats(self):
        """Group counters render with their per bucket counters."""

        def build(parser, _ofproto):
            return [
                _StubReply(
                    [
                        parser.OFPGroupStats(
                            length=56,
                            group_id=1,
                            ref_count=2,
                            packet_count=3,
                            byte_count=4,
                            duration_sec=5,
                            duration_nsec=6,
                            bucket_stats=[parser.OFPBucketCounter(7, 8)],
                        )
                    ]
                )
            ]

        groups = self._render("get_group_stats", build, "group_stats")[str(DPID)]
        self.assertEqual(1, groups[0]["group_id"])
        self.assertEqual(
            [{"packet_count": 7, "byte_count": 8}], groups[0]["bucket_stats"]
        )

    def test_group_features(self):
        """Group types, capabilities and per type actions render by name."""

        def build(parser, ofproto):
            types = (1 << ofproto.OFPGT_ALL) | (1 << ofproto.OFPGT_SELECT)
            actions = [1 << ofproto.OFPAT_OUTPUT] * 4
            return [
                _StubReply(
                    parser.OFPGroupFeaturesStats(
                        types,
                        ofproto.OFPGFC_CHAINING,
                        [10, 20, 30, 40],
                        actions,
                    )
                )
            ]

        features = self._render("get_group_features", build, "group_features")[
            str(DPID)
        ]
        self.assertEqual(["ALL", "SELECT"], features[0]["types"])
        self.assertEqual(["CHAINING"], features[0]["capabilities"])
        self.assertEqual({"ALL": 10}, features[0]["max_groups"][0])
        self.assertEqual({"ALL": ["OUTPUT"]}, features[0]["actions"][0])

    def test_group_desc(self):
        """Group buckets render with their actions as strings."""

        def build(parser, ofproto):
            bucket = parser.OFPBucket(0, 1, 2, [parser.OFPActionOutput(3)])
            return [
                _StubReply(
                    [
                        parser.OFPGroupDescStats(
                            type_=ofproto.OFPGT_ALL, group_id=1, buckets=[bucket]
                        )
                    ]
                )
            ]

        descs = self._render("get_group_desc", build, "group_desc")[str(DPID)]
        self.assertEqual("ALL", descs[0]["type"])
        self.assertEqual(1, descs[0]["group_id"])
        self.assertEqual(["OUTPUT:3"], descs[0]["buckets"][0]["actions"])

    def test_table_features(self):
        """Every table feature property kind renders its own id list."""

        def build(parser, ofproto):
            properties = [
                parser.OFPTableFeaturePropInstructions(
                    ofproto.OFPTFPT_INSTRUCTIONS,
                    instruction_ids=[parser.OFPInstructionId(ofproto.OFPIT_METER)],
                ),
                parser.OFPTableFeaturePropNextTables(
                    ofproto.OFPTFPT_NEXT_TABLES, table_ids=[1, 2]
                ),
                parser.OFPTableFeaturePropActions(
                    ofproto.OFPTFPT_APPLY_ACTIONS,
                    action_ids=[parser.OFPActionId(ofproto.OFPAT_OUTPUT)],
                ),
                parser.OFPTableFeaturePropOxm(
                    ofproto.OFPTFPT_MATCH, oxm_ids=[parser.OFPOxmId("in_port")]
                ),
            ]
            return [
                _StubReply(
                    [
                        parser.OFPTableFeaturesStats(
                            table_id=0,
                            name=b"table0",
                            metadata_match=0,
                            metadata_write=0,
                            config=0,
                            max_entries=4096,
                            properties=properties,
                        )
                    ]
                )
            ]

        tables = self._render("get_table_features", build, "table_features")[str(DPID)]
        self.assertEqual("table0", tables[0]["name"])
        properties = tables[0]["properties"]
        self.assertEqual(
            ["INSTRUCTIONS", "NEXT_TABLES", "APPLY_ACTIONS", "MATCH"],
            [prop["type"] for prop in properties],
        )
        self.assertEqual([1, 2], properties[1]["table_ids"])
        self.assertEqual("in_port", properties[3]["oxm_ids"][0]["type"])

    def test_role(self):
        """The role reply renders through the message's own JSON dict."""

        def build(parser, ofproto):
            return [parser.OFPRoleReply(None, ofproto.OFPCR_ROLE_MASTER, 3)]

        roles = self._render("get_role", build, "role")[str(DPID)]
        self.assertEqual([{"role": "MASTER", "generation_id": 3}], roles)

    def test_stats_request_times_out(self):
        """A request that is never answered gives up and drops its waiter."""
        datapath = _StubDatapath(c65_ofproto, c65_parser)
        waiters = {}
        datapath.waiters = waiters
        default_timeout = ofctl.DEFAULT_TIMEOUT
        ofctl.DEFAULT_TIMEOUT = 0.01
        try:
            self.assertEqual({str(DPID): []}, ofctl.get_port_desc(datapath, waiters))
        finally:
            ofctl.DEFAULT_TIMEOUT = default_timeout
        self.assertEqual({DPID: {}}, waiters)

    # -- request building ---------------------------------------------------

    def test_to_match(self):
        """User supplied match fields convert to the same OXM fields."""
        attrs = {
            "in_port": "CONTROLLER",
            "dl_src": "0e:00:00:00:00:01/ff:ff:ff:ff:ff:00",
            "dl_type": "0x800",
            "nw_proto": 6,
            "tp_src": 80,
            "dl_vlan": 100,
            "ipv4_dst": "192.0.2.0/24",
            "metadata": "0x10/0xff",
            "ipv6_flabel": 7,
        }
        datapath = _StubDatapath(c65_ofproto, c65_parser)
        rendered = ofctl.to_match(datapath, attrs).to_jsondict()
        self.assertEqual(OSKEN["to_match"], rendered)

    def test_to_match_arp(self):
        """With an ARP ethertype, nw_src and nw_dst become arp_spa/arp_tpa."""
        attrs = {"dl_type": 0x0806, "nw_src": "10.0.0.1", "nw_dst": "10.0.0.2"}
        datapath = _StubDatapath(c65_ofproto, c65_parser)
        rendered = ofctl.to_match(datapath, attrs).to_jsondict()
        self.assertEqual(OSKEN["to_match_arp"], rendered)

    def test_match_to_str_vid(self):
        """A VLAN id is reported as written: bare, present, or masked."""
        cases = ((0x1064, None), (0x0064, None), (0x1064, 0x1FFF))
        self.assertEqual(
            OSKEN["match_vid_to_str"],
            [ofctl.match_vid_to_str(value, mask) for value, mask in cases],
        )

    def test_action_to_str(self):
        """Every action kind renders to its string, reserved numbers by name."""
        builders = (
            ("OFPActionOutput", (4294967293,), {}),
            ("OFPActionCopyTtlOut", (), {}),
            ("OFPActionCopyTtlIn", (), {}),
            ("OFPActionSetMplsTtl", (5,), {}),
            ("OFPActionDecMplsTtl", (), {}),
            ("OFPActionPushVlan", (0x8100,), {}),
            ("OFPActionPopVlan", (), {}),
            ("OFPActionPushMpls", (0x8847,), {}),
            ("OFPActionPopMpls", (0x0800,), {}),
            ("OFPActionSetQueue", (3,), {}),
            ("OFPActionGroup", (4294967292,), {}),
            ("OFPActionSetNwTtl", (6,), {}),
            ("OFPActionDecNwTtl", (), {}),
            ("OFPActionSetField", (), {"ipv4_dst": "10.0.0.1"}),
            ("OFPActionPushPbb", (0x88E7,), {}),
            ("OFPActionPopPbb", (), {}),
        )
        self.assertEqual(
            OSKEN["action_to_str"],
            [
                ofctl.action_to_str(getattr(c65_parser, name)(*args, **kwargs))
                for name, args, kwargs in builders
            ],
        )

    def test_nicira_action_to_str(self):
        """Nicira extension actions render as os-ken's REST API rendered them."""
        builders = (
            (
                "NXActionCT",
                {
                    "flags": 0,
                    "zone_src": None,
                    "zone_ofs_nbits": 1,
                    "recirc_table": 0,
                    "alg": 0,
                    "actions": [],
                },
            ),
            (
                "NXActionCT",
                {
                    "flags": 1,
                    "zone_src": "reg0",
                    "zone_ofs_nbits": 0,
                    "recirc_table": 1,
                    "alg": 0,
                    "actions": [],
                },
            ),
            (
                "NXActionNAT",
                {
                    "flags": 1,
                    "range_ipv4_min": "10.0.0.1",
                    "range_ipv4_max": "10.0.0.2",
                },
            ),
        )
        self.assertEqual(
            OSKEN["nicira_action_to_str"],
            [
                ofctl.action_to_str(
                    _reparse(c65_parser, getattr(c65_parser, name)(**kwargs))
                )
                for name, kwargs in builders
            ],
        )

    def test_nicira_ct_action_in_flow_stats(self):
        """A CT action in a flow stats reply renders as NX_CT, not EXPERIMENTER.

        The integration tests match conntrack flows on this exact string.
        """
        act = _reparse(
            c65_parser,
            c65_parser.NXActionCT(
                flags=0,
                zone_src=None,
                zone_ofs_nbits=1,
                recirc_table=0,
                alg=0,
                actions=[],
            ),
        )
        self.assertEqual(
            ["NX_CT: {flags: 0, zone: [1..17], table: 0, alg: 0, actions: []}"],
            ofctl.actions_to_str(
                [
                    c65_parser.OFPInstructionActions(
                        c65_ofproto.OFPIT_APPLY_ACTIONS, [act]
                    )
                ]
            ),
        )

    def test_reserved_numbers_to_user(self):
        """The number to name lookups render the reserved values, both ways."""
        pairs = (
            ("ofp_port_to_user", (1, 0xFFFFFFFB, 0xFFFFFFFD, 0xFFFFFFFF)),
            ("ofp_table_to_user", (0, 0xFE, 0xFF)),
            ("ofp_group_to_user", (1, 0xFFFFFFFC, 0xFFFFFFFF)),
            ("ofp_meter_to_user", (1, 0xFFFFFFFE, 0xFFFFFFFF)),
            ("ofp_queue_to_user", (1, 0xFFFFFFFF)),
            ("ofp_role_to_user", (0, 1, 2, 3)),
        )
        for name, values in pairs:
            self.assertEqual(
                OSKEN["to_user"][name],
                [getattr(ofctl.UTIL, name)(value) for value in values],
                name,
            )
        for name in ("ofp_port_from_user", "ofp_table_from_user", "ofp_role_from_user"):
            self.assertEqual(
                OSKEN["from_user"][name],
                [
                    getattr(ofctl.UTIL, name)(value)
                    for value in ("CONTROLLER", "ALL", "MASTER", "3", 3)
                ],
                name,
            )

    # -- mods ---------------------------------------------------------------

    def test_mod_flow_entry(self):
        """A flow mod built from JSON serializes to the bytes os-ken produced."""
        flow = {
            "table_id": 1,
            "priority": "100",
            "cookie": "0x5eed",
            "idle_timeout": 30,
            "hard_timeout": 60,
            "buffer_id": "NO_BUFFER",
            "out_port": "ANY",
            "match": {"in_port": 1, "dl_type": 0x0800, "nw_src": "10.0.0.0/8"},
            "actions": [
                {"type": "OUTPUT", "port": 2, "max_len": "NO_BUFFER"},
                {"type": "SET_FIELD", "field": "eth_dst", "value": "0e:00:00:00:00:01"},
                {"type": "PUSH_VLAN", "ethertype": 33024},
                {"type": "SET_QUEUE", "queue_id": 3},
                {"type": "GROUP", "group_id": 4},
                {"type": "WRITE_ACTIONS", "actions": [{"type": "DEC_NW_TTL"}]},
                {"type": "CLEAR_ACTIONS"},
                {"type": "GOTO_TABLE", "table_id": 2},
                {"type": "WRITE_METADATA", "metadata": "0x10"},
                {"type": "METER", "meter_id": 5},
            ],
        }
        self._send("mod_flow_entry", "mod_flow_entry", flow, c65_ofproto.OFPFC_ADD)

    def test_mod_flow_entry_experimenter_action(self):
        """An experimenter action serializes with its opaque payload."""
        flow = {
            "actions": [
                {
                    "type": "EXPERIMENTER",
                    "experimenter": 0x2320,
                    "data_type": "base64",
                    "data": "AAECAwQFBgc=",
                }
            ]
        }
        self.assertIn(
            b"\x00\x01\x02\x03\x04\x05\x06\x07",
            self._send(
                "mod_flow_entry",
                "mod_flow_entry_experimenter",
                flow,
                c65_ofproto.OFPFC_ADD,
            ),
        )

    def test_mod_group_entry(self):
        """A group mod built from JSON serializes to the bytes os-ken produced."""
        group = {
            "type": "SELECT",
            "group_id": 1,
            "buckets": [
                {
                    "weight": 10,
                    "watch_port": 1,
                    "watch_group": 0,
                    "actions": [{"type": "OUTPUT", "port": 2}],
                }
            ],
        }
        self._send("mod_group_entry", "mod_group_entry", group, c65_ofproto.OFPGC_ADD)

    def test_mod_meter_entry(self):
        """A meter mod built from JSON serializes to the bytes os-ken produced."""
        meter = {
            "meter_id": 1,
            "flags": ["KBPS", "BURST"],
            "bands": [
                {"type": "DROP", "rate": 1000, "burst_size": 100},
                {
                    "type": "DSCP_REMARK",
                    "rate": 2000,
                    "burst_size": 200,
                    "prec_level": 3,
                },
            ],
        }
        self._send("mod_meter_entry", "mod_meter_entry", meter, c65_ofproto.OFPMC_ADD)

    def test_mod_port_behavior(self):
        """A port mod built from JSON serializes to the bytes os-ken produced."""
        port_config = {
            "port_no": "1",
            "hw_addr": "0e:00:00:00:00:01",
            "config": "1",
            "mask": "1",
            "advertise": "0",
        }
        self._send("mod_port_behavior", "mod_port_behavior", port_config)

    def test_set_role(self):
        """A role request built from JSON serializes to the bytes os-ken produced."""
        self._send("set_role", "set_role", {"role": "MASTER"})

    def test_send_experimenter(self):
        """An experimenter message serializes to the bytes os-ken produced."""
        self._send(
            "send_experimenter",
            "send_experimenter",
            {"experimenter": 0x2320, "exp_type": 1, "data": "hello"},
        )
        self._send(
            "send_experimenter",
            "send_experimenter_base64",
            {
                "experimenter": 0x2320,
                "exp_type": 1,
                "data_type": "base64",
                "data": "aGVsbG8=",
            },
        )

    def test_send_experimenter_bad_data_type(self):
        """An unknown data type sends nothing, as os-ken did."""
        datapath = _StubDatapath(c65_ofproto, c65_parser)
        ofctl.send_experimenter(datapath, {"data_type": "binary"})
        self.assertEqual([], datapath.sent)

    # -- surface ------------------------------------------------------------

    def test_supports_every_function_ofctl_rest_calls(self):
        """Every entry point ofctl_rest calls, and no OF1.4 only extras."""
        for name in (
            "get_aggregate_flow_stats",
            "get_desc_stats",
            "get_flow_stats",
            "get_group_desc",
            "get_group_features",
            "get_group_stats",
            "get_meter_config",
            "get_meter_features",
            "get_meter_stats",
            "get_port_desc",
            "get_port_stats",
            "get_queue_config",
            "get_queue_stats",
            "get_role",
            "get_table_features",
            "get_table_stats",
            "mod_flow_entry",
            "mod_group_entry",
            "mod_meter_entry",
            "mod_port_behavior",
            "send_experimenter",
            "set_role",
        ):
            self.assertTrue(callable(getattr(ofctl, name)), name)
        # OF1.4 only; ofctl_rest turns the AttributeError into a 501.
        absent = ["get_flow_desc", "get_meter_desc", "get_queue_desc"]
        self.assertEqual(OSKEN["absent_from_osken"], absent)
        for name in absent:
            self.assertFalse(hasattr(ofctl, name), name)


if __name__ == "__main__":
    unittest.main()  # pytype: disable=module-attr
