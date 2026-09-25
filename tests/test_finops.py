"""
tests/test_finops.py
Unit tests for squad_engine/finops.py (Pricing Matrix, Burn Rate, Budget Guard)
"""

import time
import unittest
from squad_engine.finops import FinOpsEngine, DEFAULT_PRICING, UsageRecord


class TestFinOpsEngine(unittest.TestCase):
    def setUp(self):
        self.engine = FinOpsEngine(alert_threshold_usd=1.0, hard_limit_usd=3.0)

    def test_pricing_lookup(self):
        # Exact match
        rates_flash = self.engine.get_pricing_for_model("gemini-3.0-flash")
        self.assertEqual(rates_flash["prompt"], 0.075)

        # Substring / case-insensitive match
        rates_claude = self.engine.get_pricing_for_model("Anthropic/claude-3-5-sonnet-20241022")
        self.assertEqual(rates_claude["prompt"], 3.00)
        self.assertEqual(rates_claude["completion"], 15.00)

        # Fallback default
        rates_unknown = self.engine.get_pricing_for_model("custom-finetuned-llama")
        self.assertEqual(rates_unknown["prompt"], 1.00)

    def test_calculate_cost_gemini_flash(self):
        # 1M prompt tokens = $0.075, 1M completion = $0.30
        cost = self.engine.calculate_cost("gemini-3.0-flash", prompt_tokens=1_000_000, completion_tokens=1_000_000)
        self.assertAlmostEqual(cost, 0.375, places=5)

        # Cached tokens calculation
        # 500k cached tokens at $0.01875/M + 500k regular at $0.075/M + 0 completion
        cost_cached = self.engine.calculate_cost(
            "gemini-3.0-flash", prompt_tokens=1_000_000, completion_tokens=0, cached_tokens=500_000
        )
        expected = (500_000 * 0.075 + 500_000 * 0.01875) / 1_000_000.0
        self.assertAlmostEqual(cost_cached, expected, places=5)

    def test_record_usage_and_aggregations(self):
        self.engine.record_usage("dev", "gemini-3.0-flash", 10_000, 2_000)
        self.engine.record_usage("qa", "claude-3-5-sonnet", 20_000, 5_000)

        self.assertEqual(self.engine.get_total_tokens(), 37_000)
        self.assertGreater(self.engine.get_total_cost(), 0.0)

        agent_breakdown = self.engine.get_breakdown_by_agent()
        self.assertIn("dev", agent_breakdown)
        self.assertIn("qa", agent_breakdown)
        self.assertEqual(agent_breakdown["dev"]["total_tokens"], 12_000)
        self.assertEqual(agent_breakdown["qa"]["total_tokens"], 25_000)

        model_breakdown = self.engine.get_breakdown_by_model()
        self.assertIn("gemini-3.0-flash", model_breakdown)
        self.assertIn("claude-3-5-sonnet", model_breakdown)

    def test_burn_rate(self):
        now = time.time()
        self.engine.record_usage("dev", "gemini-3.0-flash", 1000, 500, timestamp=now)
        rate = self.engine.get_burn_rate(window_seconds=60)
        self.assertIn("tokens_per_sec", rate)
        self.assertIn("cost_per_min", rate)
        self.assertEqual(rate["recent_tokens"], 1500)
        self.assertIn("dev", rate["active_agents"])

    def test_budget_guard(self):
        # Baseline OK
        self.assertEqual(self.engine.check_budget()["status"], "OK")

        # Record huge usage to trigger ALERT
        # 400k tokens on Claude-3-5-sonnet = 400k * 15 / 1M = $6.00
        self.engine.record_usage("dev", "claude-3-5-sonnet", 10_000, 100_000)
        status = self.engine.check_budget()
        self.assertIn(status["status"], ["ALERT", "HARD_LIMIT"])

    def test_to_dict_serialization(self):
        self.engine.record_usage("ba", "gpt-4o", 5000, 1000)
        d = self.engine.to_dict()
        self.assertIn("total_tokens", d)
        self.assertIn("total_cost_usd", d)
        self.assertIn("burn_rate", d)
        self.assertIn("budget_status", d)
        self.assertIn("breakdown_by_agent", d)
        self.assertIn("breakdown_by_model", d)
        self.assertEqual(d["total_calls"], 1)


if __name__ == "__main__":
    unittest.main()
