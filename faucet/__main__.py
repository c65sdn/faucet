#!/usr/bin/env python3

"""Launch script for Faucet/Gauge.

Hosts an in-process equivalent of the legacy ``osken-manager`` script so
that Faucet keeps its existing CLI surface on os-ken >= 4.0, which removed
the ``os_ken.cmd`` package and the ``osken-manager`` console script.
"""

# Copyright (C) 2015 Brad Cowie, Christopher Lorier and Joe Stringer.
# Copyright (C) 2015 Research and Education Advanced Network New Zealand Ltd.
# Copyright (C) 2015--2019 The Contributors
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

# pylint: disable=wrong-import-position
import os
import sys

# When invoked as ``python /path/to/faucet/__main__.py`` (which is how the
# mininet integration tests start Faucet) Python puts the script's directory
# at ``sys.path[0]``, which shadows the ``faucet`` package with the
# ``faucet/faucet.py`` *submodule*. ``import faucet.valve_ryuapp`` then fails
# with "'faucet' is not a package". Strip the entry before any other import.
_self_dir = os.path.dirname(os.path.abspath(__file__))
while _self_dir in sys.path:
    sys.path.remove(_self_dir)
del _self_dir

# Faucet still relies on eventlet (greenthread ``thread.dead`` checks,
# ``hub.kill``, beka/chewie). os-ken 4.0 flipped the default hub to
# ``native``; pin back to eventlet (an explicit env still wins) and run
# ``eventlet.monkey_patch()`` *before* importing ``argparse``/``logging`` so
# eventlet doesn't log "RLock(s) were not greened".
os.environ.setdefault("OSKEN_HUB_TYPE", "eventlet")
if os.environ["OSKEN_HUB_TYPE"] == "eventlet":
    import eventlet  # pylint: disable=import-error

    eventlet.monkey_patch()

import argparse
import logging

from pbr.version import VersionInfo

if sys.version_info < (3,) or sys.version_info < (3, 5):
    raise ImportError(
        """You are trying to run faucet on python {py}

Faucet is not compatible with python {py}, please upgrade to python 3.5 or newer.""".format(
            py=".".join([str(v) for v in sys.version_info[:3]])
        )
    )

RYU_OPTIONAL_ARGS = [
    ("ca-certs", "CA certificates"),
    (
        "config-dir",
        """Path to a config directory to pull `*.conf` files
                      from. This file set is sorted, so as to provide a
                      predictable parse order if individual options are
                      over-ridden. The set is parsed after the file(s)
                      specified via previous --config-file, arguments hence
                      over-ridden options in the directory take precedence.""",
    ),
    (
        "config-file",
        """Path to a config file to use. Multiple config files
                       can be specified, with values in later files taking
                       precedence. Defaults to None.""",
        "/etc/faucet/ryu.conf",
    ),
    ("ctl-cert", "controller certificate"),
    ("ctl-privkey", "controller private key"),
    ("default-log-level", "default log level"),
    ("log-config-file", "Path to a logging config file to use"),
    ("log-dir", "log file directory"),
    ("log-file", "log file name"),
    ("log-file-mode", "default log file permission"),
    ("observe-links", "observe link discovery events"),
    ("ofp-listen-host", "openflow listen host (default 0.0.0.0)"),
    ("ofp-ssl-listen-port", "openflow ssl listen port (default: 6653)"),
    (
        "ofp-switch-address-list",
        """list of IP address and port pairs (default empty).
                                   e.g., "127.0.0.1:6653,[::1]:6653""",
    ),
    (
        "ofp-switch-connect-interval",
        "interval in seconds to connect to switches (default 1)",
    ),
    ("ofp-tcp-listen-port", "openflow tcp listen port (default: 6653)"),
    ("pid-file", "pid file name"),
    ("user-flags", "Additional flags file for user applications"),
]


def parse_args(sys_args):
    """Parse Faucet/Gauge arguments.

    Returns:
        argparse.Namespace: command line arguments
    """

    args = argparse.ArgumentParser(prog="faucet", description="Faucet SDN Controller")
    args.add_argument("--gauge", action="store_true", help="run Gauge instead")
    args.add_argument(
        "-v", "--verbose", action="store_true", help="produce verbose output"
    )
    args.add_argument(
        "-V", "--version", action="store_true", help="print version and exit"
    )
    args.add_argument("--use-stderr", action="store_true", help="log to standard error")
    args.add_argument("--use-syslog", action="store_true", help="output to syslog")
    args.add_argument(
        "--ryu-app-lists",
        action="append",
        help="add Ryu app (can be specified multiple times)",
        metavar="APP",
    )

    for ryu_arg in RYU_OPTIONAL_ARGS:
        if len(ryu_arg) >= 3:
            args.add_argument(
                "--ryu-%s" % ryu_arg[0], help=ryu_arg[1], default=ryu_arg[2]
            )
        else:
            args.add_argument("--ryu-%s" % ryu_arg[0], help=ryu_arg[1])

    return args.parse_args(sys_args)


