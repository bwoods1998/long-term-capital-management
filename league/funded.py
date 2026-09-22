"""Campaign admission at the paid Sail transport boundary, including detached response polls."""
from __future__ import annotations

from decimal import Decimal
import hashlib
import threading
import time

from ltcm.provider import PROFILES, TERMINAL, BudgetExceeded, cost_from_usage, rates, _same_model, model_of
from .campaigns import CampaignClosed
from .ledger import canonical


class FundedTransport:
    def __init__(self, transport, guard, *, clock=time.time):
        self.transport, self.guard, self.clock = transport, guard, clock
        self.lock, self.checked = threading.RLock(), float('-inf')

    def refresh(self) -> bool:
        """Account spend includes sandboxes and hosting; a top-up cannot hide it."""
        with self.lock:
            if self.clock() - self.checked < 60:
                return self.guard.ready('sail')
            self.checked = self.clock()
            try:
                summary = self.transport('GET', '/v2/usage/summary?range=period')
                # The account balance, not `period_spend`: on this plan "period" is a rolling
                # seven-day window that falls as old spend rolls off (CampaignBudget.observe_balance).
                balance = summary.get('balance')
                if (summary.get('available') is not True or summary.get('balance_unavailable')
                        or type(balance) not in (float, int)):
                    return False
                evidence = {key: summary.get(key) for key in ('range', 'effective_range', 'plan_limited', 'rolling_window',
                                                              'billing_window', 'period_spend')}
                self.guard.observe_balance('sail', Decimal(str(balance)) / 100, evidence=evidence)
            except Exception:
                return False
            return self.guard.ready('sail')

    def __call__(self, method, route, body=None, idempotency_key=None):
        commitment = profile = None
        if method == 'POST':
            if route != '/v1/responses' or not idempotency_key or not isinstance(body, dict):
                raise BudgetExceeded('campaign_unpriced_request')
            profile = next((key for key, row in PROFILES.items() if row[:2] ==
                            (body.get('model'), (body.get('metadata') or {}).get('completion_window'))), None)
            if profile is None:
                raise BudgetExceeded('campaign_unpriced_model')
            encoded = canonical(body).encode('utf-8')
            # Include the body in the durable identity. Changed-body retries are distinct bills.
            commitment = 'sail:' + hashlib.sha256((idempotency_key + ':').encode() + encoded).hexdigest()
            inp, _, out = rates(profile)
            hold = (Decimal(len(encoded) + 4096) * inp + Decimal(body['max_output_tokens']) * out) / 1000000
            self.refresh()
            try:
                fresh = self.guard.reserve(commitment, 'baseline-research', hold)
            except CampaignClosed as exc:
                raise BudgetExceeded('campaign_budget_closed', detail=str(exc)) from None
            if not fresh:
                response = self.guard.response_for(commitment)
                if not response:
                    # We cannot prove whether the earlier POST was accepted. A retry after the
                    # vendor's idempotency retention window could create a second bill.
                    raise BudgetExceeded('campaign_post_unconfirmed')
                method, route, body, idempotency_key = 'GET', '/v1/responses/' + response, None, None
        payload = self.transport(method, route, body, idempotency_key)
        if isinstance(payload, dict) and isinstance(payload.get('id'), str):
            if commitment:
                self.guard.link_response(payload['id'], commitment, profile)
            linked = self.guard.response(payload['id'])
            if linked and payload.get('status') in TERMINAL and _same_model(model_of(linked[1]), payload.get('model')):
                cost = cost_from_usage(linked[1], payload.get('usage'))
                if cost is not None:
                    self.guard.settle(linked[0], cost)
        return payload
