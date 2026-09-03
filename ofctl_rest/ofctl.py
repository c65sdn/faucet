"""Render OpenFlow 1.3 structures to and from the JSON of the REST API.

A port of os-ken's ``lib/ofctl_v1_3``, and of the parts of ``lib/ofctl_utils``
it reaches, onto c65of. Only the REST rendering lives here; the value
conversions a controller runtime also needs come from :mod:`c65of.ofctl`.

``get_flow_desc``, ``get_meter_desc`` and ``get_queue_desc`` are deliberately
absent, as they are from os-ken's OpenFlow 1.3 module: ``ofctl_rest`` turns the
resulting AttributeError into a 501.
"""

# Copyright (C) 2013 Nippon Telegraph and Telephone Corporation.
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
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# pylint: disable=too-many-lines,too-many-locals,too-many-branches
# pylint: disable=too-many-return-statements

import base64
import logging
import threading

from c65of import ofctl as _c65of_ofctl
from c65of import ofproto
from c65of.ofctl import (
    OFCtlUtil,
    str_to_int,
    to_match_eth,
    to_match_ip,
    to_match_masked_int,
)
from c65of.ofproto import ether
from c65of.ofproto import inet
from c65of.ofproto import parser as ofproto_parser

LOG = logging.getLogger("ofctl")

DEFAULT_TIMEOUT = 1.0
UINT64_MAX = (1 << 64) - 1


class _Util(OFCtlUtil):
    """:class:`~c65of.ofctl.OFCtlUtil` plus the number to name direction.

    Rendering is the REST API's own concern, so the reverse lookups live here
    rather than in the controller runtime's copy.
    """

    def _reserved_num_to_user(self, num, prefix):
        for key, value in self.ofproto.__dict__.items():
            if key.startswith(prefix) and value == num:
                return key.replace(prefix, "")
        return num

    def ofp_cml_from_user(self, max_len):
        """A max_len, or the value of an ``OFPCML_`` name."""
        return self._reserved_num_from_user(max_len, "OFPCML_")

    def ofp_queue_from_user(self, queue):
        """A queue id, or the value of an ``OFPQ_`` name."""
        return self._reserved_num_from_user(queue, "OFPQ_")

    def ofp_role_from_user(self, role):
        """A role, or the value of an ``OFPCR_ROLE_`` name."""
        return self._reserved_num_from_user(role, "OFPCR_ROLE_")

    def ofp_port_to_user(self, port):
        """The ``OFPP_`` name of a reserved port, else the number."""
        return self._reserved_num_to_user(port, "OFPP_")

    def ofp_table_to_user(self, table):
        """The ``OFPTT_`` name of a reserved table, else the number."""
        return self._reserved_num_to_user(table, "OFPTT_")

    def ofp_group_to_user(self, group):
        """The ``OFPG_`` name of a reserved group, else the number."""
        return self._reserved_num_to_user(group, "OFPG_")

    def ofp_meter_to_user(self, meter):
        """The ``OFPM_`` name of a reserved meter, else the number."""
        return self._reserved_num_to_user(meter, "OFPM_")

    def ofp_queue_to_user(self, queue):
        """The ``OFPQ_`` name of a reserved queue, else the number."""
        return self._reserved_num_to_user(queue, "OFPQ_")

    def ofp_role_to_user(self, role):
        """The ``OFPCR_ROLE_`` name of a role, else the number."""
        return self._reserved_num_to_user(role, "OFPCR_ROLE_")


UTIL = _Util(ofproto)


class OFPActionExperimenterUnknown(ofproto_parser.OFPActionExperimenter):
    """An experimenter action whose payload the library does not interpret."""

    _EXTRA = "type len data"
    _VARIABLE = True
    data = None

    def pack_tail(self):
        """The opaque payload, verbatim."""
        data = self.data or b""
        return data.encode("ascii") if isinstance(data, str) else data


# -- request side -----------------------------------------------------------


def to_action(dp, dic):
    """One action from its dict form, or None if it is not an action.

    ``METER`` and the instruction pseudo-actions return None so that
    :func:`to_actions` can turn them into instructions instead.
    """
    ofp = dp.ofproto
    parser = dp.ofproto_parser
    action_type = dic.get("type")

    no_args = {
        "COPY_TTL_OUT": parser.OFPActionCopyTtlOut,
        "COPY_TTL_IN": parser.OFPActionCopyTtlIn,
        "DEC_MPLS_TTL": parser.OFPActionDecMplsTtl,
        "POP_VLAN": parser.OFPActionPopVlan,
        "DEC_NW_TTL": parser.OFPActionDecNwTtl,
        "POP_PBB": parser.OFPActionPopPbb,
    }
    if action_type in no_args:
        return no_args[action_type]()

    need_ethertype = {
        "PUSH_VLAN": parser.OFPActionPushVlan,
        "PUSH_MPLS": parser.OFPActionPushMpls,
        "POP_MPLS": parser.OFPActionPopMpls,
        "PUSH_PBB": parser.OFPActionPushPbb,
    }
    if action_type in need_ethertype:
        return need_ethertype[action_type](str_to_int(dic.get("ethertype")))

    if action_type == "OUTPUT":
        out_port = UTIL.ofp_port_from_user(dic.get("port", ofp.OFPP_ANY))
        max_len = UTIL.ofp_cml_from_user(dic.get("max_len", ofp.OFPCML_MAX))
        return parser.OFPActionOutput(out_port, max_len)
    if action_type == "SET_MPLS_TTL":
        return parser.OFPActionSetMplsTtl(str_to_int(dic.get("mpls_ttl")))
    if action_type == "SET_QUEUE":
        return parser.OFPActionSetQueue(UTIL.ofp_queue_from_user(dic.get("queue_id")))
    if action_type == "GROUP":
        return parser.OFPActionGroup(UTIL.ofp_group_from_user(dic.get("group_id")))
    if action_type == "SET_NW_TTL":
        return parser.OFPActionSetNwTtl(str_to_int(dic.get("nw_ttl")))
    if action_type == "SET_FIELD":
        return parser.OFPActionSetField(**{dic.get("field"): dic.get("value")})
    if action_type == "EXPERIMENTER":
        data_type = dic.get("data_type", "ascii")
        if data_type not in ("ascii", "base64"):
            LOG.error("Unknown data type: %s", data_type)
            return None
        data = dic.get("data", "")
        if data_type == "base64":
            data = base64.b64decode(data)
        experimenter = str_to_int(dic.get("experimenter"))
        return OFPActionExperimenterUnknown(experimenter, data=data)

    return None


