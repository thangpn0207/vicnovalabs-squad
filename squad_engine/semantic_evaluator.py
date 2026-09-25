#!/usr/bin/env python3
"""
Unified Semantic Evaluator for VicnovaLabs Squad.
Implements Single-Pass Multi-Question Jev AI / TypeSafe System One query
with LRU Semantic Cache (500 entries) and smart offline heuristics fallback.
"""

import re
import sys
import hashlib
import warnings
from collections import OrderedDict
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional

from .client import get_typesafe_client

warnings.filterwarnings("ignore", category=ResourceWarning, message=".*unclosed.*")


# ---------------------------------------------------------------------------
# In-Memory LRU Semantic Cache (500 entries)
# ---------------------------------------------------------------------------
class LRUSemanticCache:
    def __init__(self, capacity: int = 500):
        self.capacity = capacity
        self.cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()

    def _make_key(self, prompt: str, active_domain: Optional[str], platform: Optional[str]) -> str:
        raw = f"{prompt.strip().lower()}|{active_domain or ''}|{platform or ''}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, prompt: str, active_domain: Optional[str] = None, platform: Optional[str] = None) -> Optional[Dict[str, Any]]:
        key = self._make_key(prompt, active_domain, platform)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def put(self, prompt: str, active_domain: Optional[str], platform: Optional[str], value: Dict[str, Any]) -> None:
        key = self._make_key(prompt, active_domain, platform)
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    def clear(self) -> None:
        self.cache.clear()

    def size(self) -> int:
        return len(self.cache)


_GLOBAL_SEMANTIC_CACHE = LRUSemanticCache(capacity=500)


def get_semantic_cache() -> LRUSemanticCache:
    return _GLOBAL_SEMANTIC_CACHE


# ---------------------------------------------------------------------------
# Dataclass Definition
# ---------------------------------------------------------------------------
@dataclass
class UnifiedSemanticAssessment:
    assigned_role: str               # 'dev' | 'qa' | 'debug' | 'design' | 'ba' | 'marketing'
    execution_topology: str          # 'single_subagent' | 'scoped_fanout' | 'fast_path_inline'
    complexity_score: int            # 1 to 5
    recommended_model: str           # 'flash' | 'pro' | 'inherit'
    hardware_requirement: str       # 'physical_device_mandatory' | 'emulator_or_software'
    adversarial_risk: str            # 'requires_skeptic_review' | 'standard_execution'
    adversarial_target_domain: str   # 'auth_security' | 'architecture' | 'database_migration' | 'docs_specification' | 'none'
    target_platform: str             # 'mobile' | 'web' | 'cross_platform_agnostic'
    confidence: float
    provider: str                    # 'typesafe-jev' | 'offline-heuristics' | 'lru-cache'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Offline Fallback Heuristics
