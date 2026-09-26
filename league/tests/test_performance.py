"""The read-only account return reader classifies funding, pagination and incomplete data."""
import unittest
from decimal import Decimal
from league.performance import AccountPerformance,funding_flows,stamp
START='2026-09-26T06:25:30.000Z';NOW='2026-09-28T14:00:00.000Z'
CONFIG={'start_at':START,'start_equity':'481.65'}
def activity(kind='CSD',value='100',**extra):
 return {'id':extra.pop('id',kind+value),'activity_type':kind,'date':NOW,'net_amount':value,'status':'executed',**extra}
class Broker:
 def __init__(self,rows):self.rows=rows;self.calls=[]
 def _call(self,method,path,**kwargs):
  assert method=='GET' and path=='/v2/account/activities';self.calls.append(kwargs);return self.rows

def brokers(rows=()):return {'alpaca':Broker(list(rows))}
class Performance(unittest.TestCase):
 def test_funding_is_not_profit(self):
  rows=[activity('CSD','5000'),activity('CSW','-40'),activity('JNLC','25'),activity('FILL','120'),activity('FEE','-.5'),activity('DIV','3.1'),activity('CSD','900',date='2026-09-25T00:00:00Z')]
  flows=funding_flows(brokers(rows),START)
  self.assertEqual(sum(v for _,_,v in flows),Decimal('4985'));self.assertEqual(len(flows),3)
 def test_unknown_pending_nonfinite_and_other_venues_fail_closed(self):
  for row in (activity('SURPRISE'),activity(status='pending'),activity(value='NaN')):
   with self.subTest(row=row),self.assertRaises(ValueError):funding_flows(brokers([row]),START)
  with self.assertRaises(ValueError):funding_flows({},START)
  with self.assertRaises(ValueError):funding_flows({'kalshi':Broker([])},START)
 def test_creation_time_controls_later_booked_deposit(self):
  row=activity(date='2026-09-30',created_at='2026-09-25T03:00:00Z')
  self.assertEqual(funding_flows(brokers([row]),START),[])
 def test_repeated_full_page_is_not_complete_history(self):
  with self.assertRaises(ValueError):funding_flows(brokers([activity(id=str(i)) for i in range(100)]),START)
 def test_return_requires_fresh_complete_readings(self):
  monitor=AccountPerformance(CONFIG,brokers(),lambda:stamp(NOW));monitor.attempted=stamp(NOW)
  account={'venues':[{'venue':'alpaca','as_of':NOW}]}
  self.assertIsNone(monitor.read(account,NOW)['net_flows']);monitor._refresh(NOW)
  self.assertEqual(monitor.read(account,NOW)['net_flows'],'0')
  self.assertIsNone(monitor.read({'venues':[]},NOW)['net_flows'])
  account['venues'][0]['stale']=True;self.assertIsNone(monitor.read(account,NOW)['net_flows'])
  account['venues'][0].pop('stale');self.assertIsNone(monitor.read(account,'2026-09-28T14:11:00Z')['net_flows'])
 def test_deposit_after_balance_is_not_subtracted_early(self):
  monitor=AccountPerformance(CONFIG,brokers([activity()]),lambda:stamp(NOW));monitor.attempted=stamp(NOW);monitor._refresh(NOW)
  account={'venues':[{'venue':'alpaca','as_of':START}]}
  self.assertEqual(monitor.read(account,NOW)['net_flows'],'0')
  account['venues'][0]['as_of']=NOW;self.assertEqual(monitor.read(account,NOW)['net_flows'],'100')
