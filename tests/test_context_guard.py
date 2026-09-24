#!/usr/bin/env python3
"""
Unit tests for Context Guard and Hypothesis Ranking.
"""

import unittest
from unittest.mock import patch
from squad_engine.context_guard import (
    check_context_sufficiency,
    rank_hypotheses,
    _heuristic_context_sufficiency,
    _heuristic_rank_hypotheses
)


class TestContextGuard(unittest.TestCase):
    def test_heuristic_terse_context_insufficient(self):
        res = _heuristic_context_sufficiency("fix it", [])
        self.assertFalse(res["sufficient"])
        self.assertIn("terse", res["missing_context_hint"])

    def test_heuristic_sufficient_context(self):
        res = _heuristic_context_sufficiency(
            "Implement JWT authentication filter in src/auth/jwt.py",
            ["src/auth/jwt.py"]
        )
        self.assertTrue(res["sufficient"])

    def test_heuristic_missing_file_context(self):
        res = _heuristic_context_sufficiency(
            "Refactor code in src/database/migration.py",
            []
        )
        self.assertFalse(res["sufficient"])
        self.assertIn("migration.py", res["missing_context_hint"])

    def test_heuristic_rank_hypotheses(self):
        error_trace = "NullPointerException: Cannot invoke 'String.length()' because 'token' is null at AuthService.login(AuthService.java:42)"
        hypotheses = [
            "Network timeout during database connection",
            "Missing authorization token header or unparsed payload",
            "CSS layout overflow in button styling"
        ]
        res = _heuristic_rank_hypotheses(error_trace, hypotheses)
        self.assertIn("ranked_hypotheses", res)
        self.assertEqual(len(res["ranked_hypotheses"]), 3)
        self.assertEqual(res["ranked_hypotheses"][0], hypotheses[1])

    @patch("squad_engine.context_guard.get_typesafe_client", return_value=None)
    def test_check_context_sufficiency_fallback(self, mock_client):
        res = check_context_sufficiency("write plan for migration", [])
        self.assertTrue(res["sufficient"])

    @patch("squad_engine.context_guard.get_typesafe_client", return_value=None)
    def test_rank_hypotheses_fallback(self, mock_client):
        res = rank_hypotheses("NullPointerException", ["NPE bug", "Network error"])
        self.assertEqual(res["ranked_hypotheses"][0], "NPE bug")


if __name__ == "__main__":
    unittest.main()
