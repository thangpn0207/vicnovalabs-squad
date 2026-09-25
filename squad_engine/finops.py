"""
squad_engine/finops.py
Real-time Token & Cost Estimator with Model Pricing Matrix, Burn Rate, and Budget Guardrails.
"""

import time
import threading
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any


# Pricing per 1,000,000 tokens (USD)
# prompt: input price, completion: output price, cached: cached prompt price
DEFAULT_PRICING = {
    # Google Gemini family
    "gemini-2.5-flash": {"prompt": 0.075, "completion": 0.30, "cached": 0.01875},
    "gemini-3.0-flash": {"prompt": 0.075, "completion": 0.30, "cached": 0.01875},
    "gemini-3.8-flash": {"prompt": 0.075, "completion": 0.30, "cached": 0.01875},
    "gemini-1.5-flash": {"prompt": 0.075, "completion": 0.30, "cached": 0.01875},
    "gemini-1.5-pro": {"prompt": 1.25, "completion": 5.00, "cached": 0.3125},
    "gemini-2.5-pro": {"prompt": 1.25, "completion": 5.00, "cached": 0.3125},
    "gemini-3.0-pro": {"prompt": 1.25, "completion": 5.00, "cached": 0.3125},
    
    # Anthropic Claude family
    "claude-3-5-sonnet": {"prompt": 3.00, "completion": 15.00, "cached": 0.30},
    "claude-3.5-sonnet": {"prompt": 3.00, "completion": 15.00, "cached": 0.30},
    "claude-3-5-haiku": {"prompt": 0.80, "completion": 4.00, "cached": 0.08},
    "claude-3.5-haiku": {"prompt": 0.80, "completion": 4.00, "cached": 0.08},
    "claude-3-opus": {"prompt": 15.00, "completion": 75.00, "cached": 1.50},
    
    # OpenAI family
    "gpt-4o": {"prompt": 2.50, "completion": 10.00, "cached": 1.25},
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60, "cached": 0.075},
    "o1": {"prompt": 15.00, "completion": 60.00, "cached": 7.50},
    "o3-mini": {"prompt": 1.10, "completion": 4.40, "cached": 0.55},
    
    # Generic / Default Fallback
    "default": {"prompt": 1.00, "completion": 3.00, "cached": 0.25},
}


