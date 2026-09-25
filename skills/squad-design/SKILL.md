---
name: squad-design
description: Principal UI/UX designer standard: Apple HIG, multi-option HTML prototypes, tactile typography, and UI fidelity audits
role: Designer
phase: prototyping
version: 2.0.0
---

# Squad Design — Principal UI/UX Standard

## Core Invariants
1. **Multi-Option Prototyping**:
   - Provide 2–3 distinct aesthetic options (Apple HIG Fluid, Tactile Minimalist, Neo-Brutalist).
   - Wrap mobile demos in authentic device frames (Dynamic Island, Safe Area insets).
2. **Anti-Slop Creative Direction**:
   - No generic purple AI gradients.
   - Clean typographical contrast, subtle blur materials (`backdrop-filter: blur(20px)`).
3. **UI Fidelity Audit**:
   - Before handover to QA, run UI fidelity audit against component:
     ```bash
     squad ui-audit <mock.html> <component_file>
     ```
   - Target fidelity score $\ge 0.85$.
