/**
 * VicnovaLabs Squad — Virtual Animated Office & Telemetry Mission Control Client App
 * Features:
 * - 2D HTML5 Canvas Animated Office Simulation with 6 moving Agent Characters
 * - Walking pathfinding, sitting, typing, coffee sipping, and floating speech bubbles
 * - Real-time FinOps Token & Cost live odometer updates
 * - Two-way mission control interlocks & Live terminal streaming
 */

// Global State
let sessionToken = '';
let eventSource = null;
let autoScroll = true;
let isGlobalPaused = false;
let pausedAgents = new Set();
let serverStartTime = Date.now();
let selectedAgent = null;

// DOM Elements
const canvas = document.getElementById('officeCanvas');
const ctx = canvas ? canvas.getContext('2d') : null;
const topTotalTokens = document.getElementById('topTotalTokens');
const topTotalSpend = document.getElementById('topTotalSpend');
const topBurnRate = document.getElementById('topBurnRate');
const budgetBadge = document.getElementById('budgetBadge');
const budgetText = document.getElementById('budgetText');
const activeAgentsCount = document.getElementById('activeAgentsCount');
const finopsTotalCost = document.getElementById('finopsTotalCost');
const finopsCostPerMin = document.getElementById('finopsCostPerMin');
const finopsBurnRate = document.getElementById('finopsBurnRate');
const finopsCallCount = document.getElementById('finopsCallCount');
const agentBreakdownList = document.getElementById('agentBreakdownList');
const modelBreakdownList = document.getElementById('modelBreakdownList');
const terminalWindow = document.getElementById('terminalWindow');
const chkAutoScroll = document.getElementById('chkAutoScroll');
const btnClearTerminal = document.getElementById('btnClearTerminal');
const btnEmergencyStop = document.getElementById('btnEmergencyStop');
const btnGlobalPause = document.getElementById('btnGlobalPause');
const gateDecisionBadge = document.getElementById('gateDecisionBadge');
const progressPercentage = document.getElementById('progressPercentage');
const progressBarFill = document.getElementById('progressBarFill');
const progressTaskList = document.getElementById('progressTaskList');
const serverUptime = document.getElementById('serverUptime');
const connectionStatus = document.getElementById('connectionStatus');
const agentInspectorHud = document.getElementById('agentInspectorHud');
const alertContainer = document.getElementById('alertContainer');

// ==============================================================================
// 1. VIRTUAL OFFICE 2D SIMULATION ENGINE (CANVAS)
// ==============================================================================

const WORKSTATIONS = {
  dev: { x: 140, y: 110, name: 'DEV LAB', icon: '💻', color: '#06b6d4', desc: 'Code Matrix & Multi-Monitors' },
  qa: { x: 480, y: 110, name: 'QA INSPECTION', icon: '🔍', color: '#10b981', desc: 'Device Rack & Bug Radar' },
  design: { x: 820, y: 110, name: 'DESIGN STUDIO', icon: '🎨', color: '#ec4899', desc: 'Canvas Easel & UI Swatches' },
  ba: { x: 140, y: 340, name: 'BA ARCHITECTURE', icon: '📋', color: '#f59e0b', desc: 'Whiteboard & Flowcharts' },
  debug: { x: 480, y: 340, name: 'DEBUG ICU', icon: '🩺', color: '#f43f5e', desc: 'ECG Monitor & Emergency Station' },
  marketing: { x: 820, y: 340, name: 'GROWTH HUB', icon: '📣', color: '#6366f1', desc: 'Launch Rocket & CRO Board' },
};

const LOUNGE = { x: 480, y: 225, name: 'Coffee Lounge' };

class AgentCharacter {
  constructor(role, name, avatar, color, deskX, deskY, idleX, idleY) {
    this.role = role;
    this.name = name;
    this.avatar = avatar;
    this.color = color;
    this.deskX = deskX;
    this.deskY = deskY;
    this.idleX = idleX;
    this.idleY = idleY;

    // Start near coffee lounge
    this.x = idleX + (Math.random() * 60 - 30);
    this.y = idleY + (Math.random() * 40 - 20);
    this.targetX = this.deskX;
    this.targetY = this.deskY;

    this.state = 'IDLE'; // 'IDLE', 'WALKING', 'WORKING', 'PAUSED'
    this.speed = 2.2;
    this.walkCycle = 0;
    this.typingCycle = 0;
    this.facing = 'down';

    this.speechBubble = null;
    this.speechTimer = 0;
    this.currentAction = 'Standing by in lounge';
    this.tokens = 0;
    this.cost = 0.0;
    this.calls = 0;
    this.idleWanderTimer = Math.random() * 300 + 120;
  }

  say(text, durationFrames = 240) {
    this.speechBubble = text;
    this.speechTimer = durationFrames;
  }

  moveTo(targetX, targetY, onArriveState = 'WORKING') {
    this.targetX = targetX;
    this.targetY = targetY;
    this.onArriveState = onArriveState;
    this.state = 'WALKING';
  }

