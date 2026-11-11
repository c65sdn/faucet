#!/usr/bin/env python3

"""Unit tests for the command wrappers and popen helpers in clib.mininet_test_util."""

import os
import subprocess
import threading
import time
from types import SimpleNamespace
from unittest import TestCase, main

from clib import mininet_test_util


class TimeoutWrapperTest(TestCase):
    """The wrappers must bound a command without touching its output or environment."""

    CLEAN_ENV = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}

    def _run(self, cmd):
        start = time.monotonic()
        result = subprocess.run(
            ["sh", "-c", cmd],
            stdin=mininet_test_util.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.CLEAN_ENV,
            close_fds=True,
            check=False,
        )
        return result, time.monotonic() - start

    def test_hard_timeout_kills(self):
        """SIGKILL wrapper stops a long-running command"""
        result, elapsed = self._run(mininet_test_util.timeout_cmd("sleep 30", 1))
        self.assertNotEqual(result.returncode, 0)
        self.assertLess(elapsed, 15)

    def test_soft_timeout_terminates(self):
        """SIGTERM wrapper stops a long-running command"""
        result, elapsed = self._run(mininet_test_util.timeout_soft_cmd("sleep 30", 1))
        self.assertNotEqual(result.returncode, 0)
        self.assertLess(elapsed, 15)

    def test_soft_timeout_is_not_sigkill(self):
        """Soft wrapper must not escalate to SIGKILL"""
        cmd = mininet_test_util.timeout_soft_cmd("true", 5)
        self.assertNotIn("-sKILL", cmd)

    def test_wrapped_env_has_no_ld_preload(self):
        """Wrapper must not inject a preloaded library into the command"""
        result, _elapsed = self._run(mininet_test_util.timeout_cmd("env", 15))
        self.assertEqual(result.returncode, 0)
        self.assertNotIn(b"LD_PRELOAD", result.stdout)

    def test_wrapped_output_unchanged(self):
        """Wrapped command output passes through unaltered"""
        result, _elapsed = self._run(mininet_test_util.timeout_cmd("printf out-ok", 15))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"out-ok")
        self.assertEqual(result.stderr, b"")


class DrainPopenTest(TestCase):
    """drain_popen must consume each stream exactly once, until EOF."""

    def _fake_popen(self, payload):
        read_fd, write_fd = os.pipe()
        write_end = os.fdopen(write_fd, "wb")

        def writer():
            write_end.write(payload)
            write_end.close()

        threading.Thread(target=writer, daemon=True).start()
        return SimpleNamespace(stdout=os.fdopen(read_fd, "rb"))

    def _drain(self, payloads):
        popens = {object(): self._fake_popen(payload) for payload in payloads}
        try:
            return mininet_test_util.drain_popen(popens)
        finally:
            for fake_popen in popens.values():
                fake_popen.stdout.close()

    def test_returns_all_output(self):
        """All lines written before EOF come back, unaltered"""
        self.assertEqual(self._drain([b"first\nsecond\n"]), "first\nsecond\n")

    def test_empty_stream(self):
        """A stream with no data drains to the empty string"""
        self.assertEqual(self._drain([b""]), "")

    def test_returns_output_beyond_pipe_buffer(self):
        """Output larger than a pipe buffer is not truncated"""
        payload = (b"0123456789abcdef" * 8192) + b"\n"
        self.assertEqual(len(self._drain([payload])), len(payload))

    def test_multiple_streams(self):
        """Output of every stream in the dict is returned"""
        drained = self._drain([b"alpha\n", b"beta\n"])
        self.assertIn("alpha\n", drained)
        self.assertIn("beta\n", drained)


if __name__ == "__main__":
    main()
