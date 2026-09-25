#!/usr/bin/env python3
"""
Unit tests for Unified Squad Gate (SSOT), Semantic Triage,
Scoped Fan-Out Matrix, and Diff Coverage Gate.
"""

import unittest
from squad_engine.gate import squad_gate
from squad_engine.triage import triage_intent
from squad_engine.handoffs import validate_handoff_payload


class TestUnifiedGate(unittest.TestCase):
    def test_single_task_gate(self):
        res = squad_gate("chỉ sửa 1 typo trong comment của file utils.py")
        self.assertEqual(res["execution_mode"], "inline")
        self.assertEqual(res["decision"], "STOP_SINGLE_TASK")
        self.assertTrue(res["is_single_task"])
        self.assertFalse(res["auto_chain"])

    def test_scoped_fanout_gate(self):
        res = squad_gate("chia việc song song cho nhiều dev refactor toàn bộ hệ thống payment và auth")
        self.assertEqual(res["execution_mode"], "fanout")
        self.assertEqual(res["decision"], "SCOPED_FANOUT")
        self.assertIn("fanout_invocations", res)
        self.assertGreaterEqual(len(res["fanout_invocations"]), 2)
        self.assertIn("Squad Scoped Fan-Out Dispatch Card", res["dispatch_card_markdown"])

    def test_adversarial_review_gate(self):
        # In auto mode, sensitive changes dispatch adversarial review subagent
        res_auto = squad_gate("viết tài liệu đặc tả PRD và kiến trúc mới cho hệ thống auth", mode="auto")
        self.assertEqual(res_auto["execution_mode"], "subagent")
        self.assertEqual(res_auto["decision"], "DISPATCH_ADVERSARIAL_REVIEW")
        self.assertTrue(res_auto.get("adversarial_review_active"))
        self.assertEqual(res_auto.get("skeptic_agent"), "squad-debug")
        self.assertEqual(res_auto.get("schema_contract"), "critique")

        # In default (suggest) mode, sensitive changes proceed inline with soft suggestion
        res_suggest = squad_gate("viết tài liệu đặc tả PRD và kiến trúc mới cho hệ thống auth", mode="suggest")
        self.assertEqual(res_suggest["execution_mode"], "inline")
        self.assertEqual(res_suggest["decision"], "INLINE_WITH_SOFT_SUGGESTION")
        self.assertIn("💡 Notice: this change touches Auth/Security", res_suggest.get("notice", ""))

    def test_semantic_triage_dev_writing_test_runner_for_qa(self):
        """Disambiguate 'refactor test runner cho qa' -> role must be DEV (not QA)."""
        res1 = triage_intent("refactor test runner cho qa")
        self.assertEqual(res1["role"], "dev")

        res2 = triage_intent("viết unit test runner và fixture cho module auth")
        self.assertEqual(res2["role"], "dev")

        res3 = triage_intent("implement test framework cho đội kiểm thử")
        self.assertEqual(res3["role"], "dev")

        gate_res = squad_gate("refactor test runner cho qa")
        self.assertEqual(gate_res["role"], "dev")
        self.assertEqual(gate_res["target_agent"], "squad-dev")

    def test_semantic_triage_blackbox_qa(self):
        res = triage_intent("nghiệm thu tính năng login bằng playwright")
        self.assertEqual(res["role"], "qa")

        gate_res = squad_gate("chạy bộ test e2e nghiệm thu màn hình checkout")
        self.assertEqual(gate_res["role"], "qa")
        self.assertEqual(gate_res["target_agent"], "squad-qa")

    def test_coverage_gate_in_manifest_success(self):
        valid_manifest = {
            "module": "Auth",
            "modified_files": ["src/auth.py", "tests/test_auth.py"],
            "self_test_result": "PASSED",
            "verification_command": "pytest tests/test_auth.py --cov=src",
            "coverage_report": {
                "line_coverage_pct": 88.5,
                "branch_coverage_pct": 82.0,
                "tool": "pytest-cov",
                "meets_threshold": True
            }
        }
        res = validate_handoff_payload("manifest", valid_manifest)
        self.assertTrue(res["valid"])
        self.assertEqual(len(res["errors"]), 0)

    def test_coverage_gate_in_manifest_failures(self):
        # Under Dev Test Contract: coverage_report is optional and non-blocking
        missing_cov = {
            "module": "Auth",
            "modified_files": ["src/auth.py"],
            "self_test_result": "PASSED",
            "verification_command": "pytest tests/test_auth.py"
        }
        res_missing = validate_handoff_payload("manifest", missing_cov)
        self.assertTrue(res_missing["valid"])

        # Low line/branch coverage does not block handoff (treated as metadata)
        low_cov = {
            "module": "Auth",
            "modified_files": ["src/auth.py"],
            "self_test_result": "PASSED",
            "verification_command": "pytest",
            "coverage_report": {
                "line_coverage_pct": 74.0,
                "branch_coverage_pct": 72.0,
                "tool": "pytest-cov"
            }
        }
        res_low = validate_handoff_payload("manifest", low_cov)
        self.assertTrue(res_low["valid"])

        # Missing required core fields (e.g. self_test_result) MUST fail
        missing_required = {
            "module": "Auth",
            "modified_files": ["src/auth.py"]
        }
        res_err = validate_handoff_payload("manifest", missing_required)
        self.assertFalse(res_err["valid"])
        self.assertTrue(any("Missing required field" in e for e in res_err["errors"]))

    def test_mobile_qa_checklist_scoped_fanout(self):
        """Verifies multi-screen mobile QA acceptance checklist triggers Scoped Fan-Out across QA workers."""
        prompt = (
            "Kiểm tra và nghiệm thu các tính năng trên Android Emulator và iOS Simulator:\n"
            "- Age Gate & EULA điều khoản sử dụng\n"
            "- P2P Chat tin nhắn tức thời\n"
            "- Long-press menu thao tác nhanh\n"
            "- Block partner & Báo cáo vi phạm\n"
            "- Xóa danh tính và dữ liệu"
        )
        res = squad_gate(prompt, platform="mobile")
        self.assertEqual(res["execution_mode"], "fanout")
        self.assertEqual(res["decision"], "SCOPED_FANOUT")
        self.assertEqual(res["role"], "qa")
        self.assertEqual(res["target_agent"], "squad-qa")
        self.assertIn("fanout_invocations", res)
        self.assertGreaterEqual(len(res["fanout_invocations"]), 2)
        self.assertIn("Squad Scoped Fan-Out Dispatch Card", res["dispatch_card_markdown"])
        # Verify subtasks are extracted from the checklist
        subtask_titles = [st["title"] for st in res["subtasks"]]
        self.assertTrue(any("Age Gate" in t for t in subtask_titles))
        self.assertTrue(any("Chat" in t for t in subtask_titles))

    def test_squad_suggestion_default_mode(self):
        """Standard task under default 'suggest' mode runs inline with a suggestion card."""
        res = squad_gate("thêm nút chia sẻ qua mạng xã hội", mode="suggest")
        self.assertEqual(res["execution_mode"], "inline")
        self.assertEqual(res["decision"], "SUGGEST_SQUAD")
        self.assertTrue(res.get("squad_suggested"))
        self.assertEqual(res["role"], "dev")
        self.assertIn("Squad Recommendation Card", res["dispatch_card_markdown"])

    def test_explicit_squad_invocation(self):
        """Explicitly mentioning squad or agent triggers subagent execution."""
        prompts = [
            "gọi squad làm tính năng lọc sản phẩm",
            "dùng dev-agent viết service notification",
            "chạy qa-agent nghiệm thu tính năng search",
            "/squad thiết kế lại trang cá nhân",
            "triệu tập agent debug lỗi crash này"
        ]
        for p in prompts:
            res = squad_gate(p)
            self.assertEqual(res["execution_mode"], "subagent", f"Failed on prompt: {p}")
            self.assertEqual(res["decision"], "DISPATCH_EXPLICIT_SQUAD", f"Failed decision on: {p}")

    def test_option_selection_suggest_vs_squad(self):
        """Option selection runs inline by default, but subagent if squad explicitly mentioned."""
        # Standard option selection -> inline (cost-effective)
        res_inline = squad_gate("thực hiện phương án 1", mode="suggest")
        self.assertEqual(res_inline["execution_mode"], "inline")
        self.assertEqual(res_inline["decision"], "INLINE_OPTION_SELECTION")

        # Explicit squad option selection -> subagent
        res_squad = squad_gate("thực hiện phương án 1 bằng squad")
        self.assertEqual(res_squad["execution_mode"], "subagent")
        self.assertEqual(res_squad["decision"], "DISPATCH_OPTION_SELECTION")

    def test_gate_mode_overrides(self):
        """Verify behavior under different mode parameters."""
        prompt = "tạo component carousel hình ảnh"

        # Mode auto -> subagent
        res_auto = squad_gate(prompt, mode="auto")
        self.assertEqual(res_auto["execution_mode"], "subagent")

        # Mode inline -> inline
        res_inline = squad_gate(prompt, mode="inline")
        self.assertEqual(res_inline["execution_mode"], "inline")

        # Mode suggest -> inline with suggestion
        res_suggest = squad_gate(prompt, mode="suggest")
        self.assertEqual(res_suggest["execution_mode"], "inline")
        self.assertTrue(res_suggest.get("squad_suggested"))


if __name__ == "__main__":
    unittest.main()


