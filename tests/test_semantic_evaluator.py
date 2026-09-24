#!/usr/bin/env python3
"""
Unit tests for Single-Pass Multi-Question Jev AI Semantic Evaluator.
"""

import unittest
from squad_engine.semantic_evaluator import evaluate_task_semantics, get_semantic_cache


class TestSemanticEvaluator(unittest.TestCase):
    def setUp(self):
        get_semantic_cache().clear()

    def test_single_pass_structure(self):
        res = evaluate_task_semantics("triển khai API gateway thanh toán với Stripe")
        self.assertIn("assigned_role", res)
        self.assertIn("execution_topology", res)
        self.assertIn("complexity_score", res)
        self.assertIn("hardware_requirement", res)
        self.assertIn("adversarial_risk", res)
        self.assertIn("adversarial_target_domain", res)
        self.assertIn("target_platform", res)
        self.assertEqual(res["assigned_role"], "dev")

    def test_lru_cache_hit(self):
        prompt = "kiểm thử tự động giao diện checkout với playwright"
        res1 = evaluate_task_semantics(prompt)
        self.assertIn(res1["provider"], ["offline-heuristics", "typesafe-jev"])
        
        # Second call must hit LRU cache (0ms, 0 tokens)
        res2 = evaluate_task_semantics(prompt)
        self.assertEqual(res2["provider"], "lru-cache")
        self.assertEqual(res1["assigned_role"], res2["assigned_role"])

    def test_dev_test_runner_disambiguation(self):
        res = evaluate_task_semantics("refactor test runner cho qa")
        self.assertEqual(res["assigned_role"], "dev")

    def test_hardware_distinction(self):
        # Software chat flow does not demand physical hardware
        res_soft = evaluate_task_semantics("xây dựng màn hình p2p chat tin nhắn")
        self.assertEqual(res_soft["hardware_requirement"], "emulator_or_software")

        # Explicit optical real camera scanning demands physical hardware
        res_hard = evaluate_task_semantics("quét mã optical QR bằng camera thật trên thiết bị vật lý")
        self.assertEqual(res_hard["hardware_requirement"], "physical_device_mandatory")

    def test_adversarial_risk_detection(self):
        res = evaluate_task_semantics("phân quyền RBAC và tích hợp JWT authentication")
        self.assertEqual(res["adversarial_risk"], "requires_skeptic_review")
        self.assertEqual(res["adversarial_target_domain"], "auth_security")

        res_std = evaluate_task_semantics("sửa nút bấm button trong component header")
        self.assertEqual(res_std["adversarial_risk"], "standard_execution")


if __name__ == "__main__":
    unittest.main()
