"""Automatic public proposals are helper repairs only; private programs never enter git."""
from decimal import Decimal
import unittest
from league.merton import parse_proposal
class Proposal(unittest.TestCase):
 def test_only_helper_and_matching_test_paths_are_carried(self):
  answer={'files':[{'path':'league/tools/mean.py','content':'def mean(xs):\n    return sum(xs)/len(xs)\n'}, {'path':'league/tests/test_tool_mean.py','content':'import unittest\n'}, {'path':'league/live/money.py','content':'x=1'}, {'path':'league/strategies/learned.py','content':'x=1'}]}
  proposal=parse_proposal('engineer',answer,Decimal('.5'))
  self.assertEqual(len(proposal.files),2);self.assertEqual(len(proposal.dropped),2)
 def test_path_escape_unknown_role_code_io_and_duplicates_are_refused(self):
  for role,path,code in [('operator','league/config.json','{}'),('engineer','league/tools/../ci.py','x=1'),('engineer','league/tools/net.py','import os\n')]:
   self.assertFalse(parse_proposal(role,{'files':[{'path':path,'content':code}]},Decimal(0)).files)
  row={'path':'league/tools/a.py','content':'x=1'}
  result=parse_proposal('engineer',{'files':[row,row]},Decimal(0));self.assertEqual(len(result.files),1);self.assertTrue(result.dropped)