def to_actions(dp, acts):
    """The instruction list for a flow mod, from a list of action dicts.

    Anything not an apply action becomes its own instruction; everything else
    is gathered into a single OFPIT_APPLY_ACTIONS instruction, last.
    """
    ofp = dp.ofproto
    parser = dp.ofproto_parser
    inst = []
    actions = []

    for entry in acts:
        action = to_action(dp, entry)
        if action is not None:
            actions.append(action)
            continue

        action_type = entry.get("type")
        if action_type == "WRITE_ACTIONS":
            write_actions = []
            for act in entry.get("actions"):
                action = to_action(dp, act)
                if action is not None:
                    write_actions.append(action)
                else:
                    LOG.error("Unknown action type: %s", action_type)
            if write_actions:
                inst.append(
                    parser.OFPInstructionActions(ofp.OFPIT_WRITE_ACTIONS, write_actions)
                )
        elif action_type == "CLEAR_ACTIONS":
            inst.append(parser.OFPInstructionActions(ofp.OFPIT_CLEAR_ACTIONS, []))
        elif action_type == "GOTO_TABLE":
            table_id = UTIL.ofp_table_from_user(entry.get("table_id"))
            inst.append(parser.OFPInstructionGotoTable(table_id))
        elif action_type == "WRITE_METADATA":
            metadata = str_to_int(entry.get("metadata"))
            metadata_mask = (
                str_to_int(entry["metadata_mask"])
                if "metadata_mask" in entry
                else UINT64_MAX
            )
            inst.append(
                parser.OFPInstructionWriteMetadata(metadata, metadata_mask),
            )
        elif action_type == "METER":
            meter_id = UTIL.ofp_meter_from_user(entry.get("meter_id"))
            inst.append(parser.OFPInstructionMeter(meter_id))
        else:
            LOG.error("Unknown action type: %s", action_type)

    if actions:
        inst.append(parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions))
    return inst


def to_match_vid(value):
    """A VLAN match value, with OFPVID_PRESENT applied where the spec says."""
    return _c65of_ofctl.to_match_vid(value, ofproto.OFPVID_PRESENT)


_MATCH_CONVERT = {
    "in_port": UTIL.ofp_port_from_user,
    "in_phy_port": str_to_int,
    "metadata": to_match_masked_int,
    "dl_dst": to_match_eth,
    "dl_src": to_match_eth,
    "eth_dst": to_match_eth,
    "eth_src": to_match_eth,
    "dl_type": str_to_int,
    "eth_type": str_to_int,
    "dl_vlan": to_match_vid,
    "vlan_vid": to_match_vid,
    "vlan_pcp": str_to_int,
    "ip_dscp": str_to_int,
    "ip_ecn": str_to_int,
    "nw_proto": str_to_int,
    "ip_proto": str_to_int,
    "nw_src": to_match_ip,
    "nw_dst": to_match_ip,
    "ipv4_src": to_match_ip,
    "ipv4_dst": to_match_ip,
    "tp_src": str_to_int,
    "tp_dst": str_to_int,
    "tcp_src": str_to_int,
    "tcp_dst": str_to_int,
    "udp_src": str_to_int,
    "udp_dst": str_to_int,
    "sctp_src": str_to_int,
    "sctp_dst": str_to_int,
    "icmpv4_type": str_to_int,
    "icmpv4_code": str_to_int,
    "arp_op": str_to_int,
    "arp_spa": to_match_ip,
    "arp_tpa": to_match_ip,
    "arp_sha": to_match_eth,
    "arp_tha": to_match_eth,
    "ipv6_src": to_match_ip,
    "ipv6_dst": to_match_ip,
    "ipv6_flabel": str_to_int,
    "icmpv6_type": str_to_int,
    "icmpv6_code": str_to_int,
    "ipv6_nd_target": to_match_ip,
    "ipv6_nd_sll": to_match_eth,
    "ipv6_nd_tll": to_match_eth,
    "mpls_label": str_to_int,
    "mpls_tc": str_to_int,
    "mpls_bos": str_to_int,
    "pbb_isid": to_match_masked_int,
    "tunnel_id": to_match_masked_int,
    "ipv6_exthdr": to_match_masked_int,
}

# Field names predating OpenFlow 1.2, and their modern equivalents.
_MATCH_OLD_KEYS = {
    "dl_dst": "eth_dst",
    "dl_src": "eth_src",
    "dl_type": "eth_type",
    "dl_vlan": "vlan_vid",
    "nw_src": "ipv4_src",
    "nw_dst": "ipv4_dst",
    "nw_proto": "ip_proto",
}

# tp_src/tp_dst name a port whose field depends on the IP protocol.
_MATCH_TP_KEYS = {
    inet.IPPROTO_TCP: {"tp_src": "tcp_src", "tp_dst": "tcp_dst"},
    inet.IPPROTO_UDP: {"tp_src": "udp_src", "tp_dst": "udp_dst"},
}


def to_match(dp, attrs):
    """An OFPMatch from a dict of field names to user supplied values."""
    if ether.ETH_TYPE_ARP in (attrs.get("dl_type"), attrs.get("eth_type")):
        for old, new in (("nw_src", "arp_spa"), ("nw_dst", "arp_tpa")):
            if old in attrs and new not in attrs:
                attrs[new] = attrs.pop(old)

    kwargs = {}
    for key, value in attrs.items():
        key = _MATCH_OLD_KEYS.get(key, key)
        if key not in _MATCH_CONVERT:
            LOG.error("Unknown match field: %s", key)
            continue
        value = _MATCH_CONVERT[key](value)
        if key in ("tp_src", "tp_dst"):
            ip_proto = attrs.get("nw_proto", attrs.get("ip_proto", 0))
            key = _MATCH_TP_KEYS[ip_proto][key]
        kwargs[key] = value

    return dp.ofproto_parser.OFPMatch(**kwargs)


