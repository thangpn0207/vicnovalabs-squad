#!/usr/bin/env python3
"""
UI Fidelity Audit Gate.
Compares mock HTML against implementation component code (Threshold >= 0.85).
"""

import re
from pathlib import Path
from typing import Dict, Any, Set


def extract_ui_features(content: str) -> Dict[str, Set[str]]:
    """Extract structural, visual, and interaction tokens from HTML or component code."""
    c = content.lower()
    
    # Extract tags / components
    tags = set(re.findall(r"<([a-z0-9_-]+)", c))
    
    # Extract classes / style tokens
    classes = set(re.findall(r'class(?:name)?=["\']([^"\']+)["\']', c))
    class_tokens = set()
    for cl in classes:
        for t in cl.split():
            class_tokens.add(t.strip())

    # Extract button & interactive labels
    labels = set(re.findall(r">([^<]{2,30})<", c))
    clean_labels = {l.strip() for l in labels if l.strip() and not l.strip().startswith("{")}

    # Extract colors (hex, rgb, named tailwind)
    colors = set(re.findall(r"#(?:[0-9a-f]{3}|[0-9a-f]{6})\b", c))
    tw_colors = set(re.findall(r"\b(?:bg|text|border)-(?:red|blue|green|gray|slate|zinc|emerald|indigo|purple|amber)-[0-9]{2,3}\b", c))
    all_colors = colors.union(tw_colors)

    # Key layout primitives
    layout_tokens = set()
    for kw in ["flex", "grid", "col", "row", "gap", "padding", "margin", "p-", "m-", "justify", "items-center"]:
        if kw in c:
            layout_tokens.add(kw)

    return {
        "tags": tags,
        "class_tokens": class_tokens,
        "labels": clean_labels,
        "colors": all_colors,
        "layout_tokens": layout_tokens
    }


def calculate_jaccard(set_a: Set[str], set_b: Set[str]) -> float:
    """Calculate Jaccard similarity index between two sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a.intersection(set_b))
    union = len(set_a.union(set_b))
    return round(intersection / union, 4)


def calculate_ui_fidelity(mock_content: str, comp_content: str) -> Dict[str, Any]:
    """Calculate weighted UI fidelity score between Mock HTML and Component."""
    mock_feat = extract_ui_features(mock_content)
    comp_feat = extract_ui_features(comp_content)

    tag_score = calculate_jaccard(mock_feat["tags"], comp_feat["tags"])
    style_score = calculate_jaccard(mock_feat["class_tokens"], comp_feat["class_tokens"])
    label_score = calculate_jaccard(mock_feat["labels"], comp_feat["labels"])
    color_score = calculate_jaccard(mock_feat["colors"], comp_feat["colors"])
    layout_score = calculate_jaccard(mock_feat["layout_tokens"], comp_feat["layout_tokens"])

    # Weighted calculation
    # Styles & Layout: 45%, Labels/Content: 25%, Tags: 15%, Colors: 15%
    fidelity_score = round(
        (style_score * 0.30) +
        (layout_score * 0.15) +
        (label_score * 0.25) +
        (tag_score * 0.15) +
        (color_score * 0.15),
        4
    )

    passed = fidelity_score >= 0.85

    return {
        "status": "success",
        "fidelity_score": fidelity_score,
        "passed": passed,
        "threshold": 0.85,
        "breakdown": {
            "style_score": style_score,
            "layout_score": layout_score,
            "label_score": label_score,
            "tag_score": tag_score,
            "color_score": color_score
        },
        "verdict": "ACCEPT" if passed else "REJECT_DEVIATION"
    }


def audit_ui_files(mock_path: str, comp_path: str) -> Dict[str, Any]:
    """Audit UI fidelity given paths to mock HTML and implementation component."""
    mp = Path(mock_path)
    cp = Path(comp_path)
    if not mp.exists():
        return {"status": "error", "error": f"Mock file not found: {mock_path}"}
    if not cp.exists():
        return {"status": "error", "error": f"Component file not found: {comp_path}"}

    mock_text = mp.read_text(encoding="utf-8", errors="ignore")
    comp_text = cp.read_text(encoding="utf-8", errors="ignore")

    res = calculate_ui_fidelity(mock_text, comp_text)
    res["mock_file"] = str(mp)
    res["component_file"] = str(cp)
    return res


def evaluate_ui_fidelity(mock_source: str, code_source: str) -> Dict[str, Any]:
    """
    Audit fidelity between the approved HTML design mock and the coded component.
    Supports either file paths or raw string contents.
    Threshold for pass: >= 0.85
    Uses TypeSafe AI System One when available, falling back gracefully to heuristic calculation.
    """
    import sys
    from .client import get_typesafe_client

    mock_content = mock_source
    if Path(mock_source).exists():
        mock_content = Path(mock_source).read_text(encoding="utf-8", errors="ignore")

    code_content = code_source
    if Path(code_source).exists():
        code_content = Path(code_source).read_text(encoding="utf-8", errors="ignore")

    client = get_typesafe_client()
    if not client:
        return calculate_ui_fidelity(mock_content, code_content)

    try:
        from typesafe_sdk import Noul, Score
        state_payload = {
            "design_mock_html": mock_content[:4000],
            "coded_component": code_content[:4000]
        }
        result = client.system_one(
            state=state_payload,
            questions={
                "layout_fidelity": Noul(
                    instructions="Does the coded component preserve the visual layout, structural hierarchy, and sections present in the design mock?"
                ),
                "fidelity_score": Score(
                    instructions="Score the overall design fidelity match between the design mock and the coded component.",
                    criteria=[
                        "Completely diverged or missing major layout structures and elements",
                        "Low fidelity with major missing sections",
                        "Moderate fidelity with basic structure present but noticeable visual differences",
                        "High fidelity matching mock closely with minor variances",
                        "Pixel-perfect or identical fidelity with all structural elements and styles accounted for"
                    ]
                )
            }
        )
        layout_noul = float(result.nouls["layout_fidelity"].noul)
        raw_score = float(result.scores["fidelity_score"].score)
        norm_score = raw_score / 4.0
        composite = round((0.5 * norm_score) + (0.5 * layout_noul), 3)
        passes_gate = composite >= 0.85

        return {
            "fidelity_score": composite,
            "passes_gate": passes_gate,
            "metrics": {
                "layout_noul": round(layout_noul, 2),
                "fidelity_level": round(raw_score, 2)
            },
            "recommendations": ["Meets fidelity gate (>= 0.85)."] if passes_gate else [
                "Fidelity below 0.85 threshold. Align layout hierarchy, missing elements, and styles with mock."
            ],
            "provider": "typesafe-jev"
        }
    except Exception as e:
        sys.stderr.write(f"[Jev Error] Falling back to heuristics: {e}\n")
        return calculate_ui_fidelity(mock_content, code_content)

