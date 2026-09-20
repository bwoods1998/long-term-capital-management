"""Wake admission without a broker, sandbox, ledger, or model provider."""
import unittest
from collections import Counter
from types import SimpleNamespace

from league.house import House, Settings
from league.tests.fakes import Clock


class WakeAdmissionTest(unittest.TestCase):
    def house(self, cadences):
        agents = [SimpleNamespace(id=f"agent-{i:04d}", wake_minutes=minutes) for i, minutes in enumerate(cadences)]
        house = House.__new__(House)
        house.clock = Clock()
        house._born_at = house.clock() - 301
        house.settings = Settings()
        house.registry = SimpleNamespace(living=lambda: list(agents))
        house._state = {"next_wake": {}}
        return house, agents

    def test_overloaded_five_minute_population_does_not_starve_younger_agents(self):
        house, agents = self.house([5] * 100)
        served = Counter()
        for tick in range(60):
            admitted = house.due()
            self.assertLessEqual(len(admitted), 16)
            self.assertEqual(len({a.id for a in admitted}), len(admitted))
            for agent in admitted:
                self.assertLessEqual(house._state["next_wake"].get(agent.id, 0), house.clock())
                served[agent.id] += 1
                house._state["next_wake"][agent.id] = house.clock() + agent.wake_minutes * 60
            if tick == 6:
                self.assertEqual(set(served), {a.id for a in agents})
            house.clock.advance(60)
        self.assertGreaterEqual(min(served.values()), 8)
        self.assertLessEqual(max(served.values()) - min(served.values()), 2)

    def test_oldest_deadline_wins_and_equal_deadlines_keep_registry_order(self):
        house, agents = self.house([5] * 4)
        now = house.clock()
        house._state["next_wake"] = {agents[0].id: now - 10, agents[1].id: now - 30,
                                    agents[2].id: now - 30, agents[3].id: now + 1}
        self.assertEqual([a.id for a in house.due()], [agents[1].id, agents[2].id, agents[0].id])

    def test_existing_mixed_cadences_remain_bounded_and_all_agents_are_served(self):
        house, agents = self.house([10] * 2 + [5] * 6 + [60] * 10 + [30] * 14 + [15] * 3)
        self.assertEqual(house.due(), agents[:16])
        served = Counter()
        for _ in range(120):
            admitted = house.due()
            self.assertLessEqual(len(admitted), 16)
            for agent in admitted:
                deadline = house._state["next_wake"].get(agent.id, 0)
                self.assertLessEqual(deadline, house.clock())
                if deadline:
                    self.assertLessEqual(house.clock() - deadline, 60)
                served[agent.id] += 1
                house._state["next_wake"][agent.id] = house.clock() + agent.wake_minutes * 60
            house.clock.advance(60)
        self.assertEqual(set(served), {a.id for a in agents})

    def test_cold_start_and_configured_batch_limits_still_apply(self):
        house, agents = self.house([5] * 35)
        house._born_at = house.clock()
        self.assertEqual(house.due(), agents[:5])
        house.settings.max_wakes_per_tick = 3
        self.assertEqual(house.due(), agents[:3])
        house.clock.advance(301)
        self.assertEqual(house.due(), agents[:3])


if __name__ == "__main__":
    unittest.main()