# -- rendering side ---------------------------------------------------------


def action_to_str(act):
    """One action as the short string the REST API reports."""
    action_type = act.type

    if action_type == ofproto.OFPAT_OUTPUT:
        return "OUTPUT:" + str(UTIL.ofp_port_to_user(act.port))
    if action_type == ofproto.OFPAT_COPY_TTL_OUT:
        return "COPY_TTL_OUT"
    if action_type == ofproto.OFPAT_COPY_TTL_IN:
        return "COPY_TTL_IN"
    if action_type == ofproto.OFPAT_SET_MPLS_TTL:
        return "SET_MPLS_TTL:" + str(act.mpls_ttl)
    if action_type == ofproto.OFPAT_DEC_MPLS_TTL:
        return "DEC_MPLS_TTL"
    if action_type == ofproto.OFPAT_PUSH_VLAN:
        return "PUSH_VLAN:" + str(act.ethertype)
    if action_type == ofproto.OFPAT_POP_VLAN:
        return "POP_VLAN"
    if action_type == ofproto.OFPAT_PUSH_MPLS:
        return "PUSH_MPLS:" + str(act.ethertype)
    if action_type == ofproto.OFPAT_POP_MPLS:
        return "POP_MPLS:" + str(act.ethertype)
    if action_type == ofproto.OFPAT_SET_QUEUE:
        return "SET_QUEUE:" + str(UTIL.ofp_queue_to_user(act.queue_id))
    if action_type == ofproto.OFPAT_GROUP:
        return "GROUP:" + str(UTIL.ofp_group_to_user(act.group_id))
    if action_type == ofproto.OFPAT_SET_NW_TTL:
        return "SET_NW_TTL:" + str(act.nw_ttl)
    if action_type == ofproto.OFPAT_DEC_NW_TTL:
        return "DEC_NW_TTL"
    if action_type == ofproto.OFPAT_SET_FIELD:
        return "SET_FIELD: {%s:%s}" % (act.key, act.value)
    if action_type == ofproto.OFPAT_PUSH_PBB:
        return "PUSH_PBB:" + str(act.ethertype)
    if action_type == ofproto.OFPAT_POP_PBB:
        return "POP_PBB"
    if action_type == ofproto.OFPAT_EXPERIMENTER:
        data = getattr(act, "data", b"") or b""
        data_str = base64.b64encode(data)
        return "EXPERIMENTER: {experimenter:%s, data:%s}" % (
            act.experimenter,
            data_str.decode("utf-8"),
        )
    return "UNKNOWN"


def actions_to_str(instructions):
    """A flow's instruction list as the strings the REST API reports."""
    actions = []

    for instruction in instructions:
        if isinstance(instruction, ofproto_parser.OFPInstructionActions):
            if instruction.type == ofproto.OFPIT_APPLY_ACTIONS:
                actions.extend(action_to_str(a) for a in instruction.actions)
            elif instruction.type == ofproto.OFPIT_WRITE_ACTIONS:
                write_actions = [action_to_str(a) for a in instruction.actions]
                if write_actions:
                    actions.append({"WRITE_ACTIONS": write_actions})
            elif instruction.type == ofproto.OFPIT_CLEAR_ACTIONS:
                actions.append("CLEAR_ACTIONS")
            else:
                actions.append("UNKNOWN")
        elif isinstance(instruction, ofproto_parser.OFPInstructionGotoTable):
            table_id = UTIL.ofp_table_to_user(instruction.table_id)
            actions.append("GOTO_TABLE:" + str(table_id))
        elif isinstance(instruction, ofproto_parser.OFPInstructionWriteMetadata):
            actions.append(
                "WRITE_METADATA:0x%x/0x%x"
                % (instruction.metadata, instruction.metadata_mask)
                if instruction.metadata_mask
                else "WRITE_METADATA:0x%x" % instruction.metadata
            )
        elif isinstance(instruction, ofproto_parser.OFPInstructionMeter):
            meter_id = UTIL.ofp_meter_to_user(instruction.meter_id)
            actions.append("METER:" + str(meter_id))

    return actions


def match_vid_to_str(value, mask):
    """A VLAN match rendered the way it would have been written."""
    if mask is not None:
        return "0x%04x/0x%04x" % (value, mask)
    if value & ofproto.OFPVID_PRESENT:
        return str(value & ~ofproto.OFPVID_PRESENT)
    return "0x%04x" % value


# Modern field names, and the pre-1.2 names the REST API still reports.
_MATCH_TO_STR_KEYS = {
    "eth_src": "dl_src",
    "eth_dst": "dl_dst",
    "eth_type": "dl_type",
    "vlan_vid": "dl_vlan",
    "ipv4_src": "nw_src",
    "ipv4_dst": "nw_dst",
    "ip_proto": "nw_proto",
    "tcp_src": "tp_src",
    "tcp_dst": "tp_dst",
    "udp_src": "tp_src",
    "udp_dst": "tp_dst",
}


def match_to_str(ofmatch):
    """An OFPMatch as a dict of old style field names to values."""
    match = {}

    for match_field in ofmatch.to_jsondict()["OFPMatch"]["oxm_fields"]:
        tlv = match_field["OXMTlv"]
        key = _MATCH_TO_STR_KEYS.get(tlv["field"], tlv["field"])
        mask = tlv["mask"]
        value = tlv["value"]
        if key == "dl_vlan":
            value = match_vid_to_str(value, mask)
        elif key == "in_port":
            value = UTIL.ofp_port_to_user(value)
        elif mask is not None:
            value = str(value) + "/" + str(mask)
        match.setdefault(key, value)

    return match


