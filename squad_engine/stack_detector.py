#!/usr/bin/env python3
"""
Dynamic Stack Detector & Profile Resolver for VicnovaLabs Squad.
Automatically detects project tech stack from workspace markers or semantic prompts.
Provides stack-adaptive test runners, element selectors, MCP tools, and error patterns.
"""

import json
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional


@dataclass
class StackProfile:
    stack_id: str
    name: str
    category: str  # mobile, web, backend, desktop, system
    language: str
    test_runner: str
    blackbox_globs: List[str]
    selector_standard: str
    mcp_tools: List[str]
    error_signatures: List[str]
    recommended_skills: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def get_targeted_test_command(self, modified_files: Optional[List[str]] = None, workspace_dir: Optional[str] = None) -> str:
        """
        Resolves targeted test command matching modified files rather than running entire repo test suite.
        Falls back to default self.test_runner if no targeted mapping found.
        """
        if not modified_files:
            return self.test_runner

        ws = Path(workspace_dir).resolve() if workspace_dir else Path.cwd()
        mod_set = [Path(f).stem.lower().replace("test_", "") for f in modified_files if f]

        if self.stack_id == "python":
            matched_tests = []
            test_dir = ws / "tests"
            if test_dir.exists():
                for stem in mod_set:
                    candidate = test_dir / f"test_{stem}.py"
                    if candidate.exists():
                        matched_tests.append(str(candidate.relative_to(ws)))
            if matched_tests:
                return f"pytest {' '.join(matched_tests)}"
            return "pytest"

        elif self.stack_id in ["web_frontend", "node_backend"]:
            matched_specs = []
            for f in modified_files:
                if "spec." in f or "test." in f:
                    matched_specs.append(f)
            if matched_specs:
                if self.stack_id == "web_frontend" and "playwright" in self.test_runner:
                    return f"npx playwright test {' '.join(matched_specs)}"
                return f"npm test -- {' '.join(matched_specs)}"
            return self.test_runner

        elif self.stack_id == "flutter":
            matched_flutter = []
            for stem in mod_set:
                cand = ws / "test" / f"{stem}_test.dart"
                if cand.exists():
                    matched_flutter.append(str(cand.relative_to(ws)))
            if matched_flutter:
                return f"flutter test {' '.join(matched_flutter)}"
            return self.test_runner

        return self.test_runner


