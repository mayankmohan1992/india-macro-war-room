"""The dashboard payload must never be visible half-written.

Measured on 2026-11-10: verify_dashboard.py started while build_dashboard.py was rebuilding, and it
died parsing warroom_data.json with `JSONDecodeError: Expecting property name enclosed in double
quotes ... char 40020`. The build was correct; the reader happened to look during a plain
write_text(), which truncates before it fills. A gate that reads a torn file reports a defect that
does not exist, which is the one thing a verification gate must never do.

Runs on the standard library alone:  python -m unittest discover -s tests -v
"""

import json
import pathlib
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import build_dashboard                                            # noqa: E402


def payload(n):
    return json.dumps({"build": n, "pad": "x" * 200_000}, indent=1)


class AtomicWrite(unittest.TestCase):
    def test_a_concurrent_reader_never_sees_a_partial_file(self):
        with tempfile.TemporaryDirectory() as td:
            target = pathlib.Path(td) / "warroom_data.json"
            build_dashboard._atomic_write(target, payload(0))

            torn, reads, stop = [], [0], threading.Event()

            def reader():
                while not stop.is_set():
                    try:
                        json.loads(target.read_text())
                        reads[0] += 1
                    except FileNotFoundError:
                        pass                      # not part of the property; replace never unlinks
                    except json.JSONDecodeError as exc:
                        torn.append(exc)

            th = threading.Thread(target=reader, daemon=True)
            th.start()
            try:
                for n in range(1, 120):
                    build_dashboard._atomic_write(target, payload(n))
            finally:
                stop.set()
                th.join(timeout=5)

            self.assertGreater(reads[0], 0, "the reader never got a turn; test proves nothing")
            self.assertEqual(torn, [], f"{len(torn)} torn read(s) in {reads[0] + len(torn)} attempts")

    def test_no_temp_files_are_left_behind(self):
        with tempfile.TemporaryDirectory() as td:
            target = pathlib.Path(td) / "dashboard.html"
            build_dashboard._atomic_write(target, "<html></html>")
            self.assertEqual([p.name for p in pathlib.Path(td).iterdir()], ["dashboard.html"])


if __name__ == "__main__":
    unittest.main()