  update() {
    // Decrement speech timer
    if (this.speechTimer > 0) {
      this.speechTimer--;
      if (this.speechTimer <= 0) {
        this.speechBubble = null;
      }
    }

    // Walking pathfinding
    if (this.state === 'WALKING') {
      const dx = this.targetX - this.x;
      const dy = this.targetY - this.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (dist <= this.speed) {
        this.x = this.targetX;
        this.y = this.targetY;
        this.state = this.onArriveState || 'WORKING';
        if (this.state === 'WORKING') {
          this.typingCycle = 0;
        }
      } else {
        this.x += (dx / dist) * this.speed;
        this.y += (dy / dist) * this.speed;
        this.walkCycle += 0.2;
        if (Math.abs(dx) > Math.abs(dy)) {
          this.facing = dx > 0 ? 'right' : 'left';
        } else {
          this.facing = dy > 0 ? 'down' : 'up';
        }
      }
    } else if (this.state === 'WORKING') {
      this.typingCycle += 0.25;
    } else if (this.state === 'IDLE') {
      // Natural idle wandering in lounge
      this.idleWanderTimer--;
      if (this.idleWanderTimer <= 0) {
        this.idleWanderTimer = Math.random() * 400 + 200;
        const wanderX = LOUNGE.x + (Math.random() * 120 - 60);
        const wanderY = LOUNGE.y + (Math.random() * 40 - 20);
        this.moveTo(wanderX, wanderY, 'IDLE');
        if (Math.random() > 0.6) {
          const sips = ['Enjoying a sip of coffee ☕', 'Reviewing system architecture...', 'Hydrating at water cooler 💧'];
          this.say(sips[Math.floor(Math.random() * sips.length)], 180);
        }
      }
    }
  }

