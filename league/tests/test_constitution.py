import copy
import unittest
from league.constitution import CONSTITUTION, PINNED_DIGEST, digest, money_digest, options_money_problems

class ConstitutionTest(unittest.TestCase):
    def test_pinned_options_policy_has_no_retired_rules(self):
        self.assertEqual(digest(),PINNED_DIGEST)
        self.assertEqual(set(CONSTITUTION),{'version','options_money'})
        self.assertEqual(options_money_problems(),[])
    def test_money_changes_revoke_the_digest_but_document_version_does_not(self):
        changed=copy.deepcopy(CONSTITUTION);changed['version']+=1
        self.assertEqual(money_digest(changed),money_digest())
        changed['options_money']['probe']['floor_usd']='61'
        self.assertNotEqual(money_digest(changed),money_digest())
    def test_outside_run_authority_is_refused(self):
        changed=copy.deepcopy(CONSTITUTION);changed['options_money']['book_share']='1.1'
        self.assertTrue(options_money_problems(changed))
