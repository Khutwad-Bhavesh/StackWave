// StackWave RFID Cloud OS · Frontend Controller & Edge Simulator
// Nexus Studio Dark Luxury Editorial Interactive Engine

class RFIDApp {
  constructor() {
    this.apiBase = window.location.origin.includes("5500") || window.location.protocol === "file:"
      ? "http://localhost:8000"
      : ""; // Same-origin when proxied via Nginx or served by FastAPI
    this.pollInterval = null;
    this.cachedEvents = [];
    this.readerKeys = {
      "CHECKOUT-01": "checkout-secret-key-9988",
      "RETURN-01": "return-secret-key-4455",
      "SHELF-CS-01": "shelf-secret-key-1122",
      "GATE-01": "gate-secret-key-7766"
    };

    this.init();
  }

  init() {
    this.setupCustomCursor();
    this.setupTabs();
    this.setupTopAlarmBanner();
    this.fetchAllData();

    // Start background telemetry polling every 2.5 seconds
    this.pollInterval = setInterval(() => {
      this.loadStats();
      this.loadEvents();
      this.loadAlerts();
    }, 2500);
  }

  // ---------------- Nexus Studio Interactive Magnetic Cursor ----------------
  setupCustomCursor() {
    const dot = document.getElementById("custom-cursor-dot");
    const ring = document.getElementById("custom-cursor-ring");
    if (!dot || !ring) return;

    let mouseX = -100;
    let mouseY = -100;
    let dotX = -100;
    let dotY = -100;
    let ringX = -100;
    let ringY = -100;

    window.addEventListener("mousemove", (e) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
    });

    const renderCursor = () => {
      // Spring lerp interpolation
      dotX += (mouseX - dotX) * 0.45;
      dotY += (mouseY - dotY) * 0.45;
      ringX += (mouseX - ringX) * 0.16;
      ringY += (mouseY - ringY) * 0.16;

      dot.style.transform = `translate3d(${dotX}px, ${dotY}px, 0) translate(-50%, -50%)`;
      ring.style.transform = `translate3d(${ringX}px, ${ringY}px, 0) translate(-50%, -50%)`;

      requestAnimationFrame(renderCursor);
    };
    requestAnimationFrame(renderCursor);

    // Dynamic hover targets with data-cursor="hover" or interactive elements
    document.addEventListener("mouseover", (e) => {
      const el = e.target.closest('[data-cursor="hover"], button, a, select, input, .bento-card');
      if (el) {
        dot.classList.add("cursor-hover");
        ring.classList.add("cursor-hover");
        dot.textContent = "CLICK";
      }
    });

