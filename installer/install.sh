#!/usr/bin/env bash
# ==============================================================================
# VicnovaLabs Squad Universal Installer & Multi-IDE Integration Setup
# ==============================================================================
set -e

REPO_DIR="$( cd -P "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"
TARGET=""
MODE="user"
SCOPE="global"
DRY_RUN=false

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_banner() {
  echo -e "${BLUE}"
  echo "================================================================="
  echo "        🚀 VicnovaLabs SQUAD — MULTI-IDE FRAMEWORK INSTALLER     "
  echo "================================================================="
  echo -e "${NC}"
}

usage() {
  echo "Usage: $0 [OPTIONS]"
  echo ""
  echo "Options:"
  echo "  --target <ide>    Target IDE: antigravity | claude | cursor | codex | all"
  echo "  --scope <scope>   Installation scope: global (system/IDE wide) | workspace (current project only)"
  echo "  --mode <mode>     Mode: user (isolated copy) | dev (live-sync symlink to repo)"
  echo "  --dev             Shortcut for '--mode dev --scope global'"
  echo "  --local           Shortcut for '--scope workspace'"
  echo "  --dry-run         Simulate actions without modifying files"
  echo "  -h, --help        Show this help message"
  echo ""
  exit 1
}

# Parse flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET="$2"
      shift 2
      ;;
    --scope)
      SCOPE="$2"
      shift 2
      ;;
    --mode)
      MODE="$2"
      shift 2
      ;;
    --dev)
      MODE="dev"
      SCOPE="global"
      shift
      ;;
    --local|--workspace)
      SCOPE="workspace"
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      usage
      ;;
  esac
done

print_banner

# Step 1: Security & .env guidance
echo -e "${BLUE}▶ [1/4] Checking Environment & Security Guidelines...${NC}"
echo -e "${CYAN}ℹ️  Lưu ý bảo mật về API Keys:${NC}"
echo -e "   - Để bảo mật tuyệt đối, KHÔNG lưu API keys nhạy cảm vào .env của repository dự án."
echo -e "   - Đối với Antigravity: cấu hình key trong ${YELLOW}~/.gemini/config/.env${NC}"
echo -e "   - Đối với Claude/Cursor/Codex: cấu hình key trong ${YELLOW}Environment Variables${NC} của máy/IDE."
echo -e "   - Hệ thống Squad mặc định chạy ${GREEN}hoàn toàn offline và miễn phí (0 token)${NC} nếu không có API key."
echo ""

# Step 2: Interactive menu if target not provided
if [ -z "$TARGET" ]; then
  echo "Chọn IDE bạn muốn cấu hình:"
  echo "  1) Antigravity (Gemini)"
  echo "  2) Claude Code"
  echo "  3) Cursor"
  echo "  4) Codex / Universal"
  echo "  5) Tất cả (All IDEs)"
  read -p "Nhập lựa chọn [1-5]: " choice
  case "$choice" in
    1) TARGET="antigravity" ;;
    2) TARGET="claude" ;;
    3) TARGET="cursor" ;;
    4) TARGET="codex" ;;
    5) TARGET="all" ;;
    *) echo -e "${RED}Lựa chọn không hợp lệ, hủy bỏ.${NC}"; exit 1 ;;
  esac
fi

# Step 3: Configure Target IDE
TARGET_UPPER=$(echo "$TARGET" | tr '[:lower:]' '[:upper:]')
MODE_UPPER=$(echo "$MODE" | tr '[:lower:]' '[:upper:]')
SCOPE_UPPER=$(echo "$SCOPE" | tr '[:lower:]' '[:upper:]')
echo -e "${BLUE}▶ [2/4] Configuring Target: ${TARGET_UPPER} (Scope: ${SCOPE_UPPER}, Mode: ${MODE_UPPER})...${NC}"

