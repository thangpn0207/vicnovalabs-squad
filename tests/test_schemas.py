#!/usr/bin/env python3
"""
Unit tests for typed handoff schemas and Anti-Deception POAI validation.
"""

import unittest
from squad_engine.handoffs import validate_handoff_payload


class TestTypedHandoffs(unittest.TestCase):
    def test_valid_manifest(self):
        payload = {
            "module": "Auth",
            "modified_files": ["src/auth.py"],
            "self_test_result": "PASSED",
            "verification_command": "pytest tests/test_auth.py",
            "coverage_report": {
                "line_coverage_pct": 87.5,
                "branch_coverage_pct": 82.0,
                "tool": "pytest-cov",
                "meets_threshold": True
            }
        }
        res = validate_handoff_payload("manifest", payload)
        self.assertTrue(res["valid"])
        self.assertEqual(len(res["errors"]), 0)

    def test_dev_test_contract_coverage_optional(self):
        # Manifest without coverage_report is valid (coverage not required)
        payload = {
            "module": "Auth",
            "modified_files": ["src/auth.py"],
            "self_test_result": "PASSED",
            "verification_command": "pytest tests/test_auth.py"
        }
        res = validate_handoff_payload("manifest", payload)
        self.assertTrue(res["valid"])

        # Low coverage percentage does not block handoff (Dev Test Contract)
        payload_low = {
            "module": "Auth",
            "modified_files": ["src/auth.py"],
            "self_test_result": "PASSED",
            "verification_command": "pytest tests/test_auth.py",
            "coverage_report": {
                "line_coverage_pct": 70.0,
                "branch_coverage_pct": 60.0
            }
        }
        res_low = validate_handoff_payload("manifest", payload_low)
        self.assertTrue(res_low["valid"])

    def test_invalid_manifest_missing_fields(self):
        payload = {"module": "Auth"}
        res = validate_handoff_payload("manifest", payload)
        self.assertFalse(res["valid"])
        self.assertIn("Missing required field: 'modified_files'", res["errors"])

    def test_valid_defect_ticket(self):
        payload = {
            "ticket_id": "DEF-001",
            "module": "Cart",
            "severity": "Major",
            "repro_steps": ["Click Add to cart", "Check balance"],
            "actual_behavior": "Item not added",
            "expected_behavior": "Item added to cart"
        }
        res = validate_handoff_payload("defect", payload)
        self.assertTrue(res["valid"])

    def test_poai_rejection_on_passive_visual_only(self):
        payload = {
            "module": "Profile",
            "target_platforms": ["android:emulator-5554"],
            "fresh_test_identifier": "user_test_12345",
            "interactive_journey": [
                {"device": "emulator-5554", "action": "agent-device click #btn"}
            ],
            "state_mutation_delta": {"pre": "empty", "post": "updated"},
            "live_evidence": "logcat output",
            "anti_deception_checks": {
                "no_passive_visual_only": False, # Violation!
                "all_target_devices_interacted": True,
                "stale_data_ruled_out": True,
                "silent_errors_ruled_out": True
            },
            "verdict": "PASS"
        }
        res = validate_handoff_payload("acceptance", payload)
        self.assertFalse(res["valid"])
        self.assertTrue(any("Anti-Deception Violation" in e for e in res["errors"]))

    def test_poai_rejection_on_identical_pre_post(self):
        payload = {
            "module": "Profile",
            "target_platforms": ["android:emulator-5554"],
            "fresh_test_identifier": "user_test_12345",
            "interactive_journey": [
                {"device": "emulator-5554", "action": "agent-device click #btn"}
            ],
            "state_mutation_delta": {"pre": "same", "post": "same"}, # Violation!
            "live_evidence": "logcat output",
            "anti_deception_checks": {
                "no_passive_visual_only": True,
                "all_target_devices_interacted": True,
                "stale_data_ruled_out": True,
                "silent_errors_ruled_out": True
            },
            "verdict": "PASS"
        }
        res = validate_handoff_payload("acceptance", payload)
        self.assertFalse(res["valid"])

    def test_poai_rejection_on_missing_silent_error_check(self):
        payload = {
            "module": "Checkout",
            "target_platforms": ["android:emulator-5554"],
            "fresh_test_identifier": "order_test_999",
            "interactive_journey": [
                {"device": "emulator-5554", "action": "agent-device click #pay_btn"}
            ],
            "state_mutation_delta": {"pre": "cart", "post": "order_confirmed"},
            "live_evidence": "logcat trace",
            "anti_deception_checks": {
                "no_passive_visual_only": True,
                "all_target_devices_interacted": True,
                "stale_data_ruled_out": True,
                "silent_errors_ruled_out": False # Violation!
            },
            "verdict": "PASS"
        }
        res = validate_handoff_payload("acceptance", payload)
        self.assertFalse(res["valid"])
        self.assertTrue(any("silent_errors_ruled_out" in e for e in res["errors"]))

    def test_valid_acceptance_with_log_audit(self):
        payload = {
            "module": "Checkout",
            "target_platforms": ["android:emulator-5554"],
            "fresh_test_identifier": "order_test_999",
            "interactive_journey": [
                {"device": "emulator-5554", "action": "agent-device click #pay_btn"}
            ],
            "state_mutation_delta": {"pre": "cart", "post": "order_confirmed"},
            "live_evidence": "logcat trace showing no exceptions",
            "anti_deception_checks": {
                "no_passive_visual_only": True,
                "all_target_devices_interacted": True,
                "stale_data_ruled_out": True,
                "silent_errors_ruled_out": True
            },
            "log_inspection_audit": {
                "logcat_checked": True,
                "terminal_checked": True,
                "zero_silent_exceptions": True
            },
            "visual_fidelity_score": 0.95,
            "verdict": "PASS"
        }
        res = validate_handoff_payload("acceptance", payload)
        self.assertTrue(res["valid"])
        self.assertEqual(len(res["errors"]), 0)
    def test_valid_critique(self):
        payload = {
            "critique_id": "CRIT-001",
            "target_artifact": "PRD-Auth",
            "target_domain": "docs",
            "skeptic_agent": "squad-debug",
            "refuted_assumptions": ["Assumed offline sync is instantaneous"],
            "blindspots_and_edge_cases": ["Race condition on dual refresh"],
            "risk_level": "Medium",
            "verdict": "APPROVED_WITH_AMENDMENTS",
            "action_items": ["Add mutex lock on token exchange"]
        }
        res = validate_handoff_payload("critique", payload)
        self.assertTrue(res["valid"])
        self.assertEqual(len(res["errors"]), 0)

    def test_invalid_critique_missing_required(self):
        payload = {
            "critique_id": "CRIT-001",
            "target_artifact": "PRD-Auth"
        }
        res = validate_handoff_payload("critique", payload)
        self.assertFalse(res["valid"])
        self.assertTrue(any("Missing required field: 'target_domain'" in e for e in res["errors"]))
        self.assertTrue(any("Missing required field: 'skeptic_agent'" in e for e in res["errors"]))
        self.assertTrue(any("Missing required field: 'verdict'" in e for e in res["errors"]))
        self.assertTrue(any("Missing required field: 'action_items'" in e for e in res["errors"]))

    def test_invalid_critique_bad_enum(self):
        payload = {
            "critique_id": "CRIT-001",
            "target_artifact": "PRD-Auth",
            "target_domain": "invalid_domain",
            "skeptic_agent": "squad-debug",
            "verdict": "MAYBE",
            "action_items": ["Fix it"]
        }
        res = validate_handoff_payload("critique", payload)
        self.assertFalse(res["valid"])
        self.assertTrue(any("not in allowed enum" in e for e in res["errors"]))


    def test_valid_acceptance_with_screenshot_evidence(self):
        payload = {
            "module": "Checkout",
            "target_platforms": ["web:playwright"],
            "fresh_test_identifier": "order_test_9999",
            "interactive_journey": ["page.click('#submit')"],
            "state_mutation_delta": {"pre": "unpaid", "post": "paid"},
            "live_evidence": "console log 200 OK",
            "anti_deception_checks": {
                "no_passive_visual_only": True,
                "all_target_devices_interacted": True,
                "stale_data_ruled_out": True,
                "silent_errors_ruled_out": True
            },
            "screenshot_evidence": ".agents/evidence/checkout_done_1727181000.png",
            "verdict": "PASS"
        }
        res = validate_handoff_payload("acceptance", payload)
        self.assertTrue(res["valid"])
        self.assertEqual(len(res["errors"]), 0)

    def test_invalid_acceptance_screenshot_not_string(self):
        payload = {
            "module": "Checkout",
            "target_platforms": ["web:playwright"],
            "fresh_test_identifier": "order_test_9999",
            "interactive_journey": ["page.click('#submit')"],
            "state_mutation_delta": {"pre": "unpaid", "post": "paid"},
            "live_evidence": "console log 200 OK",
            "anti_deception_checks": {
                "no_passive_visual_only": True,
                "all_target_devices_interacted": True,
                "stale_data_ruled_out": True,
                "silent_errors_ruled_out": True
            },
            "screenshot_evidence": 12345,  # Invalid: not string
            "verdict": "PASS"
        }
        res = validate_handoff_payload("acceptance", payload)
        self.assertFalse(res["valid"])
        self.assertTrue(any("Field 'screenshot_evidence' expected type string" in e for e in res["errors"]))

    def test_invalid_acceptance_short_live_evidence(self):
        payload = {
            "module": "Checkout",
            "target_platforms": ["web:playwright"],
            "fresh_test_identifier": "order_test_9999",
            "interactive_journey": ["page.click('#submit')"],
            "state_mutation_delta": {"pre": "unpaid", "post": "paid"},
            "live_evidence": "short",  # Too short to be real evidence
            "anti_deception_checks": {
                "no_passive_visual_only": True,
                "all_target_devices_interacted": True,
                "stale_data_ruled_out": True,
                "silent_errors_ruled_out": True
            },
            "verdict": "PASS"
        }
        res = validate_handoff_payload("acceptance", payload)
        self.assertFalse(res["valid"])
        self.assertTrue(any("Empirical Evidence Violation" in e for e in res["errors"]))

    def test_simulation_fraud_rejection(self):
        payload = {
            "module": "P2P Media",
            "target_platforms": ["android:emulator-5554"],
            "fresh_test_identifier": "test_p2p_fraud_001",
            "interactive_journey": [
                {"device": "emulator-5554", "action": "p2p wire format simulation in-memory chunking", "observed_delta": "sha256 matched in ram"}
            ],
            "state_mutation_delta": {"pre": "empty", "post": "synced"},
            "live_evidence": "console log 200 OK verified in logcat",
            "anti_deception_checks": {
                "no_passive_visual_only": True,
                "all_target_devices_interacted": True,
                "stale_data_ruled_out": True,
                "silent_errors_ruled_out": True
            },
            "verdict": "PASS"
        }
        res = validate_handoff_payload("acceptance", payload)
        self.assertFalse(res["valid"])
        self.assertTrue(any("Simulation Fraud Violation" in e for e in res["errors"]))

    def test_agent_registry_dynamic_naming(self):
        from squad_engine.agents_registry import get_agent_definition
        dev_def = get_agent_definition("squad-dev")
        self.assertEqual(dev_def["name"], "squad-dev")
        self.assertTrue(dev_def["enable_write_tools"])
        self.assertTrue(dev_def["enable_mcp_tools"])

        qa_def = get_agent_definition("squad-qa")
        self.assertEqual(qa_def["name"], "squad-qa")
        self.assertTrue(qa_def["enable_write_tools"])

        # Role aliases also resolve to squad-<role>
        qa_short = get_agent_definition("qa")
        self.assertEqual(qa_short["name"], "squad-qa")
        self.assertTrue(qa_short["enable_write_tools"])

        dev_short = get_agent_definition("dev")
        self.assertEqual(dev_short["name"], "squad-dev")
        self.assertTrue(dev_short["enable_write_tools"])

    def test_qa_screenshot_config(self):
        import tempfile
        from squad_engine.config import is_qa_screenshot_enabled, set_qa_screenshot_config
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set OFF in isolated workspace
            res_off = set_qa_screenshot_config(False, workspace=tmpdir)
            self.assertFalse(res_off["qa_screenshot_evidence"])
            self.assertFalse(is_qa_screenshot_enabled())

            # Set ON in isolated workspace
            res_on = set_qa_screenshot_config(True, workspace=tmpdir)
            self.assertTrue(res_on["qa_screenshot_evidence"])
            self.assertTrue(is_qa_screenshot_enabled())


if __name__ == "__main__":
    unittest.main()