  draw(ctx) {
    ctx.save();

    const isPaused = pausedAgents.has(this.role) || isGlobalPaused;
    const isSelected = selectedAgent && selectedAgent.role === this.role;

    // 1. Floor Shadow
    ctx.beginPath();
    ctx.ellipse(this.x, this.y + 14, 12, 6, 0, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(0, 0, 0, 0.45)';
    ctx.fill();

    // 2. Selection / Active Glow
    if (isSelected) {
      ctx.beginPath();
      ctx.ellipse(this.x, this.y + 2, 20, 20, 0, 0, Math.PI * 2);
      ctx.strokeStyle = this.color;
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 4]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // 3. Legs (Walking Animation)
    let legOffset1 = 0;
    let legOffset2 = 0;
    if (this.state === 'WALKING') {
      legOffset1 = Math.sin(this.walkCycle) * 4;
      legOffset2 = -Math.sin(this.walkCycle) * 4;
    }

    ctx.fillStyle = '#1e293b';
    ctx.fillRect(this.x - 6, this.y + 4 + legOffset1, 4, 8);
    ctx.fillRect(this.x + 2, this.y + 4 + legOffset2, 4, 8);

    // 4. Torso / Body (Role Shirt Color)
    ctx.fillStyle = isPaused ? '#f59e0b' : (this.state === 'EXHAUSTED' ? '#f43f5e' : (this.state === 'LOOPING' ? '#f59e0b' : this.color));
    ctx.beginPath();
    ctx.roundRect(this.x - 9, this.y - 8, 18, 14, 3);
    ctx.fill();

    // 5. Head & Face
    const isExhausted = this.state === 'EXHAUSTED';
    const isLooping = this.state === 'LOOPING';
    ctx.fillStyle = isExhausted ? '#fecdd3' : '#fde047'; // Paled tone if exhausted
    ctx.beginPath();
    ctx.arc(this.x, this.y - 14, 9, 0, Math.PI * 2);
    ctx.fill();

    // Hair / Cap
    ctx.fillStyle = '#334155';
    ctx.beginPath();
    ctx.arc(this.x, this.y - 17, 9, Math.PI, Math.PI * 2);
    ctx.fill();

    // Eyes / Expression
    if (isExhausted) {
      // Slumped (x_x) eyes
      ctx.font = 'bold 8px monospace';
      ctx.fillStyle = '#f43f5e';
      ctx.textAlign = 'center';
      ctx.fillText('x_x', this.x, this.y - 12);

      // Sweat drop
      ctx.fillStyle = '#38bdf8';
      ctx.beginPath();
      ctx.arc(this.x + 10, this.y - 18, 2, 0, Math.PI * 2);
      ctx.fill();

      // Floating Zzz
      ctx.font = 'bold 9px monospace';
      ctx.fillStyle = '#cbd5e1';
      ctx.fillText('Zzz', this.x + 14, this.y - 25);
    } else if (isLooping) {
      // Dizzy (@_@) eyes
      ctx.font = 'bold 8px monospace';
      ctx.fillStyle = '#f59e0b';
      ctx.textAlign = 'center';
      ctx.fillText('@_@', this.x, this.y - 12);

      // Exclamation alert
      ctx.font = 'bold 10px sans-serif';
      ctx.fillStyle = '#f59e0b';
      ctx.fillText('⚠️', this.x + 10, this.y - 24);
    } else {
      ctx.fillStyle = '#0f172a';
      let eyeOffsetX = this.facing === 'left' ? -2 : this.facing === 'right' ? 2 : 0;
      ctx.fillRect(this.x - 4 + eyeOffsetX, this.y - 16, 2, 3);
      ctx.fillRect(this.x + 2 + eyeOffsetX, this.y - 16, 2, 3);
    }

    // 6. Hands / Action Poses
    if (this.state === 'WORKING') {
      // Typing animation
      const typeHand1 = Math.sin(this.typingCycle) * 3;
      const typeHand2 = Math.cos(this.typingCycle) * 3;
      ctx.fillStyle = '#fde047';
      ctx.fillRect(this.x - 10, this.y - 2 + typeHand1, 4, 4);
      ctx.fillRect(this.x + 6, this.y - 2 + typeHand2, 4, 4);

      // Typing Sparks / Matrix particles
      ctx.fillStyle = this.color;
      ctx.fillRect(this.x - 8 + Math.random() * 16, this.y - 24 - Math.random() * 10, 2, 2);
    } else if (isExhausted) {
      // Limp hands on desk
      ctx.fillStyle = '#fecdd3';
      ctx.fillRect(this.x - 9, this.y + 2, 4, 3);
      ctx.fillRect(this.x + 5, this.y + 2, 4, 3);
    } else {
      // Relaxed or holding coffee
      ctx.fillStyle = '#fde047';
      ctx.fillRect(this.x - 11, this.y - 4, 3, 5);
      ctx.fillRect(this.x + 8, this.y - 4, 3, 5);
      if (this.state === 'IDLE') {
        // Draw tiny coffee mug
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(this.x + 10, this.y - 5, 4, 5);
      }
    }

    // 7. Overhead Name Tag & Badge
    ctx.font = 'bold 9px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';

    let tagSuffix = '';
    if (isPaused) tagSuffix = ' [PAUSED]';
    else if (isExhausted) tagSuffix = ' [EXHAUSTED]';
    else if (isLooping) tagSuffix = ' [LOOP]';

    const tagText = `${this.name.toUpperCase()}${tagSuffix}`;
    const tagWidth = ctx.measureText(tagText).width + 8;

    ctx.fillStyle = 'rgba(7, 9, 14, 0.85)';
    ctx.beginPath();
    ctx.roundRect(this.x - tagWidth / 2, this.y - 34, tagWidth, 12, 3);
    ctx.fill();
    ctx.strokeStyle = isPaused ? '#f59e0b' : (isExhausted ? '#f43f5e' : (isLooping ? '#f59e0b' : this.color));
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = '#ffffff';
    ctx.fillText(tagText, this.x, this.y - 25);

    // Status Dot
    ctx.beginPath();
    ctx.arc(this.x - tagWidth / 2 + 5, this.y - 28, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = isPaused ? '#f59e0b' : (isExhausted ? '#f43f5e' : (isLooping ? '#f59e0b' : (this.state === 'WORKING' ? '#10b981' : '#6b7280')));
    ctx.fill();

    // 8. Speech Bubble (when talking or executing tool)
    if (this.speechBubble) {
      this.drawSpeechBubble(ctx);
    }

    ctx.restore();
  }

  drawSpeechBubble(ctx) {
    ctx.save();
    ctx.font = '10px "Plus Jakarta Sans", sans-serif';
    const padding = 8;
    const maxChars = 32;
    let displayText = this.speechBubble;
    if (displayText.length > maxChars) {
      displayText = displayText.substring(0, maxChars) + '...';
    }
    const textWidth = ctx.measureText(displayText).width;
    const bubbleWidth = textWidth + padding * 2;
    const bubbleHeight = 22;
    const bubbleX = this.x - bubbleWidth / 2;
    const bubbleY = this.y - 58;

    // Bubble Background
    ctx.fillStyle = 'rgba(13, 18, 31, 0.95)';
    ctx.strokeStyle = this.color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(bubbleX, bubbleY, bubbleWidth, bubbleHeight, 6);
    ctx.fill();
    ctx.stroke();

    // Tail
    ctx.beginPath();
    ctx.moveTo(this.x - 4, bubbleY + bubbleHeight);
    ctx.lineTo(this.x, bubbleY + bubbleHeight + 6);
    ctx.lineTo(this.x + 4, bubbleY + bubbleHeight);
    ctx.fillStyle = 'rgba(13, 18, 31, 0.95)';
    ctx.fill();
    ctx.stroke();

    // Text
    ctx.fillStyle = '#f3f4f6';
    ctx.textAlign = 'center';
    ctx.fillText(displayText, this.x, bubbleY + 14);
    ctx.restore();
  }
}

// Instantiate the 6 Squad Agents
const agents = {
  dev: new AgentCharacter('dev', 'Dev', '👨‍💻', '#06b6d4', WORKSTATIONS.dev.x, WORKSTATIONS.dev.y + 24, LOUNGE.x - 70, LOUNGE.y),
  qa: new AgentCharacter('qa', 'QA', '🕵️‍♂️', '#10b981', WORKSTATIONS.qa.x, WORKSTATIONS.qa.y + 24, LOUNGE.x - 25, LOUNGE.y - 15),
  design: new AgentCharacter('design', 'Design', '👩‍🎨', '#ec4899', WORKSTATIONS.design.x, WORKSTATIONS.design.y + 24, LOUNGE.x + 40, LOUNGE.y - 15),
  ba: new AgentCharacter('ba', 'BA', '📋', '#f59e0b', WORKSTATIONS.ba.x, WORKSTATIONS.ba.y - 20, LOUNGE.x - 70, LOUNGE.y + 20),
  debug: new AgentCharacter('debug', 'Debug', '👨‍⚕️', '#f43f5e', WORKSTATIONS.debug.x, WORKSTATIONS.debug.y - 20, LOUNGE.x + 70, LOUNGE.y),
  marketing: new AgentCharacter('marketing', 'Growth', '📣', '#6366f1', WORKSTATIONS.marketing.x, WORKSTATIONS.marketing.y - 20, LOUNGE.x + 35, LOUNGE.y + 20),
};

// ==============================================================================
// 2. CANVAS DRAWING & ENVIRONMENT
// ==============================================================================

function drawOfficeFloor() {
  if (!ctx || !canvas) return;

  const width = canvas.width;
  const height = canvas.height;

  // Clear background
  ctx.fillStyle = '#080c16';
  ctx.fillRect(0, 0, width, height);

  // Checkerboard pixel floor grid
  const tileSize = 32;
  for (let x = 0; x < width; x += tileSize) {
    for (let y = 0; y < height; y += tileSize) {
      const isAlt = ((x / tileSize) + (y / tileSize)) % 2 === 0;
      ctx.fillStyle = isAlt ? '#0c1220' : '#0a0f1b';
      ctx.fillRect(x, y, tileSize, tileSize);
    }
  }

  // Draw Central Lounge Area (Rugs & Coffee Zone)
  ctx.save();
  ctx.beginPath();
  ctx.ellipse(LOUNGE.x, LOUNGE.y, 140, 60, 0, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(6, 182, 212, 0.05)';
  ctx.fill();
  ctx.strokeStyle = 'rgba(6, 182, 212, 0.15)';
  ctx.setLineDash([6, 6]);
  ctx.stroke();
  ctx.setLineDash([]);

  // Coffee Machine Bar Table
  ctx.fillStyle = '#1e293b';
  ctx.beginPath();
  ctx.roundRect(LOUNGE.x - 40, LOUNGE.y - 15, 80, 26, 4);
  ctx.fill();
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
  ctx.stroke();

  // Coffee Machine details
  ctx.fillStyle = '#334155';
  ctx.fillRect(LOUNGE.x - 25, LOUNGE.y - 22, 24, 12);
  ctx.fillStyle = '#06b6d4';
  ctx.fillRect(LOUNGE.x - 22, LOUNGE.y - 18, 6, 4); // Screen

  // Water Cooler
  ctx.fillStyle = '#38bdf8';
  ctx.beginPath();
  ctx.arc(LOUNGE.x + 24, LOUNGE.y - 16, 7, 0, Math.PI * 2);
  ctx.fill();

  ctx.font = '10px "Plus Jakarta Sans", sans-serif';
  ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
  ctx.textAlign = 'center';
  ctx.fillText('☕ SQUAD LOUNGE', LOUNGE.x, LOUNGE.y + 4);
  ctx.restore();

  // Draw 6 Workstations
  Object.entries(WORKSTATIONS).forEach(([key, ws]) => {
    drawWorkstation(ws, agents[key]);
  });

  // Update and draw each Agent
  Object.values(agents).forEach((agent) => {
    agent.update();
    agent.draw(ctx);
  });
}

function drawWorkstation(ws, agent) {
  const isAgentWorking = agent && agent.state === 'WORKING';

  ctx.save();
  // Desk Shadow
  ctx.fillStyle = 'rgba(0, 0, 0, 0.35)';
  ctx.beginPath();
  ctx.ellipse(ws.x, ws.y + 12, 48, 16, 0, 0, Math.PI * 2);
  ctx.fill();

  // Desk Surface
  ctx.fillStyle = '#131b2e';
  ctx.beginPath();
  ctx.roundRect(ws.x - 46, ws.y - 18, 92, 34, 6);
  ctx.fill();
  ctx.strokeStyle = isAgentWorking ? ws.color : 'rgba(255, 255, 255, 0.12)';
  ctx.lineWidth = isAgentWorking ? 2 : 1;
  ctx.stroke();

  // Computer Monitors
  ctx.fillStyle = '#1e293b';
  ctx.fillRect(ws.x - 24, ws.y - 26, 48, 16);
  ctx.fillStyle = isAgentWorking ? ws.color : '#0f172a';
  ctx.fillRect(ws.x - 22, ws.y - 24, 44, 12);

  // Monitor Glow when working
  if (isAgentWorking) {
    ctx.shadowColor = ws.color;
    ctx.shadowBlur = 10;
    ctx.fillStyle = ws.color;
    ctx.fillRect(ws.x - 20, ws.y - 22, 40, 8);
    ctx.shadowBlur = 0;
  }

  // Workstation Icon & Label
  ctx.font = 'bold 10px "JetBrains Mono", monospace';
  ctx.fillStyle = isAgentWorking ? ws.color : '#94a3b8';
  ctx.textAlign = 'center';
  ctx.fillText(`${ws.icon} ${ws.name}`, ws.x, ws.y + 30);
  ctx.restore();
}

// Canvas Loop (60 FPS with visibility check)
let lastFrameTime = 0;
function simulationLoop(timestamp) {
  drawOfficeFloor();
  requestAnimationFrame(simulationLoop);
}

// Canvas Click & Raycast
if (canvas) {
  canvas.addEventListener('click', (e) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const clickX = (e.clientX - rect.left) * scaleX;
    const clickY = (e.clientY - rect.top) * scaleY;

    // Check if clicked an agent
    let clickedAgent = null;
    Object.values(agents).forEach((ag) => {
      const dist = Math.hypot(ag.x - clickX, ag.y - clickY);
      if (dist <= 24) {
        clickedAgent = ag;
      }
    });

    if (clickedAgent) {
      selectAgent(clickedAgent);
      return;
    }

    // Check if clicked a workstation
    let clickedWs = null;
    Object.entries(WORKSTATIONS).forEach(([k, ws]) => {
      const dist = Math.hypot(ws.x - clickX, ws.y - clickY);
      if (dist <= 48) {
        clickedWs = agents[k];
      }
    });

    if (clickedWs) {
      selectAgent(clickedWs);
      return;
    }

    // Otherwise, move selected agent to click point
    if (selectedAgent) {
      selectedAgent.moveTo(clickX, clickY, 'IDLE');
      selectedAgent.say('Moving here!', 120);
    }
  });
}

function selectAgent(agent) {
  selectedAgent = agent;
  if (!agentInspectorHud) return;

  agentInspectorHud.style.display = 'flex';
  const inspAvatar = document.getElementById('inspAvatar');
  const inspName = document.getElementById('inspName');
  const inspStatus = document.getElementById('inspStatus');
  const inspAction = document.getElementById('inspAction');
  const inspTokens = document.getElementById('inspTokens');
  const inspCost = document.getElementById('inspCost');
  const btnInspPause = document.getElementById('btnInspPause');

  if (inspAvatar) inspAvatar.textContent = agent.avatar;
  if (inspName) inspName.textContent = `${agent.name} Agent`;
  if (inspStatus) {
    const isPaused = pausedAgents.has(agent.role) || isGlobalPaused;
    let stClass = 'badge-idle';
    let stText = agent.state;
    if (isPaused) {
      stClass = 'badge-paused';
      stText = 'PAUSED';
    } else if (agent.state === 'WORKING') {
      stClass = 'badge-active';
    } else if (agent.state === 'EXHAUSTED') {
      stClass = 'badge-exhausted';
      stText = 'EXHAUSTED (QUOTA DEPLETED)';
    } else if (agent.state === 'LOOPING') {
      stClass = 'badge-looping';
      stText = 'LOOPING (REPEATING)';
    }
    inspStatus.textContent = stText;
    inspStatus.className = `inspector-status ${stClass}`;
  }
  if (inspAction) inspAction.textContent = agent.currentAction;
  if (inspTokens) inspTokens.textContent = `${(agent.tokens || 0).toLocaleString()} t`;
  if (inspCost) inspCost.textContent = `$${(agent.cost || 0).toFixed(4)}`;
  if (btnInspPause) {
    const isPaused = pausedAgents.has(agent.role);
    btnInspPause.textContent = isPaused ? '▶️ Resume' : '⏸ Pause';
  }
}

function closeInspectorHud() {
  if (agentInspectorHud) agentInspectorHud.style.display = 'none';
  selectedAgent = null;
}

function togglePauseSelectedAgent() {
  if (!selectedAgent) return;
  togglePauseAgent(selectedAgent.role);
  closeInspectorHud();
}

function triggerCoffeeBreak() {
  Object.values(agents).forEach((ag) => {
    const offsetX = Math.random() * 100 - 50;
    const offsetY = Math.random() * 40 - 20;
    ag.moveTo(LOUNGE.x + offsetX, LOUNGE.y + offsetY, 'IDLE');
    ag.say('Coffee break! ☕', 200);
  });
  appendTerminalLine('[OFFICE] All squad agents called to Lounge for a coffee break.', 'term-system');
}

function sendAllToDesks() {
  Object.values(agents).forEach((ag) => {
    ag.moveTo(ag.deskX, ag.deskY, 'WORKING');
    ag.say('Back to workstation!', 180);
  });
  appendTerminalLine('[OFFICE] All squad agents dispatched to their workstations.', 'term-system');
}

// ==============================================================================
// 3. SSE TELEMETRY & REAL-TIME TOKEN BURNS
// ==============================================================================

function init() {
  const urlParams = new URLSearchParams(window.location.search);
  sessionToken = urlParams.get('token') || localStorage.getItem('squad_token') || '';
  if (sessionToken) {
    localStorage.setItem('squad_token', sessionToken);
  }

  // Connect SSE
  connectSSE();

  // Status Polling Fallback
  fetchStatusSnapshot();
  setInterval(fetchStatusSnapshot, 3000);

  // Setup Listeners
  if (chkAutoScroll) chkAutoScroll.addEventListener('change', (e) => (autoScroll = e.target.checked));
  if (btnClearTerminal) {
    btnClearTerminal.addEventListener('click', () => {
      terminalWindow.innerHTML = '';
      appendTerminalLine('Terminal buffer cleared.', 'term-info');
    });
  }
  if (btnEmergencyStop) btnEmergencyStop.addEventListener('click', emergencyStopAll);

  // Tickers
  setInterval(updateUptimeTicker, 1000);

  // Launch Canvas Animation
  requestAnimationFrame(simulationLoop);
}

function connectSSE() {
  if (eventSource) eventSource.close();

  const sseUrl = `/api/stream?token=${encodeURIComponent(sessionToken)}`;
  eventSource = new EventSource(sseUrl);

  eventSource.onopen = () => {
    updateConnectionStatus(true);
    appendTerminalLine('[SSE] Real-time stream connected.', 'term-system');
  };

  eventSource.onerror = () => updateConnectionStatus(false);

  eventSource.onmessage = (e) => {
    try {
      handleTelemetryEvent(JSON.parse(e.data));
    } catch (err) {}
  };

  const events = [
    'INIT_STATE', 'AGENT_STATUS', 'TOOL_CALL', 'TOKEN_USAGE',
    'PROGRESS_UPDATE', 'GATE_EVENT', 'CONTROL_CHANGE', 'LOG_OUTPUT',
    'LOOP_DETECTED', 'QUOTA_EXHAUSTED', 'AGENT_EXHAUSTED'
  ];
  events.forEach((evtName) => {
    eventSource.addEventListener(evtName, (e) => {
      try {
        handleTelemetryEvent(JSON.parse(e.data));
      } catch (err) {}
    });
  });
}

function updateConnectionStatus(online) {
  if (!connectionStatus) return;
  if (online) {
    connectionStatus.innerHTML = '<span class="status-dot pulsing"></span><span class="status-label">STREAMING LIVE</span>';
    connectionStatus.style.borderColor = 'rgba(16, 185, 129, 0.25)';
    connectionStatus.style.color = 'var(--accent-emerald)';
  } else {
    connectionStatus.innerHTML = '<span class="status-dot" style="background:#f43f5e; box-shadow:none;"></span><span class="status-label">RECONNECTING...</span>';
    connectionStatus.style.borderColor = 'rgba(244, 63, 94, 0.25)';
    connectionStatus.style.color = 'var(--accent-rose)';
  }
}

function handleTelemetryEvent(event) {
  const type = event.event_type;
  const data = event.data || {};

  switch (type) {
    case 'INIT_STATE':
      if (data.finops) updateFinOpsUI(data.finops);
      if (data.control) updateControlUI(data.control);
      if (data.progress) updateProgressUI(data.progress);
      break;

    case 'AGENT_STATUS':
      handleAgentStatusEvent(data);
      break;

    case 'TOOL_CALL':
      handleToolCallEvent(data);
      break;

    case 'TOKEN_USAGE':
      if (data.finops) updateFinOpsUI(data.finops);
      if (data.role && agents[data.role]) {
        const ag = agents[data.role];
        ag.tokens = (ag.tokens || 0) + (data.prompt_tokens || 0) + (data.completion_tokens || 0);
        if (selectedAgent && selectedAgent.role === data.role) {
          const inspTokens = document.getElementById('inspTokens');
          if (inspTokens) inspTokens.textContent = `${(ag.tokens || 0).toLocaleString()} t`;
        }
      }
      break;

    case 'LOOP_DETECTED':
      handleLoopDetectedEvent(data);
      break;

    case 'QUOTA_EXHAUSTED':
    case 'AGENT_EXHAUSTED':
      handleExhaustedEvent(data);
      break;

    case 'PROGRESS_UPDATE':
      updateProgressUI(data);
      break;

    case 'GATE_EVENT':
      updateGateUI(data);
      break;

    case 'CONTROL_CHANGE':
      if (data.state) updateControlUI(data.state);
      break;

    case 'LOG_OUTPUT':
      appendTerminalLine(data.line || '', data.style || 'term-info');
      break;

    default:
      break;
  }
}

async function fetchStatusSnapshot() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const snap = await res.json();
    if (snap.finops) updateFinOpsUI(snap.finops);
    if (snap.control) updateControlUI(snap.control);
    if (snap.progress) updateProgressUI(snap.progress);
  } catch (err) {}
}

