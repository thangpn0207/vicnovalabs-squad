# ⚡ Optimization, Concurrency & Security Hardening

> **Target Version**: `v2.1.0`  
> **Focus**: Token Efficiency, Financial Cost Minimization, Concurrency Resilience, and DevSecOps Integrity.

---

## 1. Token & Cost Optimization Highlights

Operating multi-agent systems without governance causes exponential token growth ($O(N^2)$). VicnovaLabs Squad v2.1.0 introduces multiple structural layers to dramatically cut token consumption:

### A. Inline-First Execution Default (`suggest` mode)
- In standard mode (`suggest`), the Main Agent handles routine features, edits, bugfixes, and tests **directly inline**.
- Renders the **Squad Suggestion Card** without spawning subagents unless explicitly requested by the user.
- **Token Savings**: Prevents duplicating system prompts, tools, and conversation history across subagents. Saves ~15,000–30,000 tokens per routine edit.

### B. Batch Test Runner Script Pattern
- Prohibits interactive, step-by-step ADB loops across chat turns (e.g. `step 1: adb shell`, `step 2: tap`, `step 3: sleep`, `step 4: logcat`).
- The subagent writes a standalone Python or Bash runner script that executes locally on the host CPU in milliseconds.
- Captures pre/post screenshots and truncates logcat output to a bounded summary (< 50 lines).
- **Token Savings**: Saves ~40,000–80,000 tokens per test journey.

### C. Crawl4AI Content Distillation
- Strips boilerplates, stylesheets, tracking scripts, and HTML markup before feeding web documentation to the agent.
- Limits token budget with `--max-tokens` (default: 1500).
- **Token Savings**: Reduces raw HTML payloads by 80–90%.

### D. Memory Compaction
- Compresses large terminal dumps, build outputs, and stack traces into high-density summaries, keeping only actionable head and tail snippets.

---

## 2. Security Hardening & Zero-Leak Standards

### A. Server-Side Request Forgery (SSRF) Blacklist
The crawler (`squad crawl`) enforces strict URL validation to prevent internal network scanning and cloud credential exfiltration:
- **Blocked Targets**:
  - Loopback addresses: `127.0.0.1`, `localhost`, `::1`.
  - Cloud Instance Metadata Service (IMDS): `169.254.169.254` (AWS/GCP/Azure metadata).
  - Private RFC1918 subnets: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`.
- **Allowed Schemes**: Only `http://` and `https://`.

### B. Restored TLS/SSL Certificate Verification
- Eliminates insecure `verify=False` / `ssl._create_unverified_context()` configurations.
- Guarantees end-to-end cryptographic integrity when fetching web documentation.

### C. Zero Committed Secrets & Dynamic Config Resolver
- Never stores secrets in source control or `.env`.
- Dynamic resolver checks local environment variables (`TYPESAFE_API_KEY`) or global IDE config paths (`~/.gemini/config/.env`).
- When no key is present, falls back gracefully to offline regex heuristics with **0 external API calls**.

---

## 3. Concurrency & Reliability Guarantees

### A. Advisory File Locking (`fcntl.flock`)
- Multiple concurrent subagents updating `PROJECT_PROGRESS.md` simultaneously can cause corruptions or lost updates.
- Squad uses advisory file locking with a 5-second timeout on all read-modify-write cycles to serialize progress tracker updates safely.

### B. Persistent Circuit Breaker
- In multi-agent loops, if a feature is repeatedly rejected by QA, agents can enter an infinite rework cycle.
- Squad persists rejection counts directly in `PROJECT_PROGRESS.md` comments (`<!-- SQUAD_DEFECT_COUNT:Feature:3 -->`).
- Survives subagent context resets and halts execution after 3 consecutive rejections to protect API quotas.

### C. Safe Worktree Isolation
- Subagents working concurrently on distinct features operate in independent `.worktrees/<slug>` directories.
- Prevents git index collisions and file lock contentions.
- If merge conflicts occur during reconciliation, the engine runs `git merge --abort` immediately to protect the main branch.
