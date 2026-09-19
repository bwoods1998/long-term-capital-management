import unittest

from league.constitution import CONSTITUTION, PINNED_DIGEST, digest


class ConstitutionTest(unittest.TestCase):
    def test_the_constitution_is_pinned(self):
        """A change to any threshold changes the digest, and this test, the ledger's `ops.started`
        rows and CI's path guard all notice. Only the owner re-pins it."""
        self.assertEqual(digest(), PINNED_DIGEST)

    def test_the_numbers_the_owner_set(self):
        self.assertEqual(CONSTITUTION["budgets"]["sail_month_usd"], "100")
        self.assertEqual(CONSTITUTION["budgets"]["openai_month_usd"], "100")
        self.assertEqual(CONSTITUTION["order_caps"]["max_order_usd"], "75")
        self.assertEqual(CONSTITUTION["rungs"]["2"]["max_position_usd"], "10")
        self.assertEqual(CONSTITUTION["rungs"]["3"]["kelly_fraction"], 0.25)
        self.assertEqual(CONSTITUTION["ladder"]["alpha"], 0.05)

    def test_a_changed_threshold_changes_the_digest(self):
        import copy

        changed = copy.deepcopy(CONSTITUTION)
        changed["ladder"]["alpha"] = 0.5
        self.assertNotEqual(digest(changed), PINNED_DIGEST)


if __name__ == "__main__":
    unittest.main()