def wrap_dpid_dict(dp, value, to_user=True):
    """``value`` keyed by datapath id, as a string for a REST caller."""
    if to_user:
        return {str(dp.id): value}
    return {dp.id: value}


# -- transport --------------------------------------------------------------


def send_msg(dp, msg, logger=None):
    """Assign an xid if the message has none, then send it."""
    if msg.xid is None:
        dp.set_xid(msg)
    (logger or LOG).debug(
        "Sending message with xid(%x) to datapath(%016x): %s", msg.xid, dp.id, msg
    )
    dp.send_msg(msg)


def send_stats_request(dp, stats, waiters, msgs, logger=None):
    """Send a stats request and block until its replies have been collected.

    Replies arrive on the application's event thread, which appends them to
    ``msgs`` and sets the event. A multipart reply may span several messages,
    so keep waiting while ``msgs`` is still growing.
    """
    dp.set_xid(stats)
    waiters_per_dp = waiters.setdefault(dp.id, {})
    lock = threading.Event()
    previous_msg_len = len(msgs)
    waiters_per_dp[stats.xid] = (lock, msgs)
    send_msg(dp, stats, logger)

    lock.wait(timeout=DEFAULT_TIMEOUT)
    current_msg_len = len(msgs)
    while current_msg_len > previous_msg_len:
        previous_msg_len = current_msg_len
        lock.wait(timeout=DEFAULT_TIMEOUT)
        current_msg_len = len(msgs)

    if not lock.is_set():
        del waiters_per_dp[stats.xid]


# -- stats -------------------------------------------------------------------


def get_desc_stats(dp, waiters, to_user=True):
    """The switch description."""
    stats = dp.ofproto_parser.OFPDescStatsRequest(dp, 0)
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)
    desc = {}

    for msg in msgs:
        body = msg.body
        desc = body.to_jsondict()[body.__class__.__name__]

    return wrap_dpid_dict(dp, desc, to_user)


def get_queue_stats(dp, waiters, port=None, queue_id=None, to_user=True):
    """Per queue counters, for one port and queue or for all of them."""
    ofp = dp.ofproto
    port = ofp.OFPP_ANY if port is None else str_to_int(port)
    queue_id = ofp.OFPQ_ALL if queue_id is None else str_to_int(queue_id)

    stats = dp.ofproto_parser.OFPQueueStatsRequest(dp, 0, port, queue_id)
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)

    queues = []
    for msg in msgs:
        for stat in msg.body:
            queues.append(
                {
                    "duration_nsec": stat.duration_nsec,
                    "duration_sec": stat.duration_sec,
                    "port_no": stat.port_no,
                    "queue_id": stat.queue_id,
                    "tx_bytes": stat.tx_bytes,
                    "tx_errors": stat.tx_errors,
                    "tx_packets": stat.tx_packets,
                }
            )

    return wrap_dpid_dict(dp, queues, to_user)


def get_queue_config(dp, waiters, port=None, to_user=True):
    """The queues configured on one port, or on all of them."""
    ofp = dp.ofproto
    port = ofp.OFPP_ANY if port is None else UTIL.ofp_port_from_user(str_to_int(port))
    stats = dp.ofproto_parser.OFPQueueGetConfigRequest(dp, port)
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)

    prop_type = {
        ofp.OFPQT_MIN_RATE: "MIN_RATE",
        ofp.OFPQT_MAX_RATE: "MAX_RATE",
        ofp.OFPQT_EXPERIMENTER: "EXPERIMENTER",
    }

    configs = []
    for config in msgs:
        queue_list = []
        for queue in config.queues:
            prop_list = []
            for prop in queue.properties:
                rendered = {"property": prop_type.get(prop.property, "UNKNOWN")}
                if prop.property in (ofp.OFPQT_MIN_RATE, ofp.OFPQT_MAX_RATE):
                    rendered["rate"] = prop.rate
                elif prop.property == ofp.OFPQT_EXPERIMENTER:
                    rendered["experimenter"] = prop.experimenter
                    rendered["data"] = prop.data
                prop_list.append(rendered)

            queue_dict = {"properties": prop_list}
            if to_user:
                queue_dict["port"] = UTIL.ofp_port_to_user(queue.port)
                queue_dict["queue_id"] = UTIL.ofp_queue_to_user(queue.queue_id)
            else:
                queue_dict["port"] = queue.port
                queue_dict["queue_id"] = queue.queue_id
            queue_list.append(queue_dict)

        config_dict = {"queues": queue_list}
        config_dict["port"] = (
            UTIL.ofp_port_to_user(config.port) if to_user else config.port
        )
        configs.append(config_dict)

    return wrap_dpid_dict(dp, configs, to_user)


def get_flow_stats(dp, waiters, flow=None, to_user=True):
    """Individual flow counters, filtered by the fields in ``flow``."""
    flow = flow if flow else {}
    table_id = UTIL.ofp_table_from_user(flow.get("table_id", dp.ofproto.OFPTT_ALL))
    flags = str_to_int(flow.get("flags", 0))
    out_port = UTIL.ofp_port_from_user(flow.get("out_port", dp.ofproto.OFPP_ANY))
    out_group = UTIL.ofp_group_from_user(flow.get("out_group", dp.ofproto.OFPG_ANY))
    cookie = str_to_int(flow.get("cookie", 0))
    cookie_mask = str_to_int(flow.get("cookie_mask", 0))
    match = to_match(dp, flow.get("match", {}))
    # OpenFlow cannot filter by priority; ofctl does it here instead.
    priority = str_to_int(flow.get("priority", -1))

    stats = dp.ofproto_parser.OFPFlowStatsRequest(
        dp, flags, table_id, out_port, out_group, cookie, cookie_mask, match
    )
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)

    flows = []
    for msg in msgs:
        for stat in msg.body:
            if 0 <= priority != stat.priority:
                continue

            rendered = {
                "priority": stat.priority,
                "cookie": stat.cookie,
                "idle_timeout": stat.idle_timeout,
                "hard_timeout": stat.hard_timeout,
                "byte_count": stat.byte_count,
                "duration_sec": stat.duration_sec,
                "duration_nsec": stat.duration_nsec,
                "packet_count": stat.packet_count,
                "length": stat.length,
                "flags": stat.flags,
            }
            if to_user:
                rendered["actions"] = actions_to_str(stat.instructions)
                rendered["match"] = match_to_str(stat.match)
                rendered["table_id"] = UTIL.ofp_table_to_user(stat.table_id)
            else:
                rendered["actions"] = stat.instructions
                rendered["instructions"] = stat.instructions
                rendered["match"] = stat.match
                rendered["table_id"] = stat.table_id
            flows.append(rendered)

    return wrap_dpid_dict(dp, flows, to_user)