# ---------------------------------------------------------------------------
def _offline_fallback_evaluate(
    prompt: str,
    active_domain: Optional[str] = None,
    platform: Optional[str] = None,
    candidate_files: Optional[List[str]] = None,
    diff_summary: Optional[Dict[str, Any]] = None,
    workspace: Optional[str] = None
) -> Dict[str, Any]:
    text = prompt.lower()
    
    # 1. Platform detection
    if platform and platform in ["mobile", "web"]:
        target_platform = platform
    elif re.search(r"\b(mobile|ios|android|iphone|samsung|phone|flutter|react\s*native|swift|\.dart|adb|emulator|simulator)\b", text):
        target_platform = "mobile"
    else:
        target_platform = "web"

    # 2. Role detection (preserving dev test-infra disambiguation)
    scores = {"marketing": 0, "design": 0, "dev": 0, "debug": 0, "ba": 0, "qa": 0}
    if active_domain and active_domain in scores and re.search(r"\b(sửa|sửa lại|chỉnh|đổi|thêm|tiếp|tiếp tục|redo|update)\b", text):
        scores[active_domain] += 6

    is_dev_test_infra = bool(re.search(
        r"\b(refactor|viết|code|build|tạo|phát\s*triển|sửa|nâng\s*cấp|thực\s*thi|implement)\s+.*"
        r"(test\s*runner|test\s*suite|unit\s*test|bộ\s*test|hệ\s*thống\s*test|framework|mã\s*nguồn)",
        text
    )) or bool(re.search(
        r"\b(refactor|viết|code|build|triển\s*khai|tạo)\s+.*(cho\s*qa|cho\s*kiểm\s*thử|for\s*qa)\b",
        text
    )) or bool(re.search(
        r"\b(unit\s*test|integration\s*test|test\s*driver|mock|fixture|factory)\b",
        text
    ) and any(k in text for k in ["viết", "implement", "code", "build", "refactor", "thực hiện"]))

    if is_dev_test_infra:
        scores["dev"] += 8
        if re.search(r"\b(acceptance|playwright|verify|validate|e2e|nghiệm\s*thu|kiểm\s*thử\s*(?:hệ\s*thống|chức\s*năng|giao\s*diện|thực\s*tế|màn\s*hình|ứng\s*dụng)|chạy\s*test|run\s*test|acceptance\s*test|smoke\s*test|black[\s-]box|sdet|audit\s*log|check\s*bug)\b", text):
            scores["qa"] += 8
        elif re.search(r"\b(qa|kiểm\s*thử|testing)\b", text) and not any(k in text for k in ["refactor", "code", "build", "implement"]):
            scores["qa"] += 5

    if re.search(r"\b(seo|marketing|copy|copywriting|cta|landing\s*page|campaign|quảng\s*bá)\b", text):
        scores["marketing"] += 5
    if re.search(r"\b(design|mock|mockup|ui|ux|css|style|palette|layout|color|giao\s*diện|thiết\s*kế|wireframe)\b", text):
        scores["design"] += 5
    if re.search(r"\b(bug|fix|error|exception|fail|crash|debug|investigate|lỗi|hỏng|traceback|panic)\b", text):
        scores["debug"] += 5
    if re.search(r"\b(spec|specification|requirement|user\s*story|plan|scope|milestone|yêu\s*cầu|đặc\s*tả|prd|srs|adr)\b", text):
        scores["ba"] += 5
    if re.search(r"\b(implement|code|build|api|endpoint|database|migration|service|component|lập\s*trình|refactor|backend|frontend|viết\s*(?:mã|hàm|tính\s*năng))\b", text):
        scores["dev"] += 5

    assigned_role = max(scores, key=scores.get)
    if scores[assigned_role] == 0:
        assigned_role = active_domain if (active_domain and active_domain in scores) else "dev"

    # 3. Complexity calculation
    words = len(text.split())
    comp_score = 2
    if words > 100:
        comp_score += 1
    if re.search(r"\b(refactor|overhaul|architecture|migration|security|concurrency|distributed|rls|database\s+engine)\b", text):
        comp_score += 2
    if re.search(r"\b(multi-file|system|ecosystem|full-stack|pipeline)\b", text):
        comp_score += 1
    if re.search(r"\b(typo|rename|format|comment|small|single\s+line|docstring)\b", text):
        comp_score = max(1, comp_score - 2)
    comp_score = max(1, min(5, comp_score))
    rec_model = "pro" if comp_score >= 3 else "flash"

    # 4. Topology detection
    is_inline = False
    if re.search(r"\b(typo|rename|format|comment|small|1 line|single line|docstring|explain|what is|how to)\b", text):
        is_inline = True
    elif comp_score == 1 and assigned_role not in ["design", "debug", "qa"]:
        is_inline = True

    if re.search(r"\b(build|feature|refactor|migration|investigate|mockup|html|trace|failing|error|bug|test|suite|multi|redesign|giao\s*diện|thiết\s*kế|option\s*[0-9a-e]|phương\s*án\s*[0-9a-e]|nghiệm\s*thu|kiểm\s*thử|playwright|emulator|máy\s*ảo|acceptance)\b", text):
        is_inline = False

    # Check scoped fan-out
    fanout_match = bool(re.search(
        r"\b(chia\s*việc|song\s*song|nhiều\s*dev|nhiều\s*qa|multi\s*agent|fan[\s-]out|map[\s-]reduce|"
        r"toàn\s*bộ|tất\s*cả|toàn\s*app|batch\s*test|parallel)\b",
        text
    ))
    has_android = bool(re.search(r"\b(android|apk)\b", text))
    has_ios = bool(re.search(r"\b(ios|iphone|simulator)\b", text))
    multi_platform_qa = (has_android and has_ios) and any(k in text for k in ["test", "kiểm thử", "nghiệm thu", "acceptance"])

    bullet_count = 0
    for line in prompt.splitlines():
        if re.match(r"^\s*(?:[-*•]|\d+[.)])\s+(?:\[[ x\-/]\]\s*)?[A-Za-z0-9\u00C0-\u1EF9]", line.strip()):
            bullet_count += 1
    has_checklist = bullet_count >= 3 and any(k in text for k in ["test", "kiểm thử", "nghiệm thu", "triển khai", "build", "refactor"])

    if is_inline:
        execution_topology = "fast_path_inline"
    elif fanout_match or multi_platform_qa or has_checklist:
        execution_topology = "scoped_fanout"
    else:
        execution_topology = "single_subagent"

    # 5. Hardware requirement
    has_emulator_explicit = bool(re.search(r"\b(emulator|simulator|máy\s*ảo|giả\s*lập)\b", text))
    demands_physical = bool(re.search(r"\b(thiết\s*bị\s*thật|real\s*device|physical\s*device|máy\s*thật|camera\s*thật|cắm\s*máy\s*thật)\b", text))
    strict_hardware = bool(re.search(
        r"\b("
        r"optical\s*qr|quét\s*mã\s*bằng\s*camera|camera\s*thật|quét\s*qr\s*thật|"
        r"wi[\s\-_]*fi\s*direct\s*thật|nfc\s*(?:thật|tag)|bluetooth\s*le\s*(?:thật|device)|"
        r"máy\s*ảnh\s*thật"
        r")\b",
        text
    ))
    general_hw = bool(re.search(
        r"\b(p2p|peer[\s\-_]*to[\s\-_]*peer|wi[\s\-_]*fi\s*direct|qr|quét\s*mã|scan\s*qr|barcode|camera|bluetooth|ble|nfc|thiết\s*bị\s*thật|real\s*device|physical\s*device|máy\s*thật)\b",
        text
    ))

    if has_emulator_explicit and not demands_physical:
        hardware_requirement = "emulator_or_software"
    elif demands_physical or strict_hardware:
        hardware_requirement = "physical_device_mandatory"
    elif general_hw and not any(w in text for w in ["chat", "tin nhắn", "menu", "ui", "login", "setting", "cài đặt", "delete", "xóa", "eula", "age gate"]):
        hardware_requirement = "physical_device_mandatory"
    else:
        hardware_requirement = "emulator_or_software"

    # 6. Adversarial risk & domain — Tier A Path-Based Primary Signal (zero prompt regex)
    from .scope_evaluator import evaluate_scope_risk, is_sensitive_path
    scope_eval = evaluate_scope_risk(workspace_dir=workspace, touched_files=candidate_files, prompt=prompt)
    if scope_eval.requires_adversarial_review:
        adversarial_risk = "requires_skeptic_review"
        sens_files = [f for f in scope_eval.modified_files if is_sensitive_path(f)]
        hit = sens_files[0].lower() if sens_files else ""
        if any(k in hit for k in ["auth", "security", "rbac", "permission", ".env", "crypto"]):
            adversarial_target_domain = "auth_security"
        elif any(k in hit for k in ["migration", "schema"]):
            adversarial_target_domain = "database_migration"
        elif "payment" in hit:
            adversarial_target_domain = "auth_security"
        else:
            adversarial_target_domain = "architecture"
    else:
        adversarial_risk = "standard_execution"
        adversarial_target_domain = "none"

    return {
        "assigned_role": assigned_role,
        "execution_topology": execution_topology,
        "complexity_score": comp_score,
        "recommended_model": rec_model,
        "hardware_requirement": hardware_requirement,
        "adversarial_risk": adversarial_risk,
        "adversarial_target_domain": adversarial_target_domain,
        "target_platform": target_platform,
        "confidence": 0.85,
        "provider": "offline-heuristics"
    }


