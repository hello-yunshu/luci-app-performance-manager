import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from po_parser import missing_msgids, parse_po_msgids  # noqa: E402


class PoParserTests(unittest.TestCase):
    def test_po_single_line_msgid(self):
        self.assertEqual(parse_po_msgids('msgid "Goal"\nmsgstr "目标"\n'), ["Goal"])

    def test_po_multiline_msgid(self):
        self.assertEqual(
            parse_po_msgids('msgid ""\n"foo "\n"bar"\nmsgstr ""\n'),
            ["foo bar"],
        )

    def test_po_escaped_quote(self):
        self.assertEqual(
            parse_po_msgids('msgid "say \\\"hi\\\" \\\\path\\n"\nmsgstr ""\n'),
            ['say "hi" \\path\n'],
        )

    def test_po_missing_js_literal_fails(self):
        self.assertEqual(
            missing_msgids('msgid "Present"\nmsgstr ""\n', {"Present", "Missing"}),
            ["Missing"],
        )