# Predefined stack profiles
STACK_PROFILES: Dict[str, StackProfile] = {
    "flutter": StackProfile(
        stack_id="flutter",
        name="Flutter (Dart)",
        category="mobile",
        language="dart",
        test_runner="flutter test",
        blackbox_globs=["lib/**/*.dart"],
        selector_standard="Key('id') / ValueKey('id') / Semantics(identifier: 'id')",
        mcp_tools=["flutter_dart-mcp-server", "dart-mcp-server"],
        error_signatures=[
            r"flutter:.*Exception",
            r"flutter:.*Error",
            r"Unhandled Exception:",
            r"NoSuchMethodError",
            r"Null Check operator used on a null value"
        ],
        recommended_skills=["agent-device", "stop-slop"]
    ),
    "web_frontend": StackProfile(
        stack_id="web_frontend",
        name="Web Frontend (React / Next.js / Vue / Angular / Vite)",
        category="web",
        language="typescript",
        test_runner="npx playwright test",
        blackbox_globs=["src/**/*.{ts,tsx,js,jsx}", "app/**/*.{ts,tsx,js,jsx}"],
        selector_standard="data-testid='id' / aria-label='id' / role='button'",
        mcp_tools=["playwright"],
        error_signatures=[
            r"UnhandledPromiseRejection",
            r"TypeError:",
            r"ReferenceError:",
            r"Uncaught Error:",
            r"Console error:",
            r"Warning: Each child in a list should have a unique 'key' prop"
        ],
        recommended_skills=["playwright", "accesslint-scan", "stop-slop"]
    ),
    "react_native": StackProfile(
        stack_id="react_native",
        name="React Native / Expo",
        category="mobile",
        language="typescript",
        test_runner="npm test",
        blackbox_globs=["src/**/*.{ts,tsx,js,jsx}", "app/**/*.{ts,tsx,js,jsx}"],
        selector_standard="testID='id' / accessibilityLabel='id'",
        mcp_tools=["agent-device"],
        error_signatures=[
            r"Invariant Violation:",
            r"RCTFatalException:",
            r"TypeError:",
            r"Unhandled promise rejection"
        ],
        recommended_skills=["agent-device", "stop-slop"]
    ),
    "node_backend": StackProfile(
        stack_id="node_backend",
        name="Node.js Backend (Express / NestJS / Fastify / Hono)",
        category="backend",
        language="typescript",
        test_runner="npm test",
        blackbox_globs=["src/**/*.ts", "src/**/*.js", "lib/**/*.js"],
        selector_standard="OpenAPI route / HTTP endpoint / exported service method",
        mcp_tools=[],
        error_signatures=[
            r"UnhandledPromiseRejection",
            r"TypeError:",
            r"ReferenceError:",
            r"Error: connect ECONNREFUSED",
            r"AssertionError"
        ],
        recommended_skills=["ponytail", "test-driven-development"]
    ),
    "python": StackProfile(
        stack_id="python",
        name="Python (FastAPI / Django / Flask / PyTorch)",
        category="backend",
        language="python",
        test_runner="pytest",
        blackbox_globs=["**/*.py"],
        selector_standard="REST endpoint / CLI command / Pydantic schema",
        mcp_tools=[],
        error_signatures=[
            r"Traceback \(most recent call last\):",
            r"\w+Error:",
            r"\w+Exception:",
            r"AssertionError:"
        ],
        recommended_skills=["ponytail", "test-driven-development"]
    ),
    "go": StackProfile(
        stack_id="go",
        name="Go (Golang)",
        category="backend",
        language="go",
        test_runner="go test -v ./...",
        blackbox_globs=["**/*.go"],
        selector_standard="HTTP Handler / gRPC RPC / exported function",
        mcp_tools=[],
        error_signatures=[
            r"panic:",
            r"fatal error:",
            r"goroutine \d+ \[running\]:",
            r"FAIL\t"
        ],
        recommended_skills=["ponytail", "test-driven-development"]
    ),
    "rust": StackProfile(
        stack_id="rust",
        name="Rust",
        category="system",
        language="rust",
        test_runner="cargo test",
        blackbox_globs=["src/**/*.rs"],
        selector_standard="CLI binary argument / Crate public API / HTTP route",
        mcp_tools=[],
        error_signatures=[
            r"panicked at",
            r"thread '.*' panicked",
            r"SIGSEGV",
            r"SIGABRT"
        ],
        recommended_skills=["ponytail", "test-driven-development"]
    ),
    "android_native": StackProfile(
        stack_id="android_native",
        name="Android Native (Kotlin / Java)",
        category="mobile",
        language="kotlin",
        test_runner="./gradlew test",
        blackbox_globs=["app/src/main/java/**/*", "app/src/main/kotlin/**/*"],
        selector_standard="Modifier.testTag('id') / android:id='@+id/id'",
        mcp_tools=["agent-device"],
        error_signatures=[
            r"FATAL EXCEPTION",
            r"AndroidRuntime: FATAL",
            r"NullPointerException",
            r"Crash detected:"
        ],
        recommended_skills=["agent-device", "stop-slop"]
    ),
    "ios_native": StackProfile(
        stack_id="ios_native",
        name="iOS Native (Swift / SwiftUI)",
        category="mobile",
        language="swift",
        test_runner="xcodebuild test",
        blackbox_globs=["**/*.swift"],
        selector_standard=".accessibilityIdentifier('id')",
        mcp_tools=[],
        error_signatures=[
            r"Fatal error:",
            r"EXC_BAD_ACCESS",
            r"SIGABRT",
            r"Assertion failed:"
        ],
        recommended_skills=["agent-device", "stop-slop"]
    ),
    "generic": StackProfile(
        stack_id="generic",
        name="Generic / Multi-language Application",
        category="web",
        language="generic",
        test_runner="npm test / pytest / make test",
        blackbox_globs=["src/**/*", "lib/**/*", "app/**/*"],
        selector_standard="Public API endpoint / standard UI identifier / CLI argument",
        mcp_tools=[],
        error_signatures=[
            r"(?i)error:",
            r"(?i)exception:",
            r"(?i)fatal:",
            r"(?i)panic:"
        ],
        recommended_skills=["stop-slop"]
    )
}


