#!/usr/bin/env python3
"""
Unit tests for ADB device inspection and hardware trigger detection.
"""

import unittest
from squad_engine.devices import is_hardware_constrained, is_device_resume_prompt


class TestDevices(unittest.TestCase):
    def test_hardware_constraint_detection(self):
        self.assertTrue(is_hardware_constrained("Test QR code optical scanner with real camera"))
        self.assertTrue(is_hardware_constrained("Cần kết nối Wi-Fi Direct p2p giữa 2 máy"))
        self.assertFalse(is_hardware_constrained("Chỉ chỉnh sửa file README.md"))

    def test_resume_prompt_detection(self):
        self.assertTrue(is_device_resume_prompt("tiếp tục"))
        self.assertTrue(is_device_resume_prompt("đã kết nối"))
        self.assertTrue(is_device_resume_prompt("resume"))
        self.assertFalse(is_device_resume_prompt("hãy phân tích bug này"))


if __name__ == "__main__":
    unittest.main()