def get_aggregate_flow_stats(dp, waiters, flow=None, to_user=True):
    """Counters summed over the flows matching ``flow``."""
    flow = flow if flow else {}
    table_id = UTIL.ofp_table_from_user(flow.get("table_id", dp.ofproto.OFPTT_ALL))
    flags = str_to_int(flow.get("flags", 0))
    out_port = UTIL.ofp_port_from_user(flow.get("out_port", dp.ofproto.OFPP_ANY))
    out_group = UTIL.ofp_group_from_user(flow.get("out_group", dp.ofproto.OFPG_ANY))
    cookie = str_to_int(flow.get("cookie", 0))
    cookie_mask = str_to_int(flow.get("cookie_mask", 0))
    match = to_match(dp, flow.get("match", {}))

    stats = dp.ofproto_parser.OFPAggregateStatsRequest(
        dp, flags, table_id, out_port, out_group, cookie, cookie_mask, match
    )
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)

    flows = []
    for msg in msgs:
        body = msg.body
        flows.append(
            {
                "packet_count": body.packet_count,
                "byte_count": body.byte_count,
                "flow_count": body.flow_count,
            }
        )

    return wrap_dpid_dict(dp, flows, to_user)


def get_table_stats(dp, waiters, to_user=True):
    """Per table counters."""
    stats = dp.ofproto_parser.OFPTableStatsRequest(dp, 0)
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)

    tables = []
    for msg in msgs:
        for stat in msg.body:
            rendered = {
                "active_count": stat.active_count,
                "lookup_count": stat.lookup_count,
                "matched_count": stat.matched_count,
            }
            rendered["table_id"] = (
                UTIL.ofp_table_to_user(stat.table_id) if to_user else stat.table_id
            )
            tables.append(rendered)

    return wrap_dpid_dict(dp, tables, to_user)


def _table_feature_prop_to_str(dp, to_user):
    """The property type names to report, keyed by property type."""
    ofp = dp.ofproto
    names = {
        ofp.OFPTFPT_INSTRUCTIONS: "INSTRUCTIONS",
        ofp.OFPTFPT_INSTRUCTIONS_MISS: "INSTRUCTIONS_MISS",
        ofp.OFPTFPT_NEXT_TABLES: "NEXT_TABLES",
        ofp.OFPTFPT_NEXT_TABLES_MISS: "NEXT_TABLES_MISS",
        ofp.OFPTFPT_WRITE_ACTIONS: "WRITE_ACTIONS",
        ofp.OFPTFPT_WRITE_ACTIONS_MISS: "WRITE_ACTIONS_MISS",
        ofp.OFPTFPT_APPLY_ACTIONS: "APPLY_ACTIONS",
        ofp.OFPTFPT_APPLY_ACTIONS_MISS: "APPLY_ACTIONS_MISS",
        ofp.OFPTFPT_MATCH: "MATCH",
        ofp.OFPTFPT_WILDCARDS: "WILDCARDS",
        ofp.OFPTFPT_WRITE_SETFIELD: "WRITE_SETFIELD",
        ofp.OFPTFPT_WRITE_SETFIELD_MISS: "WRITE_SETFIELD_MISS",
        ofp.OFPTFPT_APPLY_SETFIELD: "APPLY_SETFIELD",
        ofp.OFPTFPT_APPLY_SETFIELD_MISS: "APPLY_SETFIELD_MISS",
        ofp.OFPTFPT_EXPERIMENTER: "EXPERIMENTER",
        ofp.OFPTFPT_EXPERIMENTER_MISS: "EXPERIMENTER_MISS",
    }
    if to_user:
        return names
    return {k: k for k in names}


def get_table_features(dp, waiters, to_user=True):
    """What each table can match on and do."""
    ofp = dp.ofproto
    stats = dp.ofproto_parser.OFPTableFeaturesStatsRequest(dp, 0, [])
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)

    prop_type = _table_feature_prop_to_str(dp, to_user)
    p_type_instructions = (ofp.OFPTFPT_INSTRUCTIONS, ofp.OFPTFPT_INSTRUCTIONS_MISS)
    p_type_next_tables = (ofp.OFPTFPT_NEXT_TABLES, ofp.OFPTFPT_NEXT_TABLES_MISS)
    p_type_actions = (
        ofp.OFPTFPT_WRITE_ACTIONS,
        ofp.OFPTFPT_WRITE_ACTIONS_MISS,
        ofp.OFPTFPT_APPLY_ACTIONS,
        ofp.OFPTFPT_APPLY_ACTIONS_MISS,
    )
    p_type_oxms = (
        ofp.OFPTFPT_MATCH,
        ofp.OFPTFPT_WILDCARDS,
        ofp.OFPTFPT_WRITE_SETFIELD,
        ofp.OFPTFPT_WRITE_SETFIELD_MISS,
        ofp.OFPTFPT_APPLY_SETFIELD,
        ofp.OFPTFPT_APPLY_SETFIELD_MISS,
    )

    tables = []
    for msg in msgs:
        for stat in msg.body:
            properties = []
            for prop in stat.properties:
                rendered = {"type": prop_type.get(prop.type, "UNKNOWN")}
                if prop.type in p_type_instructions:
                    rendered["instruction_ids"] = [
                        {"len": i.len, "type": i.type} for i in prop.instruction_ids
                    ]
                elif prop.type in p_type_next_tables:
                    rendered["table_ids"] = list(prop.table_ids)
                elif prop.type in p_type_actions:
                    rendered["action_ids"] = [
                        {"len": i.len, "type": i.type} for i in prop.action_ids
                    ]
                elif prop.type in p_type_oxms:
                    rendered["oxm_ids"] = [
                        {"hasmask": i.hasmask, "length": i.length, "type": i.type}
                        for i in prop.oxm_ids
                    ]
                properties.append(rendered)

            table = {
                "name": stat.name.decode("utf-8"),
                "metadata_match": stat.metadata_match,
                "metadata_write": stat.metadata_write,
                "config": stat.config,
                "max_entries": stat.max_entries,
                "properties": properties,
            }
            table["table_id"] = (
                UTIL.ofp_table_to_user(stat.table_id) if to_user else stat.table_id
            )
            tables.append(table)

    return wrap_dpid_dict(dp, tables, to_user)


