import io
import json
from pathlib import Path
import tempfile
import unittest

import lab


class MonitorStream:
    def __init__(self, replies):
        self.replies = io.BytesIO(b"".join(json.dumps(x).encode() + b"\n" for x in replies))
        self.requests = []

    def write(self, data):
        self.requests.append(json.loads(data))

    def readline(self):
        return self.replies.readline()


class LabTests(unittest.TestCase):
    def test_monitor_skips_events_before_command_reply(self):
        monitor = object.__new__(lab.QMP)
        monitor.stream = MonitorStream([{"event": "RESET"}, {"return": {"status": "running"}}])
        self.assertEqual(monitor.command("query-status"), {"status": "running"})
        self.assertEqual(monitor.stream.requests, [{"execute": "query-status"}])

    def test_monitor_reports_command_errors(self):
        monitor = object.__new__(lab.QMP)
        monitor.stream = MonitorStream([{"error": {"class": "GenericError", "desc": "bad argument"}}])
        with self.assertRaisesRegex(RuntimeError, "bad argument"):
            monitor.command("screendump", {"filename": "invalid"})

    def test_monitor_reports_disconnect(self):
        monitor = object.__new__(lab.QMP)
        monitor.stream = MonitorStream([])
        with self.assertRaises(ConnectionError):
            monitor.command("query-status")

    def test_corrupt_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image"
            image.write_bytes(b"corrupt")
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                lab.verify_digest(image, "0" * 64)


if __name__ == "__main__":
    unittest.main()
