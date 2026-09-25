# 🚀 VicnovaLabs Squad v2.4.0

> **Governed Multi-Agent Execution Platform, Evidence-Driven QA & Virtual Squad Office**  
> *Antigravity, Claude Code, Cursor, Codex / OpenAI Universal LLMs*

[![Version](https://img.shields.io/badge/version-2.4.0-blue.svg)](https://github.com/VicnovaLabs/VicnovaLabs-squad)
[![Tests](https://img.shields.io/badge/tests-233%20passed-brightgreen.svg)](tests/)
[![Python](https://img.shields.io/badge/python-3.10+-informational.svg)](setup.py)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**VicnovaLabs Squad v2.4.0** là nền tảng điều phối đa Agent tự trị có cơ chế quản trị nghiêm ngặt (**Governed Multi-Agent Execution Platform**) được thiết kế chuyên biệt cho các AI IDE hiện đại (**Google Antigravity, Claude Code, Cursor, Codex / OpenAI Universal LLMs**).

Hệ thống điều phối **6 chuyên gia kỹ thuật phần mềm tự trị** tuân theo các nguyên tắc kiến trúc bất biến: **Zero Code-Offloading**, **Proof-of-Active-Interaction (POAI)**, **Anti-Static Deception**, **Requirement Traceability (`REQ-XXX`)**, **3-Tier Execution Architecture**, và **Advisory Concurrency Locks**.

---

## 📚 Documentation Index
- 📖 [Complete CLI Reference Manual](docs/CLI_REFERENCE.md)
- 🛡️ [Evidence-Driven QA & Anti-Static Deception Guide](docs/EDQA_AND_ANTI_DECEPTION.md)
- 🏛️ [Architecture, Governance & The 4 Pillars](docs/ARCHITECTURE_AND_PILLARS.md)
- ⚡ [Optimization, Security Hardening & Concurrency](docs/SECURITY_AND_OPTIMIZATION.md)

---

## 🏛️ System Architecture

```
                             ┌────────────────────────┐
                             │    MAIN ORCHESTRATOR   │
                             │ (Inline-First Default) │
                             └───────────┬────────────┘
                                         │
        ┌───────────────┬────────────────┼───────────────┬───────────────┐
        ▼               ▼                ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   BA AGENT   │ │ DESIGN AGENT │ │  DEV AGENT   │ │  DEBUG AGENT │ │   QA AGENT   │
│ Specs & ADRs │ │ Apple HIG/UI │ │Clean Code/TDD│ │Root Cause Fix│ │ SDET & POAI  │
└──────────────┘ └──────────────┘ └──────┬───────┘ └──────────────┘ └──────▲───────┘
                                         │                                 │
                                         └─── HandoffManifest (Self-Test) ─┘
                                         ┌─── DefectTicket (Loopback) ─────┐
                                         │                                 │
```

### The 6 Specialized Squad Roles
1. **`squad-ba` (Business Analyst & Product Architect)**: Thu thập yêu cầu, User Stories, tiêu chí nghiệm thu Gherkin (*Given-When-Then*), cấp mã truy vết yêu cầu chuẩn hóa **`REQ-XXX`**, và lập Hồ sơ Quyết định Kiến trúc (*Architecture Decision Records - ADR*).
2. **`squad-design` (Principal UI/UX Designer)**: Tuân thủ Apple HIG, vật lý chuyển động (Fluid Motion Physics), thiết kế xúc giác, xây dựng bản mẫu HTML tương tác 3 phương án để người dùng phê duyệt trước khi code, kiểm định độ tương đồng giao diện qua `ui-audit` ($\ge 0.85$).
3. **`squad-dev` (Staff Full-Stack Software Engineer)**: Zero-offloading (tự ghi trực tiếp vào filesystem, tự chạy self-test), Clean Code, Composition Patterns, TDD, Supabase, và tạo `HandoffManifest` gắn chặt với `REQ-XXX` (Diff Coverage Gate: Dòng $\ge 85\%$, Nhánh $\ge 80\%$).
4. **`squad-debug` (Systems Debugger & SRE)**: Điều tra nguyên nhân gốc rễ (Root Cause Analysis), xếp hạng giả thuyết dựa trên chứng cứ thực nghiệm (`rank-hypotheses`), và áp dụng bản vá phẫu thuật tối giản (`surgical-patch`).
5. **`squad-qa` (Lead Defect Hunter & SDET)**: Tư duy săn lỗi triệt để (không áp lực phải pass), Proof-of-Active-Interaction (POAI), 3 Chiều Tra Tấn Ứng Dụng (Boundary/Fuzzing, State Inversion, Network Latency/Offline), quét bẫy ảnh tĩnh (Anti-Static Deception), ADB hardware preflight, và xuất `SignoffReceipt` (thăng cấp `DONE`) hoặc `DefectTicket` (từ chối).
6. **`squad-marketing` (Senior Growth Marketer & CRO)**: Thiết kế định vị giá trị, tối ưu tỷ lệ chuyển đổi (CRO), viết copy landing page, cấu trúc SEO, và triệt tiêu ngôn từ sáo rỗng của AI (`avoid-ai-writing`, `stop-slop`).

---

## 🌟 Các Tính Năng Cốt Lõi (Core Features v2.4.0)

### 1. Evidence-Driven QA (EDQA) & Anti-Static Deception
- **Cổng Chống Ảo Giác Ảnh Tĩnh (Anti-Static Deception Gate)**: Một màn hình hoặc ảnh chụp "trông có vẻ đúng" bị từ chối thẳng thừng làm bằng chứng tính năng hoạt động. Bằng chứng bắt buộc phải là đột biến trạng thái thực tế ($Pre \neq Post$).
- **3 Thuật Toán So Sánh Ảnh (3-Strategy Mutation Detection)**: Đối chiếu ảnh chụp màn hình trước và sau hành động qua **Perceptual Difference** (`image_diff`), **Độ chênh lệch dung lượng file** (`size_delta`), và **Mã băm mã hóa SHA-256** (`hash`). Bác bỏ mọi bộ chứng cứ dùng ảnh tĩnh trùng lặp.
- **3 Chiều Kiểm Thử Tra Tấn (Torture Test Dimensions)**:
  - *Boundary & Fuzzing*: Tiêm SQLi, emoji, chuỗi tràn bộ nhớ, và null bytes tự động qua `tortureFuzzInput`.
  - *State Inversion*: Đảo ngược trạng thái liên tục (check $\rightarrow$ uncheck, open $\rightarrow$ cancel) để phát hiện race condition.
  - *Network Latency & Interruption*: Kiểm tra xử lý offline, gián đoạn kết nối mạng và trạng thái loading.
- **Cổng Thẩm Định Phần Cứng ADB (Hardware Preflight Gate)**: Kiểm tra trạng thái máy ảo/thiết bị thật, bộ nhớ trống trên `/data` ($> 500$MB), kích thước hiển thị (`wm size`) và gói ứng dụng trước khi chạy test.
- **Cổng Chống Báo PASS Ảo (Anti-False-PASS Gate)**: Xác minh mã thoát test runner script $= 0$, số lượng assertion pass $> 0$, số assertion fail $= 0$, và quét đa dòng regex tìm ngoại lệ chưa bắt (Unhandled Exception, Crash, ANR, Traceback).

### 2. Nguyên Tắc Quản Trị & Truy Vết Toàn Trình (Governance & Traceability)
- **Truy Vết Yêu Cầu Toàn Trình (`REQ-XXX`)**: Yêu cầu kỹ thuật từ `squad-ba` mang mã `REQ-XXX` được truyền bắt buộc vào `HandoffManifest.requirement_ids` của Dev, và `squad-qa` phải kiểm tra từng mã này trước khi ghi nhận vào `SignoffReceipt.requirement_ids`.
- **Phân Định Trách Nhiệm Tuyệt Đối (Strict Scope Control)**: Dev và Design không bao giờ tự phong `[x] DONE` (chỉ đánh dấu `[-] READY_FOR_QA`). QA không bao giờ sửa source code.
- **Zero Code-Offloading**: Subagent có quyền ghi file bắt buộc phải tự ghi file vào ổ đĩa và tự chạy test. Nghiêm cấm in code thô ra màn hình chat để nhờ áp dụng.
- **Advisory Concurrency Lock (`fcntl.flock`)**: Tuần tự hóa truy cập đọc/ghi file `PROJECT_PROGRESS.md` giữa các subagent chạy song song với timeout 5 giây, triệt tiêu race condition.
- **Persistent Circuit Breaker**: Theo dõi số lần reject liên tiếp trong comment metadata của `PROJECT_PROGRESS.md`, tự động ngắt sau 3 lần reject liên tục để bảo vệ quota token.

### 3. Bốn Trụ Cột Kiến Trúc (The 4 Pillars)
- **Pillar 1: OpenClaw 5-Tier Persistent Memory & Context Compactor**:
  Phân cấp tri thức dự án vào 5 tầng tin cậy: `[VERIFIED]`, `[DECISION]`, `[INFERRED]`, `[HISTORICAL]`, và `[SUPERSEDED]`. Hỗ trợ câu lệnh `squad memory supersede <topic>` để hủy các quyết định kiến trúc cũ, cùng bộ nén log terminal dài thành bản tóm tắt $\le 50$ dòng.
- **Pillar 2: Crawl4AI Clean Micro-Crawler (SSRF-Protected)**:
  Trích xuất tài liệu web sạch dưới định dạng Markdown, loại bỏ toàn bộ mã nhúng scripts, styles, thanh điều hướng và quảng cáo (giảm $80-90\%$ token). Tích hợp sẵn bộ lọc chặn SSRF (chặn dải IP nội bộ và metadata cloud `169.254.169.254`).
- **Pillar 3: Stagehand-Inspired Self-Healing UI Primitives**:
  Bộ công cụ tự hồi phục (`smartClick`, `smartFill`, `tortureFuzzInput`) trong `test_primitives.js` tự động chuyển đổi thông minh qua nhiều tầng selector (`data-testid` $\rightarrow$ `role` $\rightarrow$ `aria-label` $\rightarrow$ text $\rightarrow$ CSS) chống giòn gãy automation.
- **Pillar 4: Superpowers Safe Git Worktrees**:
  Cô lập môi trường chạy song song của subagent vào thư mục độc lập `.worktrees/<slug>` trên nhánh `squad/<slug>`. Kiểm tra dirty working tree, áp dụng chính sách test-before-merge (`--test-command`) và rollback tự động nếu có xung đột (`git merge --abort`).

### 4. Kiến Trúc Thực Thi 3 Tầng (3-Tier Execution Architecture) & FinOps
- **Tier 0: Passive Scanner (Zero-LLM Cost)**:
  Quét diff mã nguồn tức thời bằng AST và Regex (chạy bằng Python cục bộ, chi phí **0 token**). Phân loại 3 mức độ rủi ro:
  - `fast_path`: Thay đổi nhỏ, CSS/UI không ảnh hưởng luồng nghiệp vụ.
  - `notify_only`: Thay đổi rủi ro thấp (bump patch lockfile, sửa script CI đơn lẻ).
  - `escalate_suggested`: Thay đổi có bán kính ảnh hưởng lớn (Auth/Bảo mật, Database, CI/CD, Dependency cốt lõi, thay đổi Public API Surface qua AST signature differ).
- **Tier 1: Manual On-Demand Surface**:
  Thực thi lẻ từng vai trò (`/squad <role>`, ví dụ `/squad dev`) mà không tự động xâu chuỗi downstream qua QA hay signoff (`auto_chain=False`). Chỉ kích hoạt toàn bộ pipeline khi chỉ định rõ ràng `/squad full`.
- **Tier 2: Auto-Escalation Gate**:
  Đưa ra thông báo gợi ý 1 dòng không chặn (Soft Notice) ở chế độ mặc định `suggest`. Chỉ kích hoạt full pipeline đa Agent khi người dùng bấm xác nhận hoặc ở mode `auto`.
- **Mẫu Runner Kịch Bản Gộp (Batch Test Runner Script Pattern)**:
  Nghiêm cấm chạy vòng lặp tương tác ADB gõ từng lệnh qua hàng chục turn chat ($O(N^2)$ token). Toàn bộ kịch bản được tổng hợp thành 1 script Python/Bash duy nhất, chạy 1 phát trên CPU máy chủ trong vài mili-giây (tiết kiệm **40.000 – 80.000 tokens** mỗi lần kiểm thử).
- **Stealth Mode & CLI Payload Compaction**:
  Rút gọn dữ liệu nạp `get-agent-def` từ 10.6KB xuống ~300B khi chạy inline, giữ dung lượng prompt luôn tinh gọn.

### 5. Văn Phòng Ảo & Đài Điều Khiển Thời Gian Thực (`squad office`)
- **Sàn Văn Phòng Pixel 2D (Interactive 2D Pixel Office Floor)**: Trực quan hóa vị trí và trạng thái của 6 Agent (Đang code, Đang test, Bị từ chối, Cạn kiệt năng lượng `(x_x)`, Bị kẹt vòng lặp `(@_@)`).
- **Giám Sát Chi Phí FinOps Thời Gian Thực**: Theo dõi tốc độ đốt token, chi phí ước tính ($/phút) dựa trên ma trận giá các dòng mô hình LLM, cùng bộ ngắt ngân sách tự động.
- **Đài Chỉ Huy 2 Chiều (Two-Way Mission Control Deck)**: Hỗ trợ Tạm dừng (Pause), Tiếp tục (Resume), Hủy tác vụ (Kill), hoặc Phê duyệt Gate từ xa ngay trên giao diện web.
- **Luồng Dữ Liệu Tự Động (SSE Streaming Telemetry)**: Theo dõi trực tiếp file log `transcript.jsonl` và trạng thái tiến độ dự án thời gian thực.

---

## ⚡ Những Điểm Tối Ưu Vượt Trội (Optimization Highlights)

| Hạng mục | Cơ chế tối ưu | Lợi ích đạt được |
|---|---|---|
| **Token & Chi phí** | Inline-First Default (`suggest` mode) | Tiết kiệm **15.000–30.000 tokens** cho mỗi tác vụ thường. |
| **Kiểm thử Mobile/Web** | Batch Test Runner Script Pattern | Chạy 1 shot trên host CPU, tiết kiệm **40.000–80.000 tokens** so với vòng lặp ADB interactive chat. |
| **Thu thập tài liệu** | Crawl4AI Content Distillation | Giảm **80–90%** dung lượng token trang web bằng cách lọc noise, ads, scripts. |
| **An toàn mạng** | SSRF Blacklist & TLS Verification | Chặn triệt để truy cập trái phép IP private và metadata cloud (`169.254.169.254`). |
| **Độ tin cậy** | Advisory File Lock & Persistent Circuit Breaker | Triệt tiêu race condition đọc/ghi file tiến độ và ngắt mạch sau 3 lần lặp lỗi. |
| **Tự chữa lành** | `squad fix-agent-setting` | Tự động phát hiện và sửa các bẫy phân quyền, loại bỏ cấu hình tĩnh nhiễm độc toàn cục. |

---

## 🚀 Hướng Dẫn Sử Dụng Đầy Đủ (Usage Guide)

Toàn bộ hệ thống được điều khiển thông qua lệnh `squad` (hoặc `python3 jev_triage.py`):

### 1. Phân Phối Tác Vụ & Quản Lý Chế Độ
```bash
# Phân tích ý định và điều hướng thông minh (Gateway duy nhất)
squad dispatch "thêm tính năng xác thực OAuth2 bằng Google"
squad dispatch "refactor payment gateway architecture" --mode smart
squad dispatch "nghiệm thu luồng đặt hàng trên Android" --platform mobile

# Kiểm tra hoặc thay đổi chế độ hoạt động (suggest, smart, auto, inline)
squad mode                         # Xem chế độ hiện tại
squad mode smart                   # Áp dụng cho toàn bộ dự án (.squad_mode & .env)
squad mode auto --scope session    # Chỉ áp dụng riêng cho phiên chat hiện tại
```

### 2. Kiểm Thử Chứng Cứ & Nghiệm Thu (EDQA)
```bash
# 1. Kiểm tra phần cứng và dung lượng máy ảo Android (>500MB trống)
squad preflight emulator-5554 --package com.example.shop --min-storage 500

# 2. Sinh và chạy kịch bản kiểm thử độc lập (Batch Test Runner)
squad test-run --stack web_frontend --url http://localhost:5173 --evidence-dir /tmp/ev_web
squad test-run --stack flutter --device emulator-5554 --package com.example.app --evidence-dir /tmp/ev_app

# 3. Thẩm định bộ chứng cứ qua Tòa Trọng Tài Chống Gian Lận (Anti-Fraud Oracle)
squad validate-evidence /tmp/ev_app --stack flutter

# 4. Xác thực tính hợp lệ của biên bản chuyển giao (Typed Handoff)
squad validate-handoff manifest ./handoff.json --strict-traceability
squad validate-handoff acceptance ./receipt.json --strict-evidence --exit-code 0 --evidence-dir /tmp/ev_app
```

### 3. Vận Hành 4 Trụ Cột Kiến Trúc
```bash
# [Trụ cột 1] Quản lý bộ nhớ 5 tầng & Nén log
squad memory status                                            # Xem dung lượng token các tầng
squad memory record "Wrap Playwright in try...finally" --topic BrowserAutomation --tier verified
squad memory supersede "StateManagement" --reason "Migrated to Zustand in ADR-005"
squad memory compact "<giant_terminal_log>"                    # Nén log terminal dài

# [Trụ cột 2] Quét tài liệu sạch (Crawl4AI)
squad crawl "https://pub.dev/packages/supabase_flutter" --max-tokens 1200 -o docs/supabase.md

# [Trụ cột 3] Stagehand UI Primitives
# Tích hợp sẵn trong squad_engine/test_primitives.js (smartClick, smartFill, tortureFuzzInput)

# [Trụ cột 4] Quản lý nhánh song song (Git Worktrees)
squad worktree create feat-payment                             # Tạo vùng độc lập .worktrees/feat-payment
squad worktree list                                            # Liệt kê các worktree đang chạy
squad worktree merge feat-payment --test-command "pytest"      # Tự chạy test trước khi merge
```

### 4. Quản Lý Tiến Độ, Kế Hoạch & Điều Phối
```bash
# Xem ma trận tiến độ dự án
squad progress status

# Khởi tạo và quản lý kế hoạch phân rã
squad task-plan init "Hệ thống Thanh toán" "Xác thực Giỏ hàng" "Cổng Stripe" "Email Hóa đơn"
squad task-plan status
squad task-plan update --plan .agents/plans/PLAN_01.md --subtask ST-01 --status READY_FOR_QA --note "Verified"
squad task-plan reconcile                                      # Đồng bộ trạng thái vào PROJECT_PROGRESS.md
squad task-plan prune --keep 5                                 # Dọn dẹp kế hoạch cũ

# Chạy pipeline tự động khép kín
squad orchestrate --manifest handoff.json
```

### 5. Văn Phòng Ảo & Chẩn Đoán Hệ Thống
```bash
# Khởi chạy Văn phòng ảo & Dashboard Telemetry thời gian thực
squad office                                                   # Mở giao diện tại http://localhost:7777
squad office status                                            # Kiểm tra trạng thái server
squad office stop                                              # Dừng server

# Tự chẩn đoán và tự sửa lỗi cấu hình môi trường
squad status                                                   # Xem tổng thể sức khỏe hệ thống
squad fix-agent-setting                                        # Quét và tự động sửa các lỗi phân quyền, bẫy cấu hình
squad stack                                                    # Tự động nhận diện stack công nghệ và framework test
squad device-audit                                             # Kiểm tra thiết bị ADB thật và giả lập
squad audit-skills                                             # Kiểm tra danh sách kỹ năng chuyên môn đã nạp
squad ui-audit mock.html src/Component.tsx                     # Đối chiếu độ tương đồng thiết kế UI
```

---

## 📦 Installation & Setup

```bash
# Clone the repository
git clone https://github.com/VicnovaLabs/VicnovaLabs-squad.git
cd VicnovaLabs-squad

# Live Sync Development Mode (Symlinks to global IDE plugin path)
./installer/install.sh --target antigravity --dev

# Or Standalone Production Installation
./installer/install.sh --target antigravity    # Antigravity IDE
./installer/install.sh --target claude         # Claude Code
./installer/install.sh --target cursor         # Cursor IDE
./installer/install.sh --target codex          # Codex / OpenAI Universal LLMs
./installer/install.sh --target all            # All supported IDEs
```

---

## 🧪 Verification & Test Suite

Hệ thống được kiểm chứng bởi bộ kiểm thử tự động toàn diện bao phủ mọi luồng vận hành, các trường hợp lỗi và trường hợp biên:

```bash
python3 -m unittest discover tests
```

```text
Ran 233 tests in 76.831s

OK
```

- **233/233 Tests Passing**:
  - `tests/test_tier_architecture.py` (12 tests): Bộ quét Tier-0, đường dẫn tắt CSS/UI, phát hiện thay đổi AST public signature, cảnh báo rủi ro cao và xác thực ngân sách token của luật cốt lõi (< 500 tokens).
  - `tests/test_negative_cases.py` (18 tests): Chặn SSRF, xác thực TLS, từ chối ảnh trùng lặp SHA-256, hủy bỏ khi máy ảo thiếu bộ nhớ $<500$MB, phát hiện crash logcat, ngăn chặn merge khi git đang dirty.
  - `tests/test_office_integration.py` & `tests/test_loop_and_quota_alert.py`: Kiểm thử luồng SSE thời gian thực, điều khiển 2 chiều và ngắt mạch khi gặp HTTP 429.
  - `tests/test_edqa_v21.py` (32 tests): Bộ test kiểm tra toàn diện EDQA và Proof-of-Active-Interaction.
  - `tests/test_security_leak.py`: Đảm bảo **Zero-Leak** (không lộ socket, đường dẫn tuyệt đối, hay API key).

---

## 📄 License
MIT License. Built with pride by **VicnovaLabs**.