def get_port_stats(dp, waiters, port=None, to_user=True):
    """Per port counters, for one port or for all of them."""
    port = dp.ofproto.OFPP_ANY if port is None else str_to_int(port)

    stats = dp.ofproto_parser.OFPPortStatsRequest(dp, 0, port)
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)

    ports = []
    for msg in msgs:
        for stat in msg.body:
            rendered = {
                "rx_packets": stat.rx_packets,
                "tx_packets": stat.tx_packets,
                "rx_bytes": stat.rx_bytes,
                "tx_bytes": stat.tx_bytes,
                "rx_dropped": stat.rx_dropped,
                "tx_dropped": stat.tx_dropped,
                "rx_errors": stat.rx_errors,
                "tx_errors": stat.tx_errors,
                "rx_frame_err": stat.rx_frame_err,
                "rx_over_err": stat.rx_over_err,
                "rx_crc_err": stat.rx_crc_err,
                "collisions": stat.collisions,
                "duration_sec": stat.duration_sec,
                "duration_nsec": stat.duration_nsec,
            }
            rendered["port_no"] = (
                UTIL.ofp_port_to_user(stat.port_no) if to_user else stat.port_no
            )
            ports.append(rendered)

    return wrap_dpid_dict(dp, ports, to_user)


def get_meter_stats(dp, waiters, meter_id=None, to_user=True):
    """Per meter counters, for one meter or for all of them."""
    meter_id = dp.ofproto.OFPM_ALL if meter_id is None else str_to_int(meter_id)

    stats = dp.ofproto_parser.OFPMeterStatsRequest(dp, 0, meter_id)
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)

    meters = []
    for msg in msgs:
        for stat in msg.body:
            rendered = {
                "len": stat.len,
                "flow_count": stat.flow_count,
                "packet_in_count": stat.packet_in_count,
                "byte_in_count": stat.byte_in_count,
                "duration_sec": stat.duration_sec,
                "duration_nsec": stat.duration_nsec,
                "band_stats": [
                    {
                        "packet_band_count": band.packet_band_count,
                        "byte_band_count": band.byte_band_count,
                    }
                    for band in stat.band_stats
                ],
            }
            rendered["meter_id"] = (
                UTIL.ofp_meter_to_user(stat.meter_id) if to_user else stat.meter_id
            )
            meters.append(rendered)

    return wrap_dpid_dict(dp, meters, to_user)


def get_meter_features(dp, waiters, to_user=True):
    """What the switch's meters can do."""
    ofp = dp.ofproto
    type_convert = {ofp.OFPMBT_DROP: "DROP", ofp.OFPMBT_DSCP_REMARK: "DSCP_REMARK"}
    capa_convert = {
        ofp.OFPMF_KBPS: "KBPS",
        ofp.OFPMF_PKTPS: "PKTPS",
        ofp.OFPMF_BURST: "BURST",
        ofp.OFPMF_STATS: "STATS",
    }

    stats = dp.ofproto_parser.OFPMeterFeaturesStatsRequest(dp, 0)
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)

    features = []
    for msg in msgs:
        for feature in msg.body:
            band_types = [
                v if to_user else k
                for k, v in type_convert.items()
                if (1 << k) & feature.band_types
            ]
            capabilities = [
                v if to_user else k
                for k, v in sorted(capa_convert.items())
                if k & feature.capabilities
            ]
            features.append(
                {
                    "max_meter": feature.max_meter,
                    "band_types": band_types,
                    "capabilities": capabilities,
                    "max_bands": feature.max_bands,
                    "max_color": feature.max_color,
                }
            )

    return wrap_dpid_dict(dp, features, to_user)


def get_meter_config(dp, waiters, meter_id=None, to_user=True):
    """The bands configured on one meter, or on all of them."""
    ofp = dp.ofproto
    flags = {
        ofp.OFPMF_KBPS: "KBPS",
        ofp.OFPMF_PKTPS: "PKTPS",
        ofp.OFPMF_BURST: "BURST",
        ofp.OFPMF_STATS: "STATS",
    }
    band_type = {
        ofp.OFPMBT_DROP: "DROP",
        ofp.OFPMBT_DSCP_REMARK: "DSCP_REMARK",
        ofp.OFPMBT_EXPERIMENTER: "EXPERIMENTER",
    }

    meter_id = ofp.OFPM_ALL if meter_id is None else str_to_int(meter_id)

    stats = dp.ofproto_parser.OFPMeterConfigStatsRequest(dp, 0, meter_id)
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)

    configs = []
    for msg in msgs:
        for config in msg.body:
            bands = []
            for band in config.bands:
                rendered = {"rate": band.rate, "burst_size": band.burst_size}
                rendered["type"] = (
                    band_type.get(band.type, "") if to_user else band.type
                )
                if band.type == ofp.OFPMBT_DSCP_REMARK:
                    rendered["prec_level"] = band.prec_level
                elif band.type == ofp.OFPMBT_EXPERIMENTER:
                    rendered["experimenter"] = band.experimenter
                bands.append(rendered)

            config_flags = [
                v if to_user else k
                for k, v in sorted(flags.items())
                if k & config.flags
            ]
            rendered_config = {"flags": config_flags, "bands": bands}
            rendered_config["meter_id"] = (
                UTIL.ofp_meter_to_user(config.meter_id) if to_user else config.meter_id
            )
            configs.append(rendered_config)

    return wrap_dpid_dict(dp, configs, to_user)