setup_antigravity() {
  local GEMINI_PLUGINS="$HOME/.gemini/config/plugins"
  local GLOBAL_TARGET="$GEMINI_PLUGINS/specialized-squad"
  local ADAPTER_DIR="$REPO_DIR/integrations/antigravity"

  if [ "$SCOPE" = "workspace" ]; then
    local WORKSPACE_AGENTS="$PWD/.agents/agents"
    echo "Installing Antigravity agents into local workspace: $WORKSPACE_AGENTS..."
    if [ "$DRY_RUN" = true ]; then
      echo -e "${YELLOW}[DRY-RUN] Would create $WORKSPACE_AGENTS and copy agents/*.md${NC}"
      return
    fi
    mkdir -p "$WORKSPACE_AGENTS"
    cp -f "$REPO_DIR/agents/"*.md "$WORKSPACE_AGENTS/"
    echo -e "${GREEN}✓ Successfully synced 6 squad agents into local workspace: $WORKSPACE_AGENTS${NC}"
  else
    echo "Installing Antigravity global plugin: $GLOBAL_TARGET..."
    if [ "$DRY_RUN" = true ]; then
      echo -e "${YELLOW}[DRY-RUN] Target directory: $GLOBAL_TARGET${NC}"
      echo -e "${YELLOW}[DRY-RUN] Source adapter: $ADAPTER_DIR (Mode: $MODE)${NC}"
      return
    fi

    mkdir -p "$GEMINI_PLUGINS"

    if [ "$MODE" = "dev" ]; then
      if [ -e "$GLOBAL_TARGET" ] && [ ! -L "$GLOBAL_TARGET" ]; then
        BACKUP="$GEMINI_PLUGINS/specialized-squad.bak_$(date +%Y%m%d_%H%M%S)"
        echo -e "${YELLOW}Backing up existing global setup to: $BACKUP${NC}"
        mv "$GLOBAL_TARGET" "$BACKUP"
      elif [ -L "$GLOBAL_TARGET" ]; then
        rm "$GLOBAL_TARGET"
      fi

      echo "Creating live-sync symlink: $GLOBAL_TARGET -> $ADAPTER_DIR..."
      ln -sf "$ADAPTER_DIR" "$GLOBAL_TARGET"
      echo -e "${GREEN}✓ Live Sync Link established! Mọi sửa đổi trong repo này sẽ tự động cập nhật vào Antigravity toàn cục.${NC}"
    else
      mkdir -p "$GLOBAL_TARGET"
      cp -r "$ADAPTER_DIR"/* "$GLOBAL_TARGET"/
      echo -e "${GREEN}✓ Installed isolated squad plugin into Antigravity ($GLOBAL_TARGET).${NC}"
    fi
  fi
}

setup_claude() {
  if [ "$SCOPE" = "workspace" ]; then
    echo "Configuring Claude Code in workspace: $PWD/CLAUDE.md..."
    if [ "$DRY_RUN" = true ]; then
      echo -e "${YELLOW}[DRY-RUN] Would copy CLAUDE.md to $PWD${NC}"
      return
    fi
    cp "$REPO_DIR/integrations/claude_code/CLAUDE.md" "$PWD/CLAUDE.md"
    echo -e "${GREEN}✓ Created CLAUDE.md in current workspace.${NC}"
  else
    local DEST="$HOME/.claude"
    echo "Configuring Claude Code globally in $DEST..."
    if [ "$DRY_RUN" = true ]; then
      echo -e "${YELLOW}[DRY-RUN] Would copy settings and CLAUDE.md to $DEST${NC}"
      return
    fi
    mkdir -p "$DEST"
    cp "$REPO_DIR/integrations/claude_code/CLAUDE.md" "$PWD/CLAUDE.md" 2>/dev/null || true
    cp "$REPO_DIR/integrations/claude_code/settings.json" "$DEST/squad-settings.json" 2>/dev/null || true
    echo -e "${GREEN}✓ Configured CLAUDE.md and global squad settings for Claude Code.${NC}"
  fi
}

setup_cursor() {
  local CURSOR_DIR="$PWD/.cursor/rules"
  echo "Configuring Cursor in workspace: $CURSOR_DIR..."
  if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}[DRY-RUN] Would create $CURSOR_DIR and copy .cursorrules & .mdc rules${NC}"
    return
  fi

  mkdir -p "$CURSOR_DIR"
  cp "$REPO_DIR/integrations/cursor/.cursorrules" "$PWD/.cursorrules" 2>/dev/null || true
  cp "$REPO_DIR/integrations/cursor/rules/"*.mdc "$CURSOR_DIR"/ 2>/dev/null || true
  echo -e "${GREEN}✓ Configured .cursorrules and MDC rules in $CURSOR_DIR.${NC}"
}

setup_codex() {
  echo "Configuring Codex / Universal in workspace: $PWD/AGENTS.md..."
  if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}[DRY-RUN] Would create AGENTS.md in current workspace${NC}"
    return
  fi

  cp "$REPO_DIR/integrations/codex/AGENTS.md" "$PWD/AGENTS.md" 2>/dev/null || true
  echo -e "${GREEN}✓ Created AGENTS.md in project root.${NC}"
}

case "$TARGET" in
  antigravity) setup_antigravity ;;
  claude) setup_claude ;;
  cursor) setup_cursor ;;
  codex) setup_codex ;;
  all)
    setup_antigravity
    setup_claude
    setup_cursor
    setup_codex
    ;;
esac

# Step 4: CLI binary linking & Python package registration
echo -e "${BLUE}▶ [3/4] Registering 'squad' CLI executable & Python package...${NC}"
INSTALL_BIN="$HOME/.local/bin"
if [ "$DRY_RUN" = false ]; then
  mkdir -p "$INSTALL_BIN"
  ln -sf "$REPO_DIR/bin/squad" "$INSTALL_BIN/squad"
  echo -e "${GREEN}✓ Linked executable into $INSTALL_BIN/squad${NC}"
  if [[ ":$PATH:" != *":$INSTALL_BIN:"* ]]; then
    echo -e "${YELLOW}Lưu ý: Thêm $INSTALL_BIN vào PATH của bạn nếu chưa có: export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
  fi

  # Register squad_engine package into Python user environment
  echo "Registering 'squad_engine' package into Python environment..."
  python3 -m pip install --user -e "$REPO_DIR" --break-system-packages >/dev/null 2>&1 || \
  python3 -m pip install -e "$REPO_DIR" >/dev/null 2>&1 || true

  # Ensure .pth fallback in user site-packages for non-pip environments
  python3 -c "import site, pathlib; p = pathlib.Path(site.getusersitepackages()); p.mkdir(parents=True, exist_ok=True); (p / 'vicnovalab_squad.pth').write_text('$REPO_DIR\n')" 2>/dev/null || true
  echo -e "${GREEN}✓ Registered 'squad_engine' into Python site-packages.${NC}"
fi

# Step 5: Verification & Status
echo -e "${BLUE}▶ [4/4] Verifying Installation Status & Skills...${NC}"
if [ "$DRY_RUN" = false ]; then
  "$REPO_DIR/bin/squad" status
  echo ""
  "$REPO_DIR/bin/squad" audit-skills
fi

echo ""
echo -e "${GREEN}🎉 Cài đặt VicnovaLabs Squad hoàn tất!${NC}"
echo -e "💡 Bạn có thể chạy ${BLUE}squad status${NC} hoặc ${BLUE}squad dispatch \"<task>\"${NC} để bắt đầu."
echo -e "💡 Để kiểm tra lại danh sách kỹ năng tùy chọn: ${BLUE}squad audit-skills${NC}"