def detect_stack_from_workspace(workspace_dir: Optional[str] = None) -> Optional[StackProfile]:
    """Inspect workspace filesystem for marker files to determine tech stack."""
    if not workspace_dir:
        return None

    ws = Path(workspace_dir).resolve()
    if not ws.exists() or not ws.is_dir():
        return None

    # 1. Flutter marker
    if (ws / "pubspec.yaml").exists() or (ws / "pubspec.yml").exists():
        return STACK_PROFILES["flutter"]

    # 2. Rust marker
    if (ws / "Cargo.toml").exists():
        return STACK_PROFILES["rust"]

    # 3. Go marker
    if (ws / "go.mod").exists():
        return STACK_PROFILES["go"]

    # 4. Python markers
    if (ws / "pyproject.toml").exists() or (ws / "requirements.txt").exists() or (ws / "Pipfile").exists() or (ws / "setup.py").exists():
        # Check if it might be another project containing a small python script
        # If no package.json or pubspec, it's python
        if not (ws / "package.json").exists():
            return STACK_PROFILES["python"]

    # 5. iOS Native markers
    if list(ws.glob("*.xcodeproj")) or list(ws.glob("*.xcworkspace")) or (ws / "Package.swift").exists():
        if not (ws / "pubspec.yaml").exists() and not (ws / "package.json").exists():
            return STACK_PROFILES["ios_native"]

    # 6. Android Native markers
    if ((ws / "build.gradle").exists() or (ws / "build.gradle.kts").exists()) and (ws / "app" / "src" / "main" / "AndroidManifest.xml").exists():
        if not (ws / "pubspec.yaml").exists() and not (ws / "package.json").exists():
            return STACK_PROFILES["android_native"]

    # 7. Node / JS / TS ecosystem
    pkg_file = ws / "package.json"
    if pkg_file.exists():
        try:
            data = json.loads(pkg_file.read_text(encoding="utf-8"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

            # React Native
            if "react-native" in deps or "expo" in deps:
                return STACK_PROFILES["react_native"]

            # Frontend frameworks
            web_markers = ["react", "next", "vue", "nuxt", "svelte", "@angular/core", "vite"]
            if any(m in deps for m in web_markers):
                return STACK_PROFILES["web_frontend"]

            # Backend frameworks
            backend_markers = ["express", "@nestjs/core", "koa", "fastify", "hono"]
            if any(m in deps for m in backend_markers):
                return STACK_PROFILES["node_backend"]

            # Default node
            return STACK_PROFILES["web_frontend"]
        except Exception:
            return STACK_PROFILES["web_frontend"]

    return None


def detect_stack_from_prompt(prompt: str) -> Optional[StackProfile]:
    """Fallback semantic analysis of prompt to detect tech stack."""
    if not prompt:
        return None
    text = prompt.lower()

    if re.search(r"\b(flutter|\.dart|pubspec|dart\s*tooling|widget_inspector)\b", text):
        return STACK_PROFILES["flutter"]
    if re.search(r"\b(react\s*native|expo|rctfatal)\b", text):
        return STACK_PROFILES["react_native"]
    if re.search(r"\b(react|next\.?js|vue|nuxt|angular|svelte|tailwind|frontend|playwright|vite|css|html)\b", text):
        return STACK_PROFILES["web_frontend"]
    if re.search(r"\b(fastapi|django|flask|python|\.py|pytest|torch|pydantic)\b", text):
        return STACK_PROFILES["python"]
    if re.search(r"\b(golang|go\s*lang|\.go|goroutine|go\.mod)\b", text):
        return STACK_PROFILES["go"]
    if re.search(r"\b(rust|\.rs|cargo|crate)\b", text):
        return STACK_PROFILES["rust"]
    if re.search(r"\b(node\.?js|express|nestjs|fastify|typescript|\.ts|\.tsx)\b", text):
        return STACK_PROFILES["node_backend"]
    if re.search(r"\b(kotlin|android\s*native|jetpack\s*compose|gradle)\b", text):
        return STACK_PROFILES["android_native"]
    if re.search(r"\b(swift|swiftui|ios\s*native|xcode)\b", text):
        return STACK_PROFILES["ios_native"]

    return None


def detect_project_stack(
    workspace_dir: Optional[str] = None,
    prompt: str = ""
) -> StackProfile:
    """
    Unified entrypoint to resolve project stack profile.
    Priority:
    1. Workspace markers (ground truth from filesystem)
    2. Prompt semantic analysis (fallback)
    3. Generic profile (default)
    """
    # 1. Try workspace first
    stack = detect_stack_from_workspace(workspace_dir)
    if stack:
        return stack

    # 2. Try prompt
    stack = detect_stack_from_prompt(prompt)
    if stack:
        return stack

    # 3. Default generic
    return STACK_PROFILES["generic"]
