#!/usr/bin/env python3
"""
Context Sufficiency Guardrail (Noul) & Debug Hypothesis Ranking (Choice).
Uses TypeSafe AI System One when available, falling back gracefully to offline heuristics.
"""

import re
import sys
from typing import Dict, Any, List, Optional
from .client import get_typesafe_client


def _heuristic_context_sufficiency(prompt: str, files: List[str]) -> Dict[str, Any]:
    text = prompt.strip()
    words = len(text.split())
    
    if words < 4:
        return {
            "sufficient": False,
            "confidence": 0.9,
            "missing_context_hint": "Prompt is too terse (< 4 words). Missing target files or acceptance details.",
            "provider": "offline-heuristics"
        }
        
    missing = []
    file_refs = re.findall(r"[\w/\.-]+\.(?:py|ts|tsx|js|jsx|json|md|html|css|sql|dart)", text)
    if file_refs and not files:
        missing.append(f"Referenced files {file_refs} not found in active context or workspace.")

    sufficient = len(missing) == 0
    return {
        "sufficient": sufficient,
        "confidence": 0.85 if sufficient else 0.4,
        "missing_context_hint": "; ".join(missing) if missing else "Context is sufficient.",
        "provider": "offline-heuristics"
    }


def check_context_sufficiency(prompt: str, files: Optional[List[str]] = None) -> Dict[str, Any]:
    """Determine if context is sufficient to execute without blind guessing."""
    files = files or []
    client = get_typesafe_client()
    if not client:
        return _heuristic_context_sufficiency(prompt, files)
        
    try:
        from typesafe_sdk import Noul
        result = client.system_one(
            state={"task_prompt": prompt, "available_files": files},
            questions={
                "sufficient": Noul(
                    instructions="Is this task prompt clear, actionable, and specific enough for an engineer to act on without blind guesswork?"
                )
            }
        )
        noul_ans = result.nouls["sufficient"]
        prob = round(float(noul_ans.noul), 2)
        is_sufficient = prob >= 0.40
        return {
            "sufficient": is_sufficient,
            "confidence": prob,
            "missing_context_hint": "Context sufficient." if is_sufficient else "Insufficient context detected by Jev. Clarification needed.",
            "provider": "typesafe-jev"
        }
    except Exception as e:
        sys.stderr.write(f"[Jev Error] Falling back to heuristics: {e}\n")
        return _heuristic_context_sufficiency(prompt, files)


def _heuristic_rank_hypotheses(error_trace: str, hypotheses: List[str]) -> Dict[str, Any]:
    trace_lower = error_trace.lower()
    scored = []
    for h in hypotheses:
        h_words = set(re.findall(r"\w{3,}", h.lower()))
        matches = sum(1 for w in h_words if w in trace_lower)
        scored.append({"hypothesis": h, "match_count": matches})
    
    scored.sort(key=lambda x: x["match_count"], reverse=True)
    return {
        "ranked_hypotheses": [item["hypothesis"] for item in scored],
        "details": scored,
        "provider": "offline-heuristics"
    }


def rank_hypotheses(error_trace: str, hypotheses: List[str]) -> Dict[str, Any]:
    """Rank debug hypotheses probabilistically for squad-debug."""
    client = get_typesafe_client()
    if not client:
        return _heuristic_rank_hypotheses(error_trace, hypotheses)
        
    try:
        from typesafe_sdk import Choice
        criteria = {f"hypo_{idx}": h for idx, h in enumerate(hypotheses)}
        result = client.system_one(
            state={"error_trace": error_trace[:3000]},
            questions={
                "most_probable_cause": Choice(
                    instructions="Select the hypothesis that most likely explains the root cause of this error trace.",
                    criteria=criteria
                )
            }
        )
        probs = getattr(result.choices["most_probable_cause"], "probabilities", {})
        ranked = sorted(
            [{"id": k, "hypothesis": criteria[k], "probability": probs.get(k, 0.0)} for k in criteria],
            key=lambda x: x["probability"],
            reverse=True
        )
        return {
            "ranked_hypotheses": [item["hypothesis"] for item in ranked],
            "details": ranked,
            "provider": "typesafe-jev"
        }
    except Exception as e:
        sys.stderr.write(f"[Jev Error] Falling back to heuristics: {e}\n")
        return _heuristic_rank_hypotheses(error_trace, hypotheses)