function handleAgentStatusEvent(data) {
  const role = (data.role || 'dev').toLowerCase();
  const agent = agents[role];

  if (agent) {
    const isWorking = data.status === 'WORKING' || data.status === 'RUNNING' || data.status === 'THINKING' || data.status === 'CODING';
    if (isWorking) {
      agent.moveTo(agent.deskX, agent.deskY, 'WORKING');
      agent.currentAction = data.snippet || 'Analyzing task...';
      agent.say(data.speech || 'Working on task...', 200);
    } else if (data.status === 'IDLE' || data.status === 'DONE') {
      agent.moveTo(agent.idleX, agent.idleY, 'IDLE');
      agent.currentAction = 'Idle in lounge';
      agent.say('Task complete! Taking a break.', 180);
    }
  }

  // Count active agents
  const activeCount = Object.values(agents).filter((a) => a.state === 'WORKING').length;
  if (activeAgentsCount) {
    activeAgentsCount.textContent = `${activeCount} Agents Active`;
  }
}

function handleToolCallEvent(data) {
  const role = (data.role || 'dev').toLowerCase();
  const toolName = data.tool_name || 'tool';
  const summary = data.tool_summary || data.tool_action || 'Executing tool';
  const stepIdx = data.step_index || 0;

  appendTerminalLine(`[TOOL #${stepIdx}] ${role.toUpperCase()}: ${toolName} — ${summary}`, 'term-tool');

  const agent = agents[role];
  if (agent) {
    agent.moveTo(agent.deskX, agent.deskY, 'WORKING');
    agent.currentAction = `${toolName}: ${summary}`;
    agent.say(`${toolName}: ${summary}`, 240);
  }
}