@dataclass
class UsageRecord:
    timestamp: float
    agent_role: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cost_usd: float

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class FinOpsEngine:
    """Thread-safe engine for tracking LLM token burn rate, costs, and budget limits."""

    def __init__(self, alert_threshold_usd: float = 2.0, hard_limit_usd: float = 5.0):
        self._lock = threading.RLock()
        self.records: List[UsageRecord] = []
        self.pricing: Dict[str, Dict[str, float]] = dict(DEFAULT_PRICING)
        self.alert_threshold_usd = alert_threshold_usd
        self.hard_limit_usd = hard_limit_usd
        self.start_time = time.time()

    def get_pricing_for_model(self, model: str) -> Dict[str, float]:
        """Resolves pricing rates for a given model identifier (case-insensitive substring match)."""
        m_lower = model.lower()
        if m_lower in self.pricing:
            return self.pricing[m_lower]
        for key, rates in self.pricing.items():
            if key != "default" and key in m_lower:
                return rates
        return self.pricing["default"]

    def calculate_cost(
        self, model: str, prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0
    ) -> float:
        """Calculates cost in USD for the given token amounts."""
        rates = self.get_pricing_for_model(model)
        # prompt_tokens includes total input; un-cached portion pays regular prompt rate
        uncached_prompt = max(0, prompt_tokens - cached_tokens)
        cost = (
            (uncached_prompt * rates["prompt"])
            + (cached_tokens * rates.get("cached", rates["prompt"] * 0.1))
            + (completion_tokens * rates["completion"])
        ) / 1_000_000.0
        return round(cost, 6)

    def record_usage(
        self,
        agent_role: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
        timestamp: Optional[float] = None,
    ) -> UsageRecord:
        """Records a token usage event and appends to the log."""
        ts = timestamp if timestamp is not None else time.time()
        cost = self.calculate_cost(model, prompt_tokens, completion_tokens, cached_tokens)
        record = UsageRecord(
            timestamp=ts,
            agent_role=agent_role,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            cost_usd=cost,
        )
        with self._lock:
            self.records.append(record)
        return record

    @property
    def total_tokens(self) -> int:
        """Property alias for get_total_tokens()."""
        return self.get_total_tokens()

    @property
    def total_cost_usd(self) -> float:
        """Property alias for get_total_cost()."""
        return self.get_total_cost()

    def get_total_tokens(self) -> int:
        """Returns the sum of all prompt and completion tokens."""
        with self._lock:
            return sum(r.total_tokens for r in self.records)

    def get_total_cost(self) -> float:
        """Returns cumulative cost in USD."""
        with self._lock:
            return round(sum(r.cost_usd for r in self.records), 4)

    def get_burn_rate(self, window_seconds: int = 60) -> Dict[str, Any]:
        """Calculates token burn rate and cost per minute over the given rolling window."""
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            recent = [r for r in self.records if r.timestamp >= cutoff]
            if not recent:
                return {
                    "window_seconds": window_seconds,
                    "tokens_per_sec": 0.0,
                    "cost_per_min": 0.0,
                    "recent_tokens": 0,
                    "recent_cost_usd": 0.0,
                    "active_agents": [],
                }
            
            recent_tokens = sum(r.total_tokens for r in recent)
            recent_cost = sum(r.cost_usd for r in recent)
            active_agents = sorted(list({r.agent_role for r in recent}))
            
            # Duration spans min(window_seconds, actual elapsed time)
            elapsed = max(1.0, min(float(window_seconds), now - self.start_time))
            tokens_per_sec = round(recent_tokens / elapsed, 2)
            cost_per_min = round((recent_cost / elapsed) * 60.0, 4)

            return {
                "window_seconds": window_seconds,
                "tokens_per_sec": tokens_per_sec,
                "cost_per_min": cost_per_min,
                "recent_tokens": recent_tokens,
                "recent_cost_usd": round(recent_cost, 4),
                "active_agents": active_agents,
            }

    def get_breakdown_by_agent(self) -> Dict[str, Dict[str, Any]]:
        """Returns token and cost breakdown per agent role."""
        with self._lock:
            breakdown: Dict[str, Dict[str, Any]] = {}
            total_cost = sum(r.cost_usd for r in self.records) or 1.0

            for r in self.records:
                if r.agent_role not in breakdown:
                    breakdown[r.agent_role] = {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "cached_tokens": 0,
                        "total_tokens": 0,
                        "cost_usd": 0.0,
                        "call_count": 0,
                        "percentage": 0.0,
                    }
                b = breakdown[r.agent_role]
                b["prompt_tokens"] += r.prompt_tokens
                b["completion_tokens"] += r.completion_tokens
                b["cached_tokens"] += r.cached_tokens
                b["total_tokens"] += r.total_tokens
                b["cost_usd"] = round(b["cost_usd"] + r.cost_usd, 4)
                b["call_count"] += 1

            for role, data in breakdown.items():
                data["percentage"] = round((data["cost_usd"] / total_cost) * 100.0, 1)

            return breakdown

    def get_breakdown_by_model(self) -> Dict[str, Dict[str, Any]]:
        """Returns token and cost breakdown per model."""
        with self._lock:
            breakdown: Dict[str, Dict[str, Any]] = {}
            for r in self.records:
                if r.model not in breakdown:
                    breakdown[r.model] = {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "cached_tokens": 0,
                        "total_tokens": 0,
                        "cost_usd": 0.0,
                        "call_count": 0,
                    }
                b = breakdown[r.model]
                b["prompt_tokens"] += r.prompt_tokens
                b["completion_tokens"] += r.completion_tokens
                b["cached_tokens"] += r.cached_tokens
                b["total_tokens"] += r.total_tokens
                b["cost_usd"] = round(b["cost_usd"] + r.cost_usd, 4)
                b["call_count"] += 1

            return breakdown

    def set_budget_cap(self, alert_usd: float, hard_limit_usd: float) -> None:
        """Configures budget alert and hard limit thresholds."""
        with self._lock:
            self.alert_threshold_usd = alert_usd
            self.hard_limit_usd = hard_limit_usd

    def check_budget(self) -> Dict[str, Any]:
        """Evaluates current spend against budget limits."""
        total_cost = self.get_total_cost()
        if total_cost >= self.hard_limit_usd:
            return {
                "status": "HARD_LIMIT",
                "current_cost_usd": total_cost,
                "alert_threshold_usd": self.alert_threshold_usd,
                "hard_limit_usd": self.hard_limit_usd,
                "message": f"🚨 HARD LIMIT EXCEEDED: ${total_cost:.4f} >= ${self.hard_limit_usd:.2f}. Subagents should be paused!",
            }
        elif total_cost >= self.alert_threshold_usd:
            return {
                "status": "ALERT",
                "current_cost_usd": total_cost,
                "alert_threshold_usd": self.alert_threshold_usd,
                "hard_limit_usd": self.hard_limit_usd,
                "message": f"⚠️ BUDGET ALERT: Current spend ${total_cost:.4f} has exceeded warning threshold ${self.alert_threshold_usd:.2f}.",
            }
        return {
            "status": "OK",
            "current_cost_usd": total_cost,
            "alert_threshold_usd": self.alert_threshold_usd,
            "hard_limit_usd": self.hard_limit_usd,
            "message": "Spend is within normal bounds.",
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serializes current engine snapshot for JSON API responses."""
        with self._lock:
            return {
                "total_tokens": self.get_total_tokens(),
                "total_cost_usd": self.get_total_cost(),
                "burn_rate": self.get_burn_rate(window_seconds=60),
                "budget_status": self.check_budget(),
                "breakdown_by_agent": self.get_breakdown_by_agent(),
                "breakdown_by_model": self.get_breakdown_by_model(),
                "total_calls": len(self.records),
            }
