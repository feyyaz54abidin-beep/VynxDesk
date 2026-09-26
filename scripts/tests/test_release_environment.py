"""Production identities must be usable and must not be the debug identity."""
import base64
import contextlib
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_release_contract as release


class ReleaseEnvironmentTests(unittest.TestCase):
    def check(self, host="relay.customer.test", key=None):
        if key is None:
            key = base64.b64encode(bytes(range(32))).decode("ascii")
        with patch.dict(os.environ, {
            "VYNXDESK_RENDEZVOUS_SERVER": host,
            "VYNXDESK_RENDEZVOUS_PUB_KEY": key,
        }):
            release.require_release_environment()

    def test_valid_hostname_and_key(self):
        self.check()

    def test_valid_hostname_port(self):
        self.check(host="relay.customer.test:21116")

    def test_valid_ip_literals(self):
        self.check(host="192.0.2.10:21116")
        self.check(host="[2001:db8::1]:21116")

    def test_invalid_ip_and_repeated_root_dot(self):
        for host in ("999.999.999.999", "relay.customer.test..", "host:99999999999999999"):
            with self.subTest(host=host), self.assertRaises(release.ContractError):
                self.check(host=host)

    def test_blank_inputs_rejected(self):
        with self.assertRaises(release.ContractError):
            self.check(host="  ", key="")

    def test_reject_debug_server(self):
        for host in ("rs-ny.rustdesk.com", "RS-NY.RUSTDESK.COM:21116", "rs-ny.rustdesk.com."):
            with self.subTest(host=host), self.assertRaises(release.ContractError):
                self.check(host=host)

    def test_reject_debug_key(self):
        with self.assertRaises(release.ContractError):
            self.check(key="OeVuKk5nlHiXp+APNn0Y3pC1Iwpwn44JGqrQCsWqmBw=")

    def test_reject_invalid_host(self):
        for host in ("https://relay.customer.test", "relay.customer.test/path", "bad host", "host:0", "host:65536", "host:no", "host\nother", "-bad.test", "host:21116:80"):
            with self.subTest(host=host), self.assertRaises(release.ContractError):
                self.check(host=host)

    def test_reject_invalid_base64_key(self):
        for key in ("not-a-key", "!!!!", "A" * 44, " " + base64.b64encode(bytes(range(32))).decode("ascii")):
            with self.subTest(key=key), self.assertRaises(release.ContractError):
                self.check(key=key)

    def test_reject_wrong_key_length_and_zero_key(self):
        for value in (b"x" * 31, b"x" * 33, bytes(32)):
            with self.subTest(length=len(value)), self.assertRaises(release.ContractError):
                self.check(key=base64.b64encode(value).decode("ascii"))

    def test_error_does_not_echo_configuration(self):
        host = "bad-secret-host/path"
        key = "PRIVATE-INPUT-MUST-NOT-BE-LOGGED"
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            try:
                self.check(host=host, key=key)
            except release.ContractError as error:
                self.assertNotIn(host, str(error))
                self.assertNotIn(key, str(error))
        self.assertNotIn(host, output.getvalue())
        self.assertNotIn(key, output.getvalue())


if __name__ == "__main__":
    unittest.main()
