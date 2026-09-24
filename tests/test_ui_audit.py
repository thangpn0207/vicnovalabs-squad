#!/usr/bin/env python3
"""
Unit tests for UI fidelity scoring engine.
"""

import unittest
from squad_engine.ui_audit import calculate_ui_fidelity


class TestUiAudit(unittest.TestCase):
    def test_identical_ui_fidelity(self):
        html = """
        <div class="flex items-center justify-between p-4 bg-zinc-900 rounded-xl">
            <h1 class="text-white text-lg font-bold">Settings</h1>
            <button class="bg-blue-600 text-white px-3 py-1 rounded">Save</button>
        </div>
        """
        res = calculate_ui_fidelity(html, html)
        self.assertTrue(res["passed"])
        self.assertGreaterEqual(res["fidelity_score"], 0.95)
        self.assertEqual(res["verdict"], "ACCEPT")

    def test_divergent_ui_rejection(self):
        mock = "<div class='flex bg-red-500'><h1>Header</h1></div>"
        comp = "<footer class='p-4 bg-blue-500'><p>Footer</p></footer>"
        res = calculate_ui_fidelity(mock, comp)
        self.assertFalse(res["passed"])
        self.assertEqual(res["verdict"], "REJECT_DEVIATION")


if __name__ == "__main__":
    unittest.main()
