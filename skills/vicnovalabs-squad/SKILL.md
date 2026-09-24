---
name: vicnovalabs-squad
description: Quản lý và thiết lập chế độ điều phối Squad (suggest, smart, auto, inline). Kích hoạt khi gõ /vicnolabs-squad [mode] hoặc /vicnovalabs-squad [mode].
role: Orchestrator
phase: all
squad: VicnovaLabs-squad
version: 1.2.0
---

# VicnovaLabs Squad — Dispatch Mode Manager & Skill Summoning

Skill này cung cấp cơ chế thiết lập và quản lý chế độ điều phối (Dispatch Mode) cho hệ thống Squad Agent. Cho phép người dùng chuyển đổi linh hoạt giữa các chế độ thực thi để tối ưu chi phí token, tăng tốc độ xử lý hoặc tự động hóa sâu.

---

## 1. Cú pháp kích hoạt

Người dùng có thể gõ các lệnh sau trực tiếp trong chat:
- `/vicnolabs-squad <mode>` (hoặc `/vicnovalabs-squad <mode>`)
- `/vicnolabs-squad mode <mode>`
- `/vicnolabs-squad` (Xem chế độ hiện tại và danh sách tùy chọn)

---

## 2. Các Chế độ Điều Phối (Dispatch Modes)

| Mode | Ý nghĩa & Hành vi | Trường hợp sử dụng |
| :--- | :--- | :--- |
| **`suggest`** *(Mặc định cho Project)* | **Gợi ý Squad qua thẻ Skill Card**: Mặc định Main Agent xử lý **inline trực tiếp** (nhanh, tiết kiệm token). Chỉ triệu tập subagent khi người dùng gọi on-demand (*"gọi squad"*, *"dùng dev-agent"*, *"/squad"*). | Dự án đang phát triển thường ngày, muốn tiết kiệm chi phí token tối đa. |
| **`smart`** | **Tự động phân tầng thông minh**: Inline cho tác vụ đơn giản; gợi ý cho tác vụ trung bình; tự động triệu tập subagent khi độ phức tạp $\ge 4$ hoặc composite fan-out. | Dự án lớn với nhiều tác vụ đan xen giữa đơn giản và phức tạp. |
| **`auto`** | **Tự động triệu tập toàn bộ**: Mọi tác vụ thuộc 6 miền (`dev`, `qa`, `design`, `debug`, `ba`, `marketing`) đều tự động spawn subagent chuyên biệt chạy độc lập. | Chế độ rảnh tay hoàn toàn, ủy quyền hoàn toàn cho subagent. |
| **`inline`** *(Mặc định cho Chat ngoài Project)* | **Thực thi trực tiếp 100%**: Vô hiệu hóa hoàn toàn subagent, Main Agent tự xử lý tất cả trên context hiện tại. | Các buổi chat hỏi đáp, sửa lỗi nhanh hoặc chat ngoài project. |

---

## 3. Quy tắc Phạm vi (Scope Rules)

### A. Đối với Session thuộc Project Workspace
- Khi session chat đang mở trong một thư mục dự án (có `.git`, `PROJECT_PROGRESS.md`, `package.json`, `pubspec.yaml`,...):
- Chế độ mặc định là **`suggest`**.
- Khi người dùng gõ `/vicnolabs-squad <mode>`, chế độ mới sẽ được **lưu cố định vào Project** (qua file `.squad_mode` và `.env` tại thư mục gốc của project).
- Mọi câu lệnh tiếp theo trong project này đều tuân thủ chế độ đó.

### B. Đối với Session Chat KHÔNG thuộc Project (Standalone Chat)
- Khi session chat mở ở thư mục tự do (ví dụ `$HOME`, thư mục tạm, hoặc không gắn với repo code):
- **ƯU TIÊN INLINE**: Hệ thống tự động đặt mặc định là **`inline`** để tránh lãng phí token và tài nguyên.
- Khi người dùng gõ `/vicnolabs-squad <mode>`, chế độ mới sẽ được **lưu riêng cho Session Chat đó** (lưu trong session cache/brain).
- Chế độ chỉ có hiệu lực trong phiên chat này, không ảnh hưởng sang các project hoặc session khác.

---

## 4. Lệnh CLI tương ứng

Hệ thống cung cấp lệnh CLI qua `squad mode` hoặc `jev_triage.py mode`:
```bash
# Xem chế độ hiện tại
python3 jev_triage.py mode

# Đặt chế độ cho project hiện tại
python3 jev_triage.py mode smart

# Đặt chế độ riêng cho session
python3 jev_triage.py mode auto --scope session --session <session_id>
```