def print_version():
    """Print version number and exit."""
    version = VersionInfo("c65faucet").semantic_version().release_string()
    message = "c65faucet %s" % version
    print(message)


def build_ryu_args(argv):
    """Translate Faucet CLI flags into the os-ken cfg arguments.

    Returns the list of ``--config-file=...`` style arguments and the
    Ryu/os-ken application module names to load. Returns an empty list
    when there is nothing to run (e.g. ``--version``).
    """
    args = parse_args(argv[1:])

    # Checking version number?
    if args.version:
        print_version()
        return []

    prog = os.path.basename(argv[0])
    ryu_args = []

    # Handle log location
    if args.use_stderr:
        ryu_args.append("--use-stderr")
    if args.use_syslog:
        ryu_args.append("--use-syslog")

    # Verbose output?
    if args.verbose:
        ryu_args.append("--verbose")

    for arg, val in vars(args).items():
        if not val or not arg.startswith("ryu"):
            continue
        if arg == "ryu_app_lists":
            continue
        if arg == "ryu_config_file" and not os.path.isfile(val):
            continue
        arg_name = arg.replace("ryu_", "").replace("_", "-")
        ryu_args.append("--%s=%s" % (arg_name, val))

    # Running Faucet or Gauge?
    if args.gauge or os.path.basename(prog) == "gauge":
        ryu_args.append("faucet.gauge")
    else:
        ryu_args.append("faucet.faucet")

    # Check for additional Ryu apps.
    if args.ryu_app_lists:
        ryu_args.extend(args.ryu_app_lists)

    return ryu_args


def _maybe_load_user_flags(argv):
    """Pre-import the file passed via ``--user-flags`` so it can register
    additional oslo.config options before CLI parsing happens."""
    try:
        idx = list(argv).index("--user-flags")
        user_flags_file = argv[idx + 1]
    except (ValueError, IndexError):
        return
    if not (user_flags_file and os.path.isfile(user_flags_file)):
        return
    # pylint: disable=import-outside-toplevel
    from os_ken.utils import _import_module_file

    _import_module_file(user_flags_file)


def _run_osken_manager(argv):
    """Run an in-process equivalent of the ``osken-manager`` script.

    Mirrors ``os_ken.cmd.manager.main`` from os-ken < 4.0. os-ken 4.0
    deleted the ``os_ken.cmd`` package along with the ``osken-manager``
    console script entry point, so we drive ``AppManager`` directly using
    the same building blocks (``cfg``, ``log``, ``flags``, ``hub``) which
    are still exported.
    """
    # ``OSKEN_HUB_TYPE`` is pinned and ``eventlet.monkey_patch()`` has
    # already run at module top.
    # pylint: disable=import-outside-toplevel
    from os_ken.lib import hub

    hub.patch(thread=False)

    from os_ken import __version__ as osken_version
    from os_ken import cfg
    from os_ken import flags  # pylint: disable=unused-import  # registers cfg opts
    from os_ken import log
    from os_ken.base.app_manager import AppManager

    del flags  # quiet linters: imported for its registration side-effect.

    log.early_init_log(logging.DEBUG)

    conf = cfg.CONF
    conf.register_cli_opts(
        [
            cfg.ListOpt("app-lists", default=[], help="application module name to run"),
            cfg.MultiStrOpt(
                "app",
                positional=True,
                default=[],
                help="application module name to run",
            ),
            cfg.StrOpt("pid-file", default=None, help="pid file name"),
            cfg.BoolOpt(
                "enable-debugger",
                default=False,
                help="don't overwrite Python standard threading library "
                "(use only for debugging)",
            ),
            cfg.StrOpt(
                "user-flags",
                default=None,
                help="Additional flags file for user applications",
            ),
        ]
    )

    _maybe_load_user_flags(argv)

    try:
        conf(
            args=argv,
            prog="faucet",
            project="os_ken",
            version="faucet %s" % osken_version,
            default_config_files=["/usr/local/etc/os_ken/os_ken.conf"],
        )
    except cfg.ConfigFilesNotFoundError:
        conf(
            args=argv,
            prog="faucet",
            project="os_ken",
            version="faucet %s" % osken_version,
        )

    log.init_log()
    logger = logging.getLogger(__name__)

    if not conf.enable_debugger:
        hub.patch(thread=True)

    if conf.pid_file:
        with open(conf.pid_file, "w", encoding="utf-8") as pid_file:
            pid_file.write(str(os.getpid()))

    app_lists = conf.app_lists + conf.app
    if not app_lists:
        app_lists = ["os_ken.controller.ofp_handler"]

    app_mgr = AppManager.get_instance()
    app_mgr.load_apps(app_lists)
    contexts = app_mgr.create_contexts()
    services = list(app_mgr.instantiate_apps(**contexts))

    try:
        hub.joinall(services)
    except KeyboardInterrupt:
        logger.debug("Keyboard Interrupt received, shutting down")
    finally:
        app_mgr.close()


def main():
    """Main program."""
    ryu_args = build_ryu_args(sys.argv)
    if ryu_args:
        _run_osken_manager(ryu_args)


if __name__ == "__main__":
    main()