def get_group_stats(dp, waiters, group_id=None, to_user=True):
    """Per group counters, for one group or for all of them."""
    group_id = dp.ofproto.OFPG_ALL if group_id is None else str_to_int(group_id)

    stats = dp.ofproto_parser.OFPGroupStatsRequest(dp, 0, group_id)
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)

    groups = []
    for msg in msgs:
        for stat in msg.body:
            rendered = {
                "length": stat.length,
                "ref_count": stat.ref_count,
                "packet_count": stat.packet_count,
                "byte_count": stat.byte_count,
                "duration_sec": stat.duration_sec,
                "duration_nsec": stat.duration_nsec,
                "bucket_stats": [
                    {
                        "packet_count": bucket.packet_count,
                        "byte_count": bucket.byte_count,
                    }
                    for bucket in stat.bucket_stats
                ],
            }
            rendered["group_id"] = (
                UTIL.ofp_group_to_user(stat.group_id) if to_user else stat.group_id
            )
            groups.append(rendered)

    return wrap_dpid_dict(dp, groups, to_user)


def get_group_features(dp, waiters, to_user=True):
    """What the switch's groups can do."""
    ofp = dp.ofproto
    type_convert = {
        ofp.OFPGT_ALL: "ALL",
        ofp.OFPGT_SELECT: "SELECT",
        ofp.OFPGT_INDIRECT: "INDIRECT",
        ofp.OFPGT_FF: "FF",
    }
    cap_convert = {
        ofp.OFPGFC_SELECT_WEIGHT: "SELECT_WEIGHT",
        ofp.OFPGFC_SELECT_LIVENESS: "SELECT_LIVENESS",
        ofp.OFPGFC_CHAINING: "CHAINING",
        ofp.OFPGFC_CHAINING_CHECKS: "CHAINING_CHECKS",
    }
    act_convert = {
        ofp.OFPAT_OUTPUT: "OUTPUT",
        ofp.OFPAT_COPY_TTL_OUT: "COPY_TTL_OUT",
        ofp.OFPAT_COPY_TTL_IN: "COPY_TTL_IN",
        ofp.OFPAT_SET_MPLS_TTL: "SET_MPLS_TTL",
        ofp.OFPAT_DEC_MPLS_TTL: "DEC_MPLS_TTL",
        ofp.OFPAT_PUSH_VLAN: "PUSH_VLAN",
        ofp.OFPAT_POP_VLAN: "POP_VLAN",
        ofp.OFPAT_PUSH_MPLS: "PUSH_MPLS",
        ofp.OFPAT_POP_MPLS: "POP_MPLS",
        ofp.OFPAT_SET_QUEUE: "SET_QUEUE",
        ofp.OFPAT_GROUP: "GROUP",
        ofp.OFPAT_SET_NW_TTL: "SET_NW_TTL",
        ofp.OFPAT_DEC_NW_TTL: "DEC_NW_TTL",
        ofp.OFPAT_SET_FIELD: "SET_FIELD",
        ofp.OFPAT_PUSH_PBB: "PUSH_PBB",
        ofp.OFPAT_POP_PBB: "POP_PBB",
    }

    stats = dp.ofproto_parser.OFPGroupFeaturesStatsRequest(dp, 0)
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)

    features = []
    for msg in msgs:
        feature = msg.body
        types = [
            v if to_user else k
            for k, v in type_convert.items()
            if (1 << k) & feature.types
        ]
        capabilities = [
            v if to_user else k
            for k, v in cap_convert.items()
            if k & feature.capabilities
        ]
        if to_user:
            max_groups = [{v: feature.max_groups[k]} for k, v in type_convert.items()]
        else:
            max_groups = feature.max_groups

        actions = []
        for group_type, group_name in type_convert.items():
            acts = [
                v if to_user else k
                for k, v in act_convert.items()
                if (1 << k) & feature.actions[group_type]
            ]
            actions.append({group_name if to_user else group_type: acts})

        features.append(
            {
                "types": types,
                "capabilities": capabilities,
                "max_groups": max_groups,
                "actions": actions,
            }
        )

    return wrap_dpid_dict(dp, features, to_user)


def get_group_desc(dp, waiters, to_user=True):
    """The buckets of every group on the switch."""
    ofp = dp.ofproto
    type_convert = {
        ofp.OFPGT_ALL: "ALL",
        ofp.OFPGT_SELECT: "SELECT",
        ofp.OFPGT_INDIRECT: "INDIRECT",
        ofp.OFPGT_FF: "FF",
    }

    stats = dp.ofproto_parser.OFPGroupDescStatsRequest(dp, 0)
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)

    descs = []
    for msg in msgs:
        for stat in msg.body:
            buckets = []
            for bucket in stat.buckets:
                actions = [
                    action_to_str(action) if to_user else action
                    for action in bucket.actions
                ]
                buckets.append(
                    {
                        "weight": bucket.weight,
                        "watch_port": bucket.watch_port,
                        "watch_group": bucket.watch_group,
                        "actions": actions,
                    }
                )

            desc = {"buckets": buckets}
            if to_user:
                desc["group_id"] = UTIL.ofp_group_to_user(stat.group_id)
                desc["type"] = type_convert.get(stat.type)
            else:
                desc["group_id"] = stat.group_id
                desc["type"] = stat.type
            descs.append(desc)

    return wrap_dpid_dict(dp, descs, to_user)