def classify_intent_tier_b(
    prompt: str,
    candidate_files: Optional[List[str]] = None,
    diff_summary: Optional[Dict[str, Any]] = None,
    workspace: Optional[str] = None
) -> Dict[str, Any]:
    """
    Tier B — Intent Classification via JEV (only when Tier A is inconclusive).
    Accepts candidate file list / diff summary alongside prompt text.
    Returns:
      { "is_single_task": bool, "confidence": float, "reasoning": str }
    """
    files = candidate_files or []
    stats = diff_summary or {"added": 0, "deleted": 0, "total": 0}
    text = prompt.strip()

    if files and len(files) <= 1 and stats.get("total", 0) <= 20:
        return {
            "is_single_task": True,
            "confidence": 0.95,
            "reasoning": f"single localized change in {files[0]}, {stats.get('total', 0)} lines, no new complex architecture"
        }

    client = get_typesafe_client()
    if client:
        try:
            from typesafe_sdk import Choice
            context_desc = f"Prompt: {text}\nCandidate Files: {files}\nDiff Summary: {stats}"
            question = Choice(
                instructions=(
                    "Determine whether this task is a single bounded task or a multi-part composite task. "
                    "A single bounded task implements or fixes one specific item/endpoint/screen. "
                    "A multi-part composite task spans multiple unrelated subsystems or demands broad fan-out."
                ),
                criteria={
                    "single": "Single isolated task or bounded feature/fix",
                    "composite": "Multi-module, multi-phase, or composite task"
                }
            )
            ans = client.ask(context_desc, {"is_single": question})
            is_single = ans.get("is_single") == "single"
            return {
                "is_single_task": is_single,
                "confidence": 0.85,
                "reasoning": "Jev AI evaluated prompt with candidate file context and diff stats"
            }
        except Exception:
            pass

    from .scope_evaluator import evaluate_scope_risk
    scope = evaluate_scope_risk(workspace_dir=workspace, touched_files=files, prompt=prompt)
    if scope.is_fast_path:
        return {
            "is_single_task": True,
            "confidence": 0.90,
            "reasoning": "Tier A safe fast-path verified, bounded scope and lines"
        }

    # For text-only fallback without diff, only treat as single_task if prompt has clear isolated/read-only intent
    single_pattern = r"\b(chỉ|chỉ làm|chỉ cần|duy nhất|one-off|single task|giải thích|tại sao|nghĩa là gì|explain|what is|how does|typo|rename|comment|1 dòng|single line|chỉnh 1 màu|sửa 1 nút)\b"
    is_single = bool(re.search(single_pattern, text.lower()))
    return {
        "is_single_task": is_single,
        "confidence": 0.85,
        "reasoning": "evaluated prompt scope and single-task intent indicators"
    }


