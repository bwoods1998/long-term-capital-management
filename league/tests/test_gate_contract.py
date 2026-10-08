"""THE GATE'S CONTRACT (Oct 8, 2026): the readers are shown the context's computed fields too."""

import unittest

from league.gym.review_contract import review_contract
from league.swarm import gate


class GateContract(unittest.TestCase):
    def test_chainview_greeks_are_in_the_contract_the_readers_see(self):
        fields = gate.gate_contract()["context_fields"]["ChainView"]
        for name in ("iv", "delta", "gamma", "theta", "vega"):
            self.assertIn(name, fields)
        # the slots are all still there, in their order, ahead of the computed ones
        self.assertEqual(fields[:len(review_contract()["context_fields"]["ChainView"])],
                         review_contract()["context_fields"]["ChainView"])

    def test_the_gym_contract_alone_lacks_them_which_is_why_the_gate_adds_them(self):
        self.assertNotIn("delta", review_contract()["context_fields"]["ChainView"])

    def test_the_gate_contract_has_its_own_hash_and_a_fact_about_computed_fields(self):
        c = gate.gate_contract()
        self.assertNotEqual(c["sha256"], review_contract()["sha256"])
        self.assertIn("computed", c["facts"])
        self.assertIn("delta", c["facts"]["computed"])

    def test_bands_and_incubator_compare_reviews_against_the_gate_contract(self):
        from league.swarm import bands, incubator
        import inspect
        for mod in (bands, incubator):
            src = inspect.getsource(mod)
            self.assertNotIn("from ..gym.review_contract import review_contract", src)
            self.assertIn("gate_contract", src)


if __name__ == "__main__":
    unittest.main()