def get_port_desc(dp, waiters, to_user=True):
    """The description of every port on the switch."""
    stats = dp.ofproto_parser.OFPPortDescStatsRequest(dp, 0)
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)

    descs = []
    for msg in msgs:
        for stat in msg.body:
            desc = {
                "hw_addr": stat.hw_addr,
                "name": stat.name.decode("utf-8", errors="replace"),
                "config": stat.config,
                "state": stat.state,
                "curr": stat.curr,
                "advertised": stat.advertised,
                "supported": stat.supported,
                "peer": stat.peer,
                "curr_speed": stat.curr_speed,
                "max_speed": stat.max_speed,
            }
            desc["port_no"] = (
                UTIL.ofp_port_to_user(stat.port_no) if to_user else stat.port_no
            )
            descs.append(desc)

    return wrap_dpid_dict(dp, descs, to_user)


def get_role(dp, waiters, to_user=True):
    """The controller's role on this datapath."""
    stats = dp.ofproto_parser.OFPRoleRequest(
        dp, dp.ofproto.OFPCR_ROLE_NOCHANGE, generation_id=0
    )
    msgs = []
    send_stats_request(dp, stats, waiters, msgs, LOG)

    descs = []
    for msg in msgs:
        desc = msg.to_jsondict()[msg.__class__.__name__]
        if to_user:
            desc["role"] = UTIL.ofp_role_to_user(desc["role"])
        descs.append(desc)

    return {str(dp.id): descs}


# -- mods --------------------------------------------------------------------


def mod_flow_entry(dp, flow, cmd):
    """Send the flow mod ``cmd`` described by ``flow``."""
    cookie = str_to_int(flow.get("cookie", 0))
    cookie_mask = str_to_int(flow.get("cookie_mask", 0))
    table_id = UTIL.ofp_table_from_user(flow.get("table_id", 0))
    idle_timeout = str_to_int(flow.get("idle_timeout", 0))
    hard_timeout = str_to_int(flow.get("hard_timeout", 0))
    priority = str_to_int(flow.get("priority", 0))
    buffer_id = UTIL.ofp_buffer_from_user(
        flow.get("buffer_id", dp.ofproto.OFP_NO_BUFFER)
    )
    out_port = UTIL.ofp_port_from_user(flow.get("out_port", dp.ofproto.OFPP_ANY))
    out_group = UTIL.ofp_group_from_user(flow.get("out_group", dp.ofproto.OFPG_ANY))
    flags = str_to_int(flow.get("flags", 0))
    match = to_match(dp, flow.get("match", {}))
    inst = to_actions(dp, flow.get("actions", []))

    flow_mod = dp.ofproto_parser.OFPFlowMod(
        dp,
        cookie,
        cookie_mask,
        table_id,
        cmd,
        idle_timeout,
        hard_timeout,
        priority,
        buffer_id,
        out_port,
        out_group,
        flags,
        match,
        inst,
    )
    send_msg(dp, flow_mod, LOG)


def mod_meter_entry(dp, meter, cmd):
    """Send the meter mod ``cmd`` described by ``meter``."""
    _c65of_ofctl.mod_meter_entry(dp, meter, cmd)


def mod_group_entry(dp, group, cmd):
    """Send the group mod ``cmd`` described by ``group``."""
    ofp = dp.ofproto
    type_convert = {
        "ALL": ofp.OFPGT_ALL,
        "SELECT": ofp.OFPGT_SELECT,
        "INDIRECT": ofp.OFPGT_INDIRECT,
        "FF": ofp.OFPGT_FF,
    }
    group_type = type_convert.get(group.get("type", "ALL"))
    if group_type is None:
        LOG.error("Unknown group type: %s", group.get("type"))

    group_id = UTIL.ofp_group_from_user(group.get("group_id", 0))

    buckets = []
    for bucket in group.get("buckets", []):
        weight = str_to_int(bucket.get("weight", 0))
        watch_port = str_to_int(bucket.get("watch_port", ofp.OFPP_ANY))
        watch_group = str_to_int(bucket.get("watch_group", ofp.OFPG_ANY))
        actions = []
        for dic in bucket.get("actions", []):
            action = to_action(dp, dic)
            if action is not None:
                actions.append(action)
        buckets.append(
            dp.ofproto_parser.OFPBucket(weight, watch_port, watch_group, actions)
        )

    group_mod = dp.ofproto_parser.OFPGroupMod(dp, cmd, group_type, group_id, buckets)
    send_msg(dp, group_mod, LOG)


def mod_port_behavior(dp, port_config):
    """Send the port mod described by ``port_config``."""
    port_no = UTIL.ofp_port_from_user(port_config.get("port_no", 0))
    hw_addr = str(port_config.get("hw_addr"))
    config = str_to_int(port_config.get("config", 0))
    mask = str_to_int(port_config.get("mask", 0))
    advertise = str_to_int(port_config.get("advertise"))

    port_mod = dp.ofproto_parser.OFPPortMod(
        dp, port_no, hw_addr, config, mask, advertise
    )
    send_msg(dp, port_mod, LOG)


def set_role(dp, role):
    """Ask the switch to give this controller the role in ``role``."""
    requested = UTIL.ofp_role_from_user(role.get("role", dp.ofproto.OFPCR_ROLE_EQUAL))
    role_request = dp.ofproto_parser.OFPRoleRequest(dp, requested, 0)
    send_msg(dp, role_request, LOG)


def send_experimenter(dp, exp, logger=None):
    """Send the experimenter message described by ``exp``."""
    experimenter = exp.get("experimenter", 0)
    exp_type = exp.get("exp_type", 0)
    data_type = exp.get("data_type", "ascii")

    data = exp.get("data", "")
    if data_type == "base64":
        data = base64.b64decode(data)
    elif data_type == "ascii":
        data = data.encode("ascii")
    else:
        (logger or LOG).error("Unknown data type: %s", data_type)
        return

    expmsg = dp.ofproto_parser.OFPExperimenter(dp, experimenter, exp_type, data)
    send_msg(dp, expmsg, logger)