    document.addEventListener("mouseout", (e) => {
      if (e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest('[data-cursor="hover"], button, a, select, input, .bento-card')) {
        return;
      }
      dot.classList.remove("cursor-hover");
      ring.classList.remove("cursor-hover");
      dot.textContent = "";
    });
  }

  // ---------------- Cryptographic HMAC-SHA256 Helper ----------------
  async computeHMAC(device_id, tag_uid, timestamp, nonce, secret_key) {
    const message = `${device_id}:${tag_uid}:${timestamp}:${nonce}`;
    const enc = new TextEncoder();
    const keyData = enc.encode(secret_key);
    const msgData = enc.encode(message);

    try {
      const cryptoKey = await window.crypto.subtle.importKey(
        "raw",
        keyData,
        { name: "HMAC", hash: "SHA-256" },
        false,
        ["sign"]
      );
      const sigBuffer = await window.crypto.subtle.sign("HMAC", cryptoKey, msgData);
      const hashArray = Array.from(new Uint8Array(sigBuffer));
      const hexSignature = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
      return hexSignature;
    } catch (err) {
      console.error("WebCrypto HMAC computation error:", err);
      return "0000000000000000000000000000000000000000000000000000000000000000";
    }
  }

  generateNonce() {
    if (window.crypto && window.crypto.randomUUID) {
      return window.crypto.randomUUID().replace(/-/g, '').substring(0, 16);
    }
    return Math.random().toString(36).substring(2, 18);
  }

  // ---------------- Virtual RFID Edge Terminal Scanner ----------------
  async simulateScan(tagUid, overrideReaderId = null, customNonce = null, customTimestamp = null, customSignature = null) {
    const readerSelect = document.getElementById("reader-select");
    if (overrideReaderId) {
      readerSelect.value = overrideReaderId;
    }
    const readerId = readerSelect.value;
    const secretKey = this.readerKeys[readerId] || "unknown-secret";

    const timestamp = customTimestamp !== null ? customTimestamp : Math.floor(Date.now() / 1000);
    const nonce = customNonce !== null ? customNonce : this.generateNonce();
    const signature = customSignature !== null
      ? customSignature
      : await this.computeHMAC(readerId, tagUid, timestamp, nonce, secretKey);

    const payload = {
      reader_id: readerId,
      tag_uid: tagUid,
      timestamp: timestamp,
      nonce: nonce,
      signature: signature
    };

    // Update real-time crypto inspector
    const inspector = document.getElementById("payload-inspector-code");
    const indicator = document.getElementById("sig-indicator");
    inspector.textContent = `// OUTGOING EDGE PAYLOAD (HTTPS POST /rfid/scan)\n` +
      JSON.stringify(payload, null, 2) + `\n\n// Awaiting backend verification...`;

    try {
      const resp = await fetch(`${this.apiBase}/rfid/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await resp.json();

      inspector.textContent = `// OUTGOING EDGE PAYLOAD (HTTPS POST /rfid/scan)\n` +
        JSON.stringify(payload, null, 2) +
        `\n\n// SERVER RESPONSE (${resp.status} ${resp.statusText}):\n` +
        JSON.stringify(data, null, 2);

      if (resp.status === 200) {
        indicator.textContent = "HMAC VERIFIED";
        indicator.className = "crypto-badge badge-valid";
        this.handleScanResult(data);
      } else {
        indicator.textContent = "REJECTED / 401";
        indicator.className = "crypto-badge badge-invalid";
        this.showToast(`Scan Rejected: ${data.detail || "Authentication Failed"}`, "danger");
      }

      // Refresh data tables
      this.fetchAllData();
    } catch (err) {
      console.error("Scan dispatch error:", err);
      inspector.textContent += `\n\n[Network Error]: ${err.message}`;
      this.showToast(`Network Error: Cannot reach cloud API`, "danger");
    }
  }

  handleScanResult(data) {
    if (data.status === "debounced") {
      this.showToast(`Debounced: ${data.message}`, "info");
    } else if (data.status === "alert") {
      this.showToast(`🚨 ${data.message}`, "danger");
      this.triggerTheftAlarmEffect(data.message);
    } else if (data.status === "rejected") {
      this.showToast(`⚠️ ${data.message}`, "warning");
    } else {
      this.showToast(`✅ ${data.message}`, "success");
    }
  }

  triggerTheftAlarmEffect(message) {
    const banner = document.getElementById("theft-alarm-banner");
    const msgSpan = document.getElementById("alarm-message");
    msgSpan.textContent = message;
    banner.classList.remove("hidden");

    // Synthetic audio alert chime via Web Audio API
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.setValueAtTime(440, ctx.currentTime + 0.15);
      osc.frequency.setValueAtTime(880, ctx.currentTime + 0.3);
      gain.gain.setValueAtTime(0.15, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.5);
    } catch (e) {
      // Audio autoplay policy fallback
    }
  }

  // ---------------- Special Verification Scenarios ----------------
  async triggerDebounceTest() {
    const tag = "TAG-BK-CLEAN-01";
    const readerId = "CHECKOUT-01";
    this.showToast("⚡ Rapid RF Burst Triggered (2 reads in 30ms)...", "info");

    // First scan
    this.simulateScan(tag, readerId);

    // Second scan immediately after 30ms
    setTimeout(() => {
      this.simulateScan(tag, readerId);
    }, 30);
  }

  async triggerReplayAttackTest() {
    const readerId = "CHECKOUT-01";
    const secretKey = this.readerKeys[readerId];
    const tag = "CARD-ALICE-001";
    const timestamp = Math.floor(Date.now() / 1000);
    const nonce = "replay-nonce-" + Math.floor(Math.random() * 10000);
    const sig = await this.computeHMAC(readerId, tag, timestamp, nonce, secretKey);

    this.showToast("🛡️ Phase 1: Emitting legitimate signed scan...", "info");
    await this.simulateScan(tag, readerId, nonce, timestamp, sig);

    setTimeout(async () => {
      this.showToast("🛡️ Phase 2: Injecting fraudulent replay packet with duplicated nonce...", "warning");
      await this.simulateScan(tag, readerId, nonce, timestamp, sig);
    }, 1200);
  }

  triggerCustomScan() {
    const input = document.getElementById("custom-tag-input");
    const val = input.value.trim();
    if (!val) {
      this.showToast("Please enter an RFID Tag or Card UID", "warning");
      return;
    }
    this.simulateScan(val);
    input.value = "";
  }

  // ---------------- Data Telemetry Fetchers ----------------
  async fetchAllData() {
    await Promise.all([
      this.loadStats(),
      this.loadEvents(),
      this.loadLoans(),
      this.loadTracking(),
      this.loadAlerts()
    ]);
  }

  async loadStats() {
    try {
      const resp = await fetch(`${this.apiBase}/stats`);
      if (!resp.ok) return;
      const data = await resp.json();

      document.getElementById("kpi-total-books").textContent = data.total_books;
      document.getElementById("kpi-total-copies").textContent = `${data.total_copies} physical copies (${data.copies_available} available)`;
      document.getElementById("kpi-checked-out").textContent = data.copies_checked_out;
      document.getElementById("kpi-active-loans").textContent = `${data.active_loans} active loans`;
      document.getElementById("kpi-overdue").textContent = data.overdue_loans;
      document.getElementById("kpi-scans-today").textContent = data.total_scans_today;
      document.getElementById("kpi-active-alerts").textContent = data.unresolved_alerts;

      const alertsCard = document.getElementById("kpi-alerts-card");
      const alertsTag = document.getElementById("kpi-alerts-tag");
      if (data.unresolved_alerts > 0) {
        alertsCard.classList.add("highlight-red");
        if (alertsTag) {
          alertsTag.textContent = "BREACH";
          alertsTag.className = "card-tag tag-ember";
        }
        document.getElementById("kpi-alerts-sub").textContent = "ATTENTION REQUIRED";
      } else {
        alertsCard.classList.remove("highlight-red");
        if (alertsTag) {
          alertsTag.textContent = "CLEAN";
          alertsTag.className = "card-tag";
        }
        document.getElementById("kpi-alerts-sub").textContent = "All gates clear";
      }

      this.renderFleet(data.reader_fleet);
    } catch (err) {
      console.warn("Could not load stats:", err);
    }
  }

  async loadEvents() {
    try {
      const resp = await fetch(`${this.apiBase}/events?limit=25`);
      if (!resp.ok) return;
      const events = await resp.json();
      this.cachedEvents = events;
      this.renderEvents();
    } catch (err) {
      console.warn("Could not load events:", err);
    }
  }

  renderEvents() {
    const filter = document.getElementById("event-reader-filter").value;
    const tbody = document.getElementById("events-table-body");
    const filtered = filter ? this.cachedEvents.filter(e => e.reader_id === filter) : this.cachedEvents;

    if (!filtered || filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="text-center py-8 text-mist-900 font-mono text-xs">No scan events recorded yet. Trigger a scenario on the left!</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map(e => {
      const timeStr = new Date(e.created_at).toLocaleTimeString();
      let badgeClass = "badge-info";
      if (e.result_status.includes("SUCCESS") || e.result_status === "SESSION_OPENED" || e.result_status === "AUTHORIZED_EXIT") {
        badgeClass = "badge-success";
      } else if (e.result_status.includes("ALERT") || e.result_status.includes("THEFT")) {
        badgeClass = "badge-danger";
      } else if (e.result_status.includes("BLOCKED") || e.result_status.includes("REPLAY")) {
        badgeClass = "badge-warning";
      } else if (e.result_status === "DEBOUNCED") {
        badgeClass = "badge-debounced";
      }

      return `
        <tr>
          <td class="font-mono text-xs text-mist-900">${timeStr}</td>
          <td><span class="mono-tag text-signal">${e.reader_id}</span></td>
          <td><span class="mono-tag font-bold">${e.tag_uid}</span></td>
          <td><span class="badge ${e.tag_type === 'MEMBER_CARD' ? 'badge-purple' : 'badge-info'}">${e.tag_type}</span></td>
          <td>
            <span class="badge ${badgeClass}">${e.result_status}</span>
            <div style="font-size: 0.72rem; color: var(--mist-900); margin-top: 2px;">${e.action_detail || ''}</div>
          </td>
          <td>
            <span class="badge ${e.signature_valid ? 'badge-success' : 'badge-danger'}">
              ${e.signature_valid ? '✓ HMAC-OK' : '✗ TAMPERED'}
            </span>
          </td>
        </tr>
      `;
    }).join('');
  }

  async loadLoans() {
    try {
      const resp = await fetch(`${this.apiBase}/loans`);
      if (!resp.ok) return;
      const loans = await resp.json();

      document.getElementById("loans-tab-count").textContent = loans.filter(l => l.status === "ACTIVE").length;
      const tbody = document.getElementById("loans-table-body");

      if (!loans || loans.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-center py-8 text-mist-900 font-mono text-xs">No active loans in database.</td></tr>`;
        return;
      }

      const now = new Date();
      tbody.innerHTML = loans.map(l => {
        const dueDate = new Date(l.due_date);
        const isOverdue = l.status === "ACTIVE" && dueDate < now;
        const statusBadge = isOverdue
          ? `<span class="badge badge-danger">OVERDUE</span>`
          : (l.status === "ACTIVE" ? `<span class="badge badge-success">ACTIVE</span>` : `<span class="badge badge-info">RETURNED</span>`);

        const canRenew = l.status === "ACTIVE" && !isOverdue && l.renewal_count < 1;

        return `
          <tr>
            <td class="font-mono text-xs text-mist-900">#${l.id}</td>
            <td><strong>${l.book_title || 'N/A'}</strong></td>
            <td><span class="mono-tag text-signal">${l.tag_uid || 'N/A'}</span></td>
            <td>${l.member_name || 'N/A'}</td>
            <td class="font-mono text-xs text-mist-900">${new Date(l.checkout_at).toLocaleDateString()}</td>
            <td class="font-mono text-xs" style="${isOverdue ? 'color: #f87171; font-weight: 700;' : 'color: var(--mist-700);'}">${dueDate.toLocaleDateString()}</td>
            <td>${statusBadge}</td>
            <td class="font-mono text-xs">${l.renewal_count}/1</td>
            <td>
              ${canRenew
                ? `<button class="btn-sm btn-renew" onclick="app.renewLoan(${l.id})" data-cursor="hover">Renew (+14d)</button>`
                : `<span class="font-mono text-xs text-mist-900">${l.renewal_count >= 1 ? 'Limit Met' : (isOverdue ? 'Blocked: Overdue' : 'Completed')}</span>`
              }
            </td>
          </tr>
        `;
      }).join('');
    } catch (err) {
      console.warn("Could not load loans:", err);
    }
  }

  async renewLoan(loanId) {
    try {
      const resp = await fetch(`${this.apiBase}/loans/${loanId}/renew`, { method: "POST" });
      const data = await resp.json();
      if (resp.ok) {
        this.showToast(`Renewed: ${data.message}`, "success");
      } else {
        this.showToast(`Renewal Blocked: ${data.detail}`, "warning");
      }
      this.loadLoans();
      this.loadStats();
    } catch (err) {
      this.showToast(`Network error renewing loan`, "danger");
    }
  }

  async loadTracking() {
    try {
      const resp = await fetch(`${this.apiBase}/tracking`);
      if (!resp.ok) return;
      const items = await resp.json();

      const tbody = document.getElementById("tracking-table-body");
      if (!items || items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-mist-900 font-mono text-xs">No catalog copies tracked.</td></tr>`;
        return;
      }

      tbody.innerHTML = items.map(c => {
        let statusBadge = "badge-success";
        if (c.status === "CHECKED_OUT") statusBadge = "badge-info";
        else if (c.status === "LOST") statusBadge = "badge-danger";

        const lastSeen = c.last_seen_at ? new Date(c.last_seen_at).toLocaleTimeString() : 'Never';

        return `
          <tr>
            <td><strong>${c.book_title}</strong></td>
            <td><span class="mono-tag text-signal">${c.tag_uid}</span></td>
            <td><span class="badge ${statusBadge}">${c.status}</span></td>
            <td><span class="font-mono text-xs">📍 ${c.shelf_location}</span></td>
            <td><span class="mono-tag">${c.last_seen_reader_id || 'N/A'}</span></td>
            <td class="font-mono text-xs text-mist-900">${lastSeen}</td>
            <td>${c.current_borrower || '<span class="text-mist-900 font-mono text-xs">On Shelf</span>'}</td>
          </tr>
        `;
      }).join('');
    } catch (err) {
      console.warn("Could not load tracking:", err);
    }
  }

  async loadAlerts() {
    try {
      const resp = await fetch(`${this.apiBase}/alerts?unresolved_only=false`);
      if (!resp.ok) return;
      const alerts = await resp.json();

      const unresolvedCount = alerts.filter(a => !a.resolved).length;
      document.getElementById("alerts-tab-count").textContent = unresolvedCount;

      const activeCritical = alerts.find(a => !a.resolved && a.severity === "CRITICAL");
      const topBanner = document.getElementById("theft-alarm-banner");
      if (activeCritical) {
        topBanner.classList.remove("hidden");
        document.getElementById("alarm-message").textContent = activeCritical.message;
      } else {
        topBanner.classList.add("hidden");
      }

      const tbody = document.getElementById("alerts-table-body");
      if (!alerts || alerts.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-8 text-mist-900 font-mono text-xs">Zero security incidents recorded.</td></tr>`;
        return;
      }

      tbody.innerHTML = alerts.map(a => {
        const severityBadge = a.severity === "CRITICAL"
          ? `<span class="badge badge-danger">CRITICAL</span>`
          : `<span class="badge badge-warning">${a.severity}</span>`;

        return `
          <tr>
            <td>${severityBadge}</td>
            <td><strong>${a.alert_type}</strong></td>
            <td style="color: #fca5a5;">${a.message}</td>
            <td><span class="mono-tag text-signal">${a.reader_id || 'N/A'}</span></td>
            <td class="font-mono text-xs text-mist-900">${new Date(a.created_at).toLocaleTimeString()}</td>
            <td>
              <span class="badge ${a.resolved ? 'badge-success' : 'badge-danger'}">
                ${a.resolved ? 'RESOLVED' : 'ACTIVE'}
              </span>
            </td>
            <td>
              ${!a.resolved
                ? `<button class="btn-sm btn-action-resolve" onclick="app.resolveAlert(${a.id})" data-cursor="hover">Acknowledge</button>`
                : `<span class="font-mono text-xs text-mist-900">By ${a.resolved_by || 'Staff'}</span>`
              }
            </td>
          </tr>
        `;
      }).join('');
    } catch (err) {
      console.warn("Could not load alerts:", err);
    }
  }

  async resolveAlert(alertId) {
    try {
      const resp = await fetch(`${this.apiBase}/alerts/${alertId}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resolved_by: "Security_Desk" })
      });
      if (resp.ok) {
        this.showToast("Incident acknowledged & resolved.", "success");
        this.loadAlerts();
        this.loadStats();
      }
    } catch (err) {
      this.showToast("Failed to resolve alert", "danger");
    }
  }

  renderFleet(fleet) {
    const container = document.getElementById("fleet-cards-container");
    if (!container || !fleet) return;

    container.innerHTML = fleet.map(r => `
      <div class="fleet-card" data-cursor="hover">
        <div class="fleet-card-header">
          <span class="fleet-device-id">${r.device_id}</span>
          <span class="badge ${r.is_online ? 'badge-success' : 'badge-warning'}">
            ${r.is_online ? 'ONLINE' : 'ACTIVE'}
          </span>
        </div>
        <div class="fleet-card-name">${r.name}</div>
        <div class="fleet-meta">
          <span>Role: <strong>${r.type}</strong></span>
          <span>Location: <strong>${r.location}</strong></span>
          <span>Total Ingested Reads: <strong>${r.total_scans}</strong></span>
          <span>Security: <strong class="text-signal">HMAC-SHA256</strong></span>
        </div>
      </div>
    `).join('');
  }

  // ---------------- UI Helpers ----------------
  setupTabs() {
    const tabButtons = document.querySelectorAll(".tab-link");
    tabButtons.forEach(btn => {
      btn.addEventListener("click", () => {
        tabButtons.forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-panel").forEach(tc => tc.classList.remove("active"));

        btn.classList.add("active");
        const target = btn.getAttribute("data-tab");
        const contentEl = document.getElementById(`tab-${target}`);
        if (contentEl) contentEl.classList.add("active");
      });
    });
  }

  setupTopAlarmBanner() {
    const btn = document.getElementById("btn-resolve-top-alarm");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const resp = await fetch(`${this.apiBase}/alerts?unresolved_only=true`);
      if (resp.ok) {
        const alerts = await resp.json();
        for (const a of alerts) {
          await this.resolveAlert(a.id);
        }
      }
      document.getElementById("theft-alarm-banner").classList.add("hidden");
    });
  }

  showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;

    let icon = "ℹ️";
    if (type === "success") icon = "✅";
    else if (type === "warning") icon = "⚠️";
    else if (type === "danger") icon = "🚨";

    toast.innerHTML = `<span>${icon}</span><div>${message}</div>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(100%)";
      setTimeout(() => toast.remove(), 300);
    }, 4500);
  }
}

// Instantiate on DOM ready
let app;
window.addEventListener("DOMContentLoaded", () => {
  app = new RFIDApp();
});
