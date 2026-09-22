"""SYNTHETIC repair drill 20260922t152804: proves the engineer revises against CI's failure text."""

import unittest

from league.tools.repair_drill import checksum


class RepairDrillTest(unittest.TestCase):
    def test_checksum_adds_every_value(self):
        self.assertEqual(checksum([1, 2, 3]), 6)
