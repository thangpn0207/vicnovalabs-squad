#!/usr/bin/env python3
"""
Unit tests for squad intent triage, complexity scoring, and dynamic skill matrix.
"""

import unittest
from squad_engine.triage import triage_intent, calculate_complexity, dispatch_task, get_skills_for_phase


class TestTriage(unittest.TestCase):
    def test_triage_roles(self):
        self.assertEqual(triage_intent("fix bug in login crash")["role"], "debug")
        self.assertEqual(triage_intent("create ui mockup for settings")["role"], "design")
        self.assertEqual(triage_intent("write acceptance tests in playwright")["role"], "qa")
        self.assertEqual(triage_intent("implement rest api endpoint")["role"], "dev")
        self.assertEqual(triage_intent("write user stories and specification")["role"], "ba")
        self.assertEqual(triage_intent("optimize landing page seo and copy")["role"], "marketing")

    def test_complexity_scoring(self):
        res_simple = calculate_complexity("fix small typo in readme")
        self.assertLessEqual(res_simple["complexity_score"], 3)
        self.assertIn("Flash", res_simple["recommended_model_tier"])

        res_complex = calculate_complexity("refactor distributed architecture auth with multi-tenant database migration")
        self.assertGreaterEqual(res_complex["complexity_score"], 4)
        self.assertIn("Pro", res_complex["recommended_model_tier"])

    def test_phase_skills(self):
        dev_skills = get_skills_for_phase("dev", "coding", "web")
        self.assertIn("ponytail", dev_skills["skills"])
        self.assertIn("safe-refactor", dev_skills["skills"])

        qa_skills = get_skills_for_phase("qa", "acceptance", "mobile")
        self.assertIn("agent-device", qa_skills["skills"])

    def test_dispatch_generation(self):
        # Isolated suggest mode returns squad suggestion card
        res = dispatch_task("implement payment gateway API", mode="suggest")
        self.assertEqual(res["role"], "dev")
        self.assertEqual(res["target_agent"], "squad-dev")
        self.assertTrue(res.get("squad_suggested"))
        self.assertIn("Squad Recommendation Card", res["dispatch_card_markdown"])

        # Isolated smart mode dispatches subagent on complexity >= 4
        res_smart = dispatch_task("implement payment gateway API", mode="smart")
        self.assertEqual(res_smart["execution_mode"], "subagent")
        self.assertFalse(res_smart.get("squad_suggested"))

        # Explicit squad summon returns full subagent dispatch card
        res_explicit = dispatch_task("gọi dev-agent implement payment gateway API")
        self.assertEqual(res_explicit["role"], "dev")
        self.assertEqual(res_explicit["target_agent"], "squad-dev")
        self.assertEqual(res_explicit["execution_mode"], "subagent")
        self.assertIn("ZERO CODE-OFFLOADING", res_explicit["dispatch_card_markdown"])

    def test_audit_recommended_skills(self):
        from squad_engine.triage import audit_recommended_skills
        res = audit_recommended_skills()
        self.assertGreaterEqual(res["total_recommended"], 15)
        self.assertIn("installed", res)
        self.assertIn("missing", res)
    def test_adversarial_review_triggers(self):
        from squad_engine.orchestrator import requires_adversarial_review

        # Docs / Specs
        self.assertTrue(requires_adversarial_review("viết PRD cho module thanh toán"))
        self.assertTrue(requires_adversarial_review("xây dựng đặc tả yêu cầu SRS"))
        self.assertTrue(requires_adversarial_review("đặc tả user story cho onboarding"))

        # Test Strategy
        self.assertTrue(requires_adversarial_review("lập test plan cho luồng thanh toán"))
        self.assertTrue(requires_adversarial_review("xây dựng kịch bản kiểm thử cho login"))
        self.assertTrue(requires_adversarial_review("chiến lược test cho release 2.0"))

        # Architecture / Security
        self.assertTrue(requires_adversarial_review("thiết kế kiến trúc mới cho hệ thống"))
        self.assertTrue(requires_adversarial_review("database schema migration cho multi-tenant"))
        self.assertTrue(requires_adversarial_review("phân quyền RBAC và bảo mật JWT"))

    def test_adversarial_dispatch_annotation(self):
        res = dispatch_task("lập test plan và kịch bản test cho luồng checkout")
        self.assertTrue(res.get("adversarial_review_active"))
        self.assertEqual(res.get("skeptic_agent"), "squad-dev")
        self.assertIn("ADVERSARIAL REVIEW ACTIVE", res["dispatch_card_markdown"])

        res_prd = dispatch_task("viết PRD đặc tả cho hệ thống auth")
        self.assertTrue(res_prd.get("adversarial_review_active"))
        self.assertEqual(res_prd.get("skeptic_agent"), "squad-debug")
        self.assertIn("ADVERSARIAL REVIEW ACTIVE", res_prd["dispatch_card_markdown"])


if __name__ == "__main__":
    unittest.main()