function showAlertBanner(type, message, role, actionCallback, actionText = 'Action') {
  if (!alertContainer) return;
  const alertId = `alert_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`;
  const banner = document.createElement('div');
  banner.id = alertId;
  banner.className = `alert-banner ${type === 'loop' ? 'alert-loop' : 'alert-quota'}`;

  const icon = type === 'loop' ? '🔄' : '🛑';
  banner.innerHTML = `
    <div class="alert-content">
      <span class="alert-icon">${icon}</span>
      <span class="alert-text">${message}</span>
    </div>
    <div class="alert-actions">
      <button class="btn-alert-action" id="btn_${alertId}">${actionText}</button>
      <button class="btn-alert-close" onclick="document.getElementById('${alertId}')?.remove()">✕</button>
    </div>
  `;
  alertContainer.appendChild(banner);

  const actionBtn = document.getElementById(`btn_${alertId}`);
  if (actionBtn && actionCallback) {
    actionBtn.addEventListener('click', () => {
      actionCallback();
      banner.remove();
    });
  }

  // Auto dismiss after 30 seconds
  setTimeout(() => {
    const el = document.getElementById(alertId);
    if (el) el.remove();
  }, 30000);
}

function handleLoopDetectedEvent(data) {
  const role = (data.role || 'dev').toLowerCase();
  const agent = agents[role];
  const msg = data.message || `Agent ${role.toUpperCase()} is stuck in a loop!`;

  appendTerminalLine(`🚨 [LOOP DETECTED] ${msg}`, 'term-error');

  if (agent) {
    agent.state = 'LOOPING';
    agent.currentAction = `Stuck in loop: ${data.error_type || 'Repeating command'}`;
    agent.say('⚠️ ĐANG BỊ LOOP / STUCK! @_@', 300);
  }

  showAlertBanner('loop', msg, role, () => togglePauseAgent(role), '⏸ Pause Agent');
}