# ---------------------------------------------------------------------------
# Main Semantic Evaluation Function
# ---------------------------------------------------------------------------
def evaluate_task_semantics(
    prompt: str,
    active_domain: Optional[str] = None,
    platform: Optional[str] = None,
    candidate_files: Optional[List[str]] = None,
    diff_summary: Optional[Dict[str, Any]] = None,
    workspace: Optional[str] = None,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Evaluates task semantics using Single-Pass Multi-Question Jev AI query.
    Extracts 6 core criteria in a single round-trip:
      1. assigned_role ('dev', 'qa', 'debug', 'design', 'ba', 'marketing')
      2. execution_topology ('single_subagent', 'scoped_fanout', 'fast_path_inline')
      3. complexity_tier ('low', 'medium', 'high', 'critical') -> score 1-5
      4. hardware_requirement ('physical_device_mandatory', 'emulator_or_software')
      5. adversarial_risk ('requires_skeptic_review', 'standard_execution')
      6. adversarial_target_domain ('auth_security', 'architecture', 'database_migration', 'docs_specification', 'none')
      7. target_platform ('mobile', 'web', 'cross_platform_agnostic')
    Results are cached in an LRU cache (500 entries) for 0ms, 0-token instant lookups.
    """
    if not prompt or not prompt.strip():
        fallback = _offline_fallback_evaluate(
            "", active_domain, platform, candidate_files=candidate_files, diff_summary=diff_summary, workspace=workspace
        )
        return fallback

    # Check LRU cache
    if use_cache and not candidate_files:
        cached = _GLOBAL_SEMANTIC_CACHE.get(prompt, active_domain, platform)
        if cached is not None:
            res = dict(cached)
            res["provider"] = "lru-cache"
            return res

    client = get_typesafe_client()
    if client:
        try:
            from typesafe_sdk import Choice

            questions = {
                "assigned_role": Choice(
                    instructions=(
                        "Assign this software development task to the single best squad role. "
                        "Assign to 'qa' for acceptance testing, Playwright/E2E testing, verifying UI/behavior, or quality sign-off. "
                        "Assign to 'dev' for implementing application features, writing production code, refactoring code, services, APIs, or unit test runners. "
                        "Assign to 'debug' for investigating errors, crashes, stack traces, or fixing broken code. "
                        "Assign to 'design' for UI/UX mockups, styles, and layouts. "
                        "Assign to 'ba' for PRDs, specs, and requirements. "
                        "Assign to 'marketing' for SEO, copy, and growth."
                    ),
                    criteria={
                        "dev": "Software engineering: implement features, write code, refactor code, test runners, services, APIs",
                        "qa": "Quality assurance: acceptance testing, Playwright E2E tests, verifying UI, running test suites, sign-off",
                        "debug": "System debugging: root cause investigation of crashes, stack traces, bug fixes",
                        "design": "UI/UX design: HTML mockups, layout, CSS, visual styles, wireframes",
                        "ba": "Business analysis: specifications, PRD, user stories, requirements, scope",
                        "marketing": "Growth marketing: copywriting, SEO, landing page copy, value propositions"
                    }
                ),
                "execution_topology": Choice(
                    instructions=(
                        "Determine the execution topology for this task. "
                        "CRITICAL: If the prompt describes a single feature, API endpoint, screen, or module (such as implement payment gateway API, "
                        "build user profile page, fix crash on login, create settings UI), you MUST choose single_subagent. "
                        "Choose fast_path_inline for trivial 1-line tweaks, typos, docstrings, or simple explanations. "
                        "Choose scoped_fanout ONLY if: there is an explicit request to run parallel agents or divide work across multiple workers, "
                        "or if there is a multi-feature checklist (>=3 distinct modules) or multi-platform (Android AND iOS) testing."
                    ),
                    criteria={
                        "fast_path_inline": "Trivial 1-line edit, typo fix, documentation clarification, or single small query",
                        "scoped_fanout": "Parallel execution, multi-agent fan-out, multi-module checklist, or multi-platform verification",
                        "single_subagent": "Single feature, single API endpoint, single screen, single bug fix, or standard linear development task"
                    }
                ),
                "complexity_tier": Choice(
                    instructions="Assess technical complexity and risk tier of this software development task.",
                    criteria={
                        "low": "Trivial 1-2 line tweak, typo, comment, or small localized script (Score 1-2)",
                        "medium": "Standard feature implementation, component composition, or moderate bugfix (Score 3)",
                        "high": "Cross-file refactoring, database migration, or security/auth rule change (Score 4)",
                        "critical": "High-risk architectural overhaul, distributed consensus, or complex data model redesign (Score 5)"
                    }
                ),
                "hardware_requirement": Choice(
                    instructions=(
                        "Determine if this task strictly requires physical mobile hardware (real camera, real optical QR scanning, physical NFC, Bluetooth LE hardware) "
                        "or can run on software / emulators / simulators / browser. "
                        "Pure software UI, P2P chat, menus, QR UI displays, or explicit emulator runs MUST choose 'emulator_or_software'."
                    ),
                    criteria={
                        "physical_device_mandatory": "Requires physical hardware peripherals (real camera, real optical scanner, real NFC tag, real BLE device)",
                        "emulator_or_software": "Can run on emulator, simulator, headless browser, mock environment, or pure software UI"
                    }
                ),
                "adversarial_risk": Choice(
                    instructions=(
                        "Determine if this task involves high-impact architecture, auth, security, RBAC, database migration, "
                        "or formal specifications (PRD/SRS) that require a skeptical adversarial review (Red Team / squad-debug)."
                    ),
                    criteria={
                        "requires_skeptic_review": "High-impact changes: PRD/SRS specs, new architecture, auth/RBAC security, database migration, or test strategy",
                        "standard_execution": "Standard feature development, routine bugfixes, UI styling, or standard documentation"
                    }
                ),
                "adversarial_target_domain": Choice(
                    instructions=(
                        "Identify if this task requires skeptical adversarial review (Red Team / two-way cross-agent review). "
                        "IMPORTANT: Standard feature implementation (such as implementing payment gateway API, user profile, CRUD endpoints) "
                        "is standard feature work and MUST choose none. "
                        "Formal requirements docs (PRD, SRS, user stories, specs) or test strategy/plans MUST choose docs_specification. "
                        "Dedicated security/auth/RBAC architecture MUST choose auth_security."
                    ),
                    criteria={
                        "auth_security": "Dedicated authentication, authorization, JWT, RBAC, access control security redesign",
                        "architecture": "New system architecture, breaking design changes, ADR, distributed consensus",
                        "database_migration": "Database schema migration, relational data model overhaul",
                        "docs_specification": "Formal PRD, SRS, requirements, user stories, or QA test plan / test strategy",
                        "none": "Standard feature implementation (including payment gateway APIs, endpoints, services), bugfixes, UI design"
                    }
                ),
                "target_platform": Choice(
                    instructions="Identify the target deployment platform.",
                    criteria={
                        "mobile": "Mobile applications (iOS, Android, Flutter, React Native, ADB)",
                        "web": "Web applications (HTML, CSS, JS/TS, React, Vue, browser, Playwright)",
                        "cross_platform_agnostic": "Backend services, CLI tools, documentation, or platform-neutral logic"
                    }
                )
            }

            state = {
                "prompt": prompt,
                "active_domain": active_domain or "",
                "hint_platform": platform or ""
            }

            result = client.system_one(state=state, questions=questions)

            def _extract_choice(q_name: str, default_val: str) -> str:
                ans = result.choices.get(q_name)
                if ans is None:
                    return default_val
                return ans.choice if hasattr(ans, "choice") else str(ans)

            role = _extract_choice("assigned_role", "dev")
            topology = _extract_choice("execution_topology", "single_subagent")
            comp_tier = _extract_choice("complexity_tier", "medium")
            hw_req = _extract_choice("hardware_requirement", "emulator_or_software")
            adv_risk = _extract_choice("adversarial_risk", "standard_execution")
            adv_domain = _extract_choice("adversarial_target_domain", "none")
            plat = _extract_choice("target_platform", "web" if platform != "mobile" else "mobile")

            comp_map = {"low": 2, "medium": 3, "high": 4, "critical": 5}
            comp_score = comp_map.get(comp_tier, 3)
            rec_model = "pro" if comp_score >= 3 else "flash"

            # Deterministic reconciliation guards
            t_low = prompt.lower()
            docs_match = bool(re.search(r"\b(prd|srs|đặc\s*tả|spec|specification|requirement|user\s*story|design\s*doc|test\s*plan|kịch\s*bản\s*test|kịch\s*bản\s*kiểm\s*thử|chiến\s*lược\s*test|test\s*strategy|acceptance\s*criteria)\b", t_low))
            impl_match = bool(re.search(r"\b(implement|code|build|triển\s*khai|tạo|viết\s*(?:mã|hàm|code|endpoint|api)|lập\s*trình)\b", t_low))
            crit_arch = bool(re.search(r"\b(kiến\s*trúc\s*mới|breaking\s*change|adr|tài\s*liệu\s*kiến\s*trúc|rbac|phân\s*quyền|migration)\b", t_low))
            is_running_qa = bool(re.search(r"\b(chạy\s*(?:bộ\s*)?test|run\s*test|nghiệm\s*thu|qa[\s-]agent|playwright|e2e|smoke\s*test)\b", t_low))
            is_writing_strategy = bool(re.search(r"\b(lập\s*test\s*plan|kịch\s*bản\s*test|kịch\s*bản\s*kiểm\s*thử|chiến\s*lược\s*test|test\s*strategy)\b", t_low))

            is_dev_test_infra = bool(re.search(
                r"\b(implement|refactor|viết|code|build|tạo)\s+.*(test\s*runner|test\s*framework|unit\s*test|fixture|test\s*suite)", t_low
            )) or bool(re.search(r"\b(implement|refactor|viết|code|build)\s+.*(cho\s*qa|cho\s*(?:đội\s*)?kiểm\s*thử|for\s*qa)\b", t_low))

            if is_running_qa and not is_writing_strategy:
                adv_risk = "standard_execution"
                adv_domain = "none"
                role = "qa"
            elif is_dev_test_infra:
                adv_risk = "standard_execution"
                adv_domain = "none"
                role = "dev"
            elif docs_match:
                adv_risk = "requires_skeptic_review"
                if adv_domain == "none":
                    adv_domain = "docs_specification"
            elif impl_match and not crit_arch:
                adv_risk = "standard_execution"
                adv_domain = "none"
                if role in ["debug", "ba"]:
                    role = "dev"
            elif adv_domain != "none":
                adv_risk = "requires_skeptic_review"

            assessment = {
                "assigned_role": role,
                "execution_topology": topology,
                "complexity_score": comp_score,
                "recommended_model": rec_model,
                "hardware_requirement": hw_req,
                "adversarial_risk": adv_risk,
                "adversarial_target_domain": adv_domain,
                "target_platform": plat,
                "confidence": 0.95,
                "provider": "typesafe-jev"
            }

            if use_cache:
                _GLOBAL_SEMANTIC_CACHE.put(prompt, active_domain, platform, assessment)

            return assessment

        except Exception as e:
            sys.stderr.write(f"[Jev Error] System One multi-question failed: {e}. Falling back to heuristics.\n")

    fallback = _offline_fallback_evaluate(prompt, active_domain, platform)
    if use_cache:
        _GLOBAL_SEMANTIC_CACHE.put(prompt, active_domain, platform, fallback)
    return fallback
