#!/usr/bin/env python3
"""
Security & Privacy Leak Test Suite.
Verifies that 0 personal paths, usernames, or secret credentials exist in the repo.
"""

import os
import re
import unittest
from pathlib import Path


class TestSecurityLeak(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent

    def test_no_hardcoded_personal_paths_or_users(self):
        """Ensure no personal home paths or developer usernames are committed."""
        forbidden_patterns = [
            (re.compile(r"/Users/[a-zA-Z0-9_-]+"), "Hardcoded /Users/ path"),
            (re.compile(r"\bphamngocthang\b", re.IGNORECASE), "Developer personal username"),
            (re.compile(r"TYPESAFE_API_KEY\s*=\s*['\"][a-zA-Z0-9_-]{10,}['\"]"), "Hardcoded TypeSafe API Key"),
        ]

        ignored_dirs = {".git", "__pycache__", ".pytest_cache", "build", "dist", ".squad_cache", ".agents"}
        ignored_files = {Path(__file__).name, ".env"} # .env is in .gitignore anyway

        violations = []

        for root, dirs, files in os.walk(self.repo_root):
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            for file in files:
                if file in ignored_files or file.endswith((".pyc", ".png", ".jpg")):
                    continue
                file_path = Path(root) / file
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    for pattern, desc in forbidden_patterns:
                        matches = pattern.findall(content)
                        if matches:
                            rel_path = file_path.relative_to(self.repo_root)
                            violations.append(f"{rel_path}: {desc} (Found: {matches[:3]})")
                except Exception as e:
                    pass

        self.assertEqual(
            len(violations), 0,
            f"Security Leak Detected! Found {len(violations)} violations:\n" + "\n".join(violations)
        )


if __name__ == "__main__":
    unittest.main()