function handleExhaustedEvent(data) {
  const role = (data.role || 'dev').toLowerCase();
  const agent = agents[role];
  const msg = data.message || `Agent ${role.toUpperCase()} exhausted quota / overworked!`;

  appendTerminalLine(`🛑 [QUOTA EXHAUSTED] ${msg}`, 'term-error');

  if (agent) {
    agent.state = 'EXHAUSTED';
    agent.currentAction = `Exhausted: ${data.error_type || 'Quota depleted'}`;
    agent.say('⚠️ HẾT QUOTA / MỆT QUÁ! (x_x)', 350);
  }

  showAlertBanner('quota', msg, role, () => togglePauseAgent(role), '⏸ Pause Agent');
}

function updateFinOpsUI(finops) {
  if (!finops) return;

  const totalTokens = finops.total_tokens || 0;
  const totalCost = finops.total_cost_usd || 0.0;
  const burnRate = finops.burn_rate || {};
  const tokensPerSec = burnRate.tokens_per_sec || 0;
  const costPerMin = burnRate.cost_per_min || 0;
  const budget = finops.budget_status || {};

  if (topTotalTokens) topTotalTokens.textContent = totalTokens.toLocaleString();
  if (topTotalSpend) topTotalSpend.textContent = `$${totalCost.toFixed(4)}`;
  if (topBurnRate) topBurnRate.textContent = `${tokensPerSec} t/s`;

  if (finopsTotalCost) finopsTotalCost.textContent = `$${totalCost.toFixed(4)}`;
  if (finopsCostPerMin) finopsCostPerMin.textContent = `$${costPerMin.toFixed(4)} /min`;
  if (finopsBurnRate) finopsBurnRate.textContent = `${tokensPerSec}`;
  if (finopsCallCount) finopsCallCount.textContent = `${finops.total_calls || 0} Calls`;

  // Update budget badge
  if (budgetBadge && budgetText) {
    if (budget.status === 'HARD_LIMIT') {
      budgetBadge.style.borderColor = 'var(--accent-rose)';
      budgetBadge.style.color = 'var(--accent-rose)';
      budgetText.textContent = 'HARD LIMIT EXCEEDED';
    } else if (budget.status === 'ALERT') {
      budgetBadge.style.borderColor = 'var(--accent-amber)';
      budgetBadge.style.color = 'var(--accent-amber)';
      budgetText.textContent = 'BUDGET ALERT';
    } else {
      budgetBadge.style.borderColor = 'var(--border-color)';
      budgetBadge.style.color = 'var(--text-main)';
      budgetText.textContent = 'Budget Normal';
    }
  }

  // Update agent breakdown & character token data
  if (finops.breakdown_by_agent) {
    Object.entries(finops.breakdown_by_agent).forEach(([r, stats]) => {
      if (agents[r]) {
        agents[r].tokens = stats.total_tokens || 0;
        agents[r].cost = stats.cost_usd || 0.0;
        agents[r].calls = stats.call_count || 0;
      }
    });

    // Live update open inspector HUD
    if (selectedAgent && agents[selectedAgent.role]) {
      const liveAg = agents[selectedAgent.role];
      const inspTokens = document.getElementById('inspTokens');
      const inspCost = document.getElementById('inspCost');
      if (inspTokens) inspTokens.textContent = `${(liveAg.tokens || 0).toLocaleString()} t`;
      if (inspCost) inspCost.textContent = `$${(liveAg.cost || 0).toFixed(4)}`;
    }

    if (agentBreakdownList) {
      const items = Object.entries(finops.breakdown_by_agent);
      if (items.length > 0) {
        agentBreakdownList.innerHTML = items
          .map(([r, s]) => `
            <div class="breakdown-item">
              <span class="breakdown-item-name">${r.toUpperCase()}</span>
              <span>${(s.total_tokens || 0).toLocaleString()} t</span>
              <span class="breakdown-item-val">$${(s.cost_usd || 0).toFixed(4)}</span>
            </div>
          `)
          .join('');
      }
    }
  }

  // Model breakdown
  if (modelBreakdownList && finops.breakdown_by_model) {
    const models = Object.entries(finops.breakdown_by_model);
    if (models.length > 0) {
      modelBreakdownList.innerHTML = models
        .map(([m, s]) => `
          <div class="breakdown-item">
            <span class="breakdown-item-name">${m}</span>
            <span>${(s.total_tokens || 0).toLocaleString()} t</span>
            <span class="breakdown-item-val">$${(s.cost_usd || 0).toFixed(4)}</span>
          </div>
        `)
        .join('');
    }
  }
}

