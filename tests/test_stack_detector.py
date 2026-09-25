#!/usr/bin/env python3
"""
Unit tests for squad_engine.stack_detector.
Tests dynamic detection across Flutter, Web, React Native, Python, Go, Rust, Java, and iOS.
"""

import json
import tempfile
import unittest
from pathlib import Path
from squad_engine.stack_detector import (
    detect_project_stack,
    detect_stack_from_workspace,
    detect_stack_from_prompt,
    STACK_PROFILES
)


class TestStackDetector(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_detect_flutter_from_pubspec(self):
        (self.ws / "pubspec.yaml").write_text("name: my_flutter_app\n", encoding="utf-8")
        stack = detect_stack_from_workspace(str(self.ws))
        self.assertIsNotNone(stack)
        self.assertEqual(stack.stack_id, "flutter")
        self.assertEqual(stack.category, "mobile")
        self.assertEqual(stack.language, "dart")
        self.assertIn("flutter_dart-mcp-server", stack.mcp_tools)

    def test_detect_rust_from_cargo(self):
        (self.ws / "Cargo.toml").write_text("[package]\nname = 'demo'\n", encoding="utf-8")
        stack = detect_stack_from_workspace(str(self.ws))
        self.assertIsNotNone(stack)
        self.assertEqual(stack.stack_id, "rust")
        self.assertEqual(stack.test_runner, "cargo test")

    def test_detect_go_from_gomod(self):
        (self.ws / "go.mod").write_text("module example.com/demo\n", encoding="utf-8")
        stack = detect_stack_from_workspace(str(self.ws))
        self.assertIsNotNone(stack)
        self.assertEqual(stack.stack_id, "go")
        self.assertIn("go test", stack.test_runner)

    def test_detect_web_frontend_react(self):
        pkg = {
            "name": "my-react-app",
            "dependencies": {"react": "^18.0.0", "next": "^14.0.0"}
        }
        (self.ws / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        stack = detect_stack_from_workspace(str(self.ws))
        self.assertIsNotNone(stack)
        self.assertEqual(stack.stack_id, "web_frontend")
        self.assertEqual(stack.category, "web")
        self.assertIn("playwright", stack.mcp_tools)
        self.assertIn("data-testid", stack.selector_standard)

    def test_detect_react_native(self):
        pkg = {
            "name": "my-mobile-app",
            "dependencies": {"react": "^18.0.0", "react-native": "^0.72.0"}
        }
        (self.ws / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        stack = detect_stack_from_workspace(str(self.ws))
        self.assertIsNotNone(stack)
        self.assertEqual(stack.stack_id, "react_native")
        self.assertEqual(stack.category, "mobile")
        self.assertIn("testID", stack.selector_standard)

    def test_detect_node_backend(self):
        pkg = {
            "name": "my-api",
            "dependencies": {"express": "^4.18.0"}
        }
        (self.ws / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        stack = detect_stack_from_workspace(str(self.ws))
        self.assertIsNotNone(stack)
        self.assertEqual(stack.stack_id, "node_backend")
        self.assertEqual(stack.category, "backend")

    def test_detect_python(self):
        (self.ws / "pyproject.toml").write_text("[project]\nname = 'api'\n", encoding="utf-8")
        stack = detect_stack_from_workspace(str(self.ws))
        self.assertIsNotNone(stack)
        self.assertEqual(stack.stack_id, "python")
        self.assertEqual(stack.category, "backend")
        self.assertEqual(stack.test_runner, "pytest")

    def test_detect_from_prompt_fallback(self):
        stack_flutter = detect_stack_from_prompt("kiểm thử ứng dụng flutter trên android")
        self.assertEqual(stack_flutter.stack_id, "flutter")

        stack_go = detect_stack_from_prompt("viết microservice golang goroutine")
        self.assertEqual(stack_go.stack_id, "go")

        stack_fastapi = detect_stack_from_prompt("build backend with FastAPI and pytest")
        self.assertEqual(stack_fastapi.stack_id, "python")

        stack_nextjs = detect_stack_from_prompt("tạo trang landing page bằng Next.js và Tailwind")
        self.assertEqual(stack_nextjs.stack_id, "web_frontend")

    def test_unified_detect_generic_default(self):
        stack = detect_project_stack(workspace_dir=str(self.ws), prompt="do some calculations")
        self.assertEqual(stack.stack_id, "generic")


if __name__ == "__main__":
    unittest.main()