function updateControlUI(control) {
  if (!control) return;
  isGlobalPaused = control.global_state === 'PAUSED';
  pausedAgents = new Set((control.paused_agents || []).map((r) => r.toLowerCase()));

  if (btnGlobalPause) {
    btnGlobalPause.textContent = isGlobalPaused ? '▶️ Resume Entire Squad' : '⏸ Pause Entire Squad';
    btnGlobalPause.style.borderColor = isGlobalPaused ? 'var(--accent-amber)' : 'var(--border-color)';
  }

  const sysBadge = document.getElementById('systemStateBadge');
  if (sysBadge) {
    sysBadge.textContent = control.global_state;
    sysBadge.style.color = isGlobalPaused ? 'var(--accent-amber)' : 'var(--accent-emerald)';
  }

  if (control.gate_decision) {
    updateGateUI({ decision: control.gate_decision, notes: control.gate_notes });
  }
}

function updateGateUI(data) {
  const dec = (data.decision || 'PENDING').toUpperCase();
  if (gateDecisionBadge) {
    gateDecisionBadge.textContent = dec;
    gateDecisionBadge.className = 'gate-badge';
    if (dec === 'APPROVED') gateDecisionBadge.classList.add('approved');
    if (dec === 'REJECTED') gateDecisionBadge.classList.add('rejected');
  }
}

function updateProgressUI(progress) {
  if (!progress) return;
  const pct = progress.completion_percentage || 0;
  if (progressPercentage) progressPercentage.textContent = `${pct}%`;
  if (progressBarFill) progressBarFill.style.width = `${pct}%`;

  if (progressTaskList && progress.completed) {
    const tasks = progress.completed.slice(-5);
    progressTaskList.innerHTML = tasks.map((t) => `<div class="progress-task-item">✅ ${t}</div>`).join('');
  }
}

async function sendControlRequest(endpoint, body) {
  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Squad-Token': sessionToken,
      },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.state) updateControlUI(data.state);
    return data;
  } catch (err) {
    console.error('Control request error:', err);
  }
}

function togglePauseAgent(role) {
  const isPaused = pausedAgents.has(role.toLowerCase());
  const endpoint = isPaused ? '/api/control/resume' : '/api/control/pause';
  sendControlRequest(endpoint, { role });
  appendTerminalLine(`[CONTROL] Sent ${isPaused ? 'RESUME' : 'PAUSE'} for agent: ${role.toUpperCase()}`, 'term-system');
}

function toggleGlobalPause() {
  const endpoint = isGlobalPaused ? '/api/control/resume' : '/api/control/pause';
  sendControlRequest(endpoint, {});
  appendTerminalLine(`[CONTROL] ${isGlobalPaused ? 'Resuming' : 'Pausing'} entire squad.`, 'term-system');
}

function resumeAllAgents() {
  sendControlRequest('/api/control/resume', {});
  appendTerminalLine('[CONTROL] Resumed all squad agents.', 'term-system');
}

function emergencyStopAll() {
  if (confirm('Are you sure you want to EMERGENCY STOP all squad agents?')) {
    sendControlRequest('/api/control/kill', { role: 'all' });
    appendTerminalLine('🚨 [EMERGENCY STOP] All agents terminated by operator.', 'term-error');
  }
}

function submitGateDecision(decision) {
  sendControlRequest('/api/gate/decision', { decision, notes: `Operator action via Web Dashboard at ${new Date().toLocaleTimeString()}` });
  appendTerminalLine(`[GATE] Acceptance decision submitted: ${decision}`, 'term-agent');
}

function appendTerminalLine(text, styleClass = '') {
  if (!terminalWindow) return;
  const line = document.createElement('div');
  line.className = `term-line ${styleClass}`;
  const timestamp = new Date().toLocaleTimeString();
  line.textContent = `[${timestamp}] ${text}`;
  terminalWindow.appendChild(line);

  while (terminalWindow.children.length > 200) {
    terminalWindow.removeChild(terminalWindow.firstChild);
  }

  if (autoScroll) {
    terminalWindow.scrollTop = terminalWindow.scrollHeight;
  }
}

function updateUptimeTicker() {
  if (!serverUptime) return;
  const elapsedSec = Math.floor((Date.now() - serverStartTime) / 1000);
  const m = Math.floor(elapsedSec / 60);
  const s = elapsedSec % 60;
  serverUptime.textContent = `Uptime: ${m}m ${s}s`;
}

// Start
window.addEventListener('DOMContentLoaded', init);
