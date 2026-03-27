/**
 * Duox Intercom Card — Custom Lovelace card for Fermax Duox live video
 * and bidirectional audio via mediasoup WebRTC.
 *
 * Dependencies loaded from CDN:
 *   - mediasoup-client v3 (browser WebRTC)
 *   - socket.io-client v4 (signaling transport)
 */

const CARD_VERSION = "0.3.0";
const PROTOCOL_VERSION = "0.8.2";

const MS_CDN = "https://esm.sh/mediasoup-client@3?bundle";
const SIO_CDN = "https://esm.sh/socket.io-client@4?bundle";

/* ------------------------------------------------------------------ */
/* CDN loader                                                          */
/* ------------------------------------------------------------------ */

let _mediasoupClient = null;
let _io = null;

async function loadDeps() {
  if (_mediasoupClient && _io) return;
  const [ms, sio] = await Promise.all([
    import(MS_CDN),
    import(SIO_CDN),
  ]);
  _mediasoupClient = ms;
  _io = sio.io || sio.default?.io;
}

function safeParse(val) {
  if (val == null) return val;
  if (typeof val === "object") return val;
  try { return JSON.parse(val); } catch (_) { return val; }
}

/* ------------------------------------------------------------------ */
/* SVG Icons (22x22 viewBox)                                           */
/* ------------------------------------------------------------------ */

const ICONS = {
  video: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"/></svg>`,
  mic: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1-9c0-.55.45-1 1-1s1 .45 1 1v6c0 .55-.45 1-1 1s-1-.45-1-1V5z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>`,
  micOff: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 11h-1.7c0 .74-.16 1.43-.43 2.05l1.23 1.23c.56-.98.9-2.09.9-3.28zm-4.02.17c0-.06.02-.11.02-.17V5c0-1.66-1.34-3-3-3S9 3.34 9 5v.18l5.98 5.99zM4.27 3L3 4.27l6.01 6.01V11c0 1.66 1.33 3 2.99 3 .22 0 .44-.03.65-.08l1.66 1.66c-.71.33-1.5.52-2.31.52-2.76 0-5.3-2.1-5.3-5.1H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c.91-.13 1.77-.45 2.54-.9L19.73 21 21 19.73 4.27 3z"/></svg>`,
  phoneHangup: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 9c-1.6 0-3.15.25-4.6.72v3.1c0 .39-.23.74-.56.9-.98.49-1.87 1.12-2.66 1.85-.18.18-.43.28-.7.28-.28 0-.53-.11-.71-.29L.29 13.08a.956.956 0 0 1 0-1.36C3.53 8.46 7.56 6.5 12 6.5s8.47 1.96 11.71 5.22c.18.18.29.43.29.71 0 .28-.11.53-.29.71l-2.48 2.48c-.18.18-.43.29-.71.29-.27 0-.52-.1-.7-.28-.79-.73-1.68-1.36-2.66-1.85a.996.996 0 0 1-.56-.9v-3.1C15.15 9.25 13.6 9 12 9z"/></svg>`,
  lockOpen: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 17c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm6-9h-1V6c0-2.76-2.24-5-5-5-2.28 0-4.27 1.54-4.84 3.75-.14.54.18 1.08.72 1.22.53.14 1.08-.18 1.22-.72C9.44 3.93 10.63 3 12 3c1.65 0 3 1.35 3 3v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm0 12H6V10h12v10z"/></svg>`,
  history: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z"/></svg>`,
  phoneIn: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M20 15.5c-1.25 0-2.45-.2-3.57-.57a1.02 1.02 0 0 0-1.02.24l-2.2 2.2a15.045 15.045 0 0 1-6.59-6.59l2.2-2.21a.96.96 0 0 0 .25-1A11.36 11.36 0 0 1 8.5 4c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1 0 9.39 7.61 17 17 17 .55 0 1-.45 1-1v-3.5c0-.55-.45-1-1-1z"/></svg>`,
  phoneMissed: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6.5 5.5L12 11l7-7-1.41-1.41L12 8.17 6.91 3.09 5.5 4.5 6.5 5.5z"/><path d="M20 15.5c-1.25 0-2.45-.2-3.57-.57a1.02 1.02 0 0 0-1.02.24l-2.2 2.2a15.045 15.045 0 0 1-6.59-6.59l2.2-2.21a.96.96 0 0 0 .25-1A11.36 11.36 0 0 1 8.5 4c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1 0 9.39 7.61 17 17 17 .55 0 1-.45 1-1v-3.5c0-.55-.45-1-1-1z"/></svg>`,
  autoOn: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"/></svg>`,
  check: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/></svg>`,
};

function wifiIcon(level) {
  const on = "currentColor";
  const off = "currentColor\" opacity=\".15";
  return `<svg viewBox="0 0 24 24" fill="none" stroke-width="0">
    <circle cx="12" cy="19" r="1.5" fill="${level >= 1 ? on : off}"/>
    <path d="M8.7 15.7a4.7 4.7 0 0 1 6.6 0" stroke="${level >= 2 ? on : off}" stroke-width="2" fill="none" stroke-linecap="round"/>
    <path d="M5.6 12.6a9.2 9.2 0 0 1 12.8 0" stroke="${level >= 3 ? on : off}" stroke-width="2" fill="none" stroke-linecap="round"/>
    <path d="M2.5 9.5a13.8 13.8 0 0 1 19 0" stroke="${level >= 4 ? on : off}" stroke-width="2" fill="none" stroke-linecap="round"/>
  </svg>`;
}

const WIFI_MAP = { terrible: 1, bad: 1, weak: 2, good: 3, excellent: 4, unknown: 0 };
const WIFI_COLORS = { terrible: "#f44336", bad: "#f44336", weak: "#FF9800", good: "#4CAF50", excellent: "#4CAF50", unknown: "#888" };

/* ------------------------------------------------------------------ */
/* Card                                                                */
/* ------------------------------------------------------------------ */

class DuoxIntercomCard extends HTMLElement {
  /* -- Lovelace lifecycle ------------------------------------------ */

  setConfig(config) {
    this._config = config;
    this._entryId = config.entry_id || "";
    this._cameraEntity = config.camera_entity || "";
    this._lockEntity = config.lock_entity || "";
    this._wifiEntity = config.wifi_entity || "";
    this._deviceName = config.device_name || "Doorbell";
    this._hass = null;
    this._state = "idle";
    this._socket = null;
    this._device = null;
    this._recvVideoTransport = null;
    this._recvAudioTransport = null;
    this._sendTransport = null;
    this._videoConsumer = null;
    this._audioConsumer = null;
    this._micProducer = null;
    this._callData = null;
    this._callAudioConsumer = null;
    this._error = null;
    this._videoStream = null;
    this._audioStream = null;
    this._sheetOpen = false;
    this._callHistory = null;
    this._historyLoading = false;
    this._thumbCache = {};
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    this._render();
  }

  set hass(hass) {
    const prev = this._hass;
    this._hass = hass;

    if (!prev && this._state === "idle") {
      const url = new URL(window.location.href);
      if (url.searchParams.get("autoconnect") === "1") {
        url.searchParams.delete("autoconnect");
        window.history.replaceState(null, "", url.toString());
        setTimeout(() => this._connect(), 500);
      }
      setTimeout(() => this._loadHistory(), 100);
    }

    if (this._wifiEntity && prev) {
      const oldWifi = prev.states[this._wifiEntity];
      const newWifi = hass.states[this._wifiEntity];
      if (oldWifi?.state !== newWifi?.state) {
        this._updateWifiIcon();
      }
    }

    if (this._state === "idle" && this._cameraEntity) {
      const stateObj = hass.states?.[this._cameraEntity];
      const entityPic = stateObj?.attributes?.entity_picture;
      if (entityPic) {
        const img = this.shadowRoot?.querySelector(".video-wrap img");
        if (img && img.dataset.src !== entityPic) {
          img.src = entityPic;
          img.dataset.src = entityPic;
        } else if (!img && this.shadowRoot) {
          this._render();
        }
      }
    }
  }

  /* -- CSS --------------------------------------------------------- */

  _css() {
    return `
      * { box-sizing: border-box; margin: 0; padding: 0; }
      :host { display: block; }
      :host::before, :host::after { display: none !important; }

      .card {
        background: var(--ha-card-background, var(--card-background-color, #fff));
        border-radius: var(--ha-card-border-radius, 12px);
        box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.15));
        overflow: hidden;
        position: relative;
        font-family: var(--primary-font-family, Roboto, sans-serif);
      }

      /* -- Video / snapshot area ----------------------------------- */
      .video-wrap {
        position: relative;
        width: 100%;
        background: #111;
        aspect-ratio: 16/9;
      }
      .video-wrap video, .video-wrap img {
        width: 100%; height: 100%; object-fit: contain; display: block;
      }
      .snapshot-badge {
        position: absolute; bottom: 0; left: 0; right: 0;
        background: rgba(0,0,0,.55);
        color: #fff; font-size: 11px; padding: 4px 10px;
        text-align: center; pointer-events: none;
        letter-spacing: .3px;
      }

      /* -- WiFi indicator ------------------------------------------ */
      .wifi-indicator {
        position: absolute; top: 8px; right: 8px;
        width: 34px; height: 34px;
        border-radius: 50%;
        background: rgba(0,0,0,.5);
        display: flex; align-items: center; justify-content: center;
        z-index: 2;
      }
      .wifi-indicator svg { width: 22px; height: 22px; }

      /* -- Controls bar -------------------------------------------- */
      .controls {
        display: flex; gap: 10px; padding: 12px 16px;
        justify-content: center; align-items: center;
      }

      /* -- Icon buttons (Midea-style circular) --------------------- */
      .ibtn {
        width: 44px; height: 44px; border-radius: 50%;
        border: 2px solid; padding: 0;
        display: flex; align-items: center; justify-content: center;
        cursor: pointer; background: transparent;
        transition: filter .15s, opacity .15s;
        flex-shrink: 0;
        -webkit-user-select: none; user-select: none;
      }
      .ibtn:hover { filter: brightness(1.15); }
      .ibtn:active { filter: brightness(.9); }
      .ibtn:disabled { opacity: .35; cursor: default; pointer-events: none; }
      .ibtn svg { width: 22px; height: 22px; pointer-events: none; }

      .ibtn-connect  { border-color: #4CAF50; color: #4CAF50; }
      .ibtn-talk     { border-color: #2196F3; color: #2196F3; }
      .ibtn-mute     { border-color: #FF9800; color: #FF9800; }
      .ibtn-hangup   { border-color: #f44336; color: #f44336; background: #f44336; }
      .ibtn-hangup svg { color: #fff; }
      .ibtn-unlock   { border-color: #9C27B0; color: #9C27B0; }

      /* -- Status bar ---------------------------------------------- */
      .status {
        text-align: center; padding: 4px 12px 10px;
        font-size: 11px; color: var(--secondary-text-color, #888);
      }
      .status:empty { display: none; }
      .status.error { color: #f44336; }

      /* -- Call history (inline) ------------------------------------ */
      .call-history {
        border-top: 1px solid var(--divider-color, #eee);
      }
      .hist-header {
        display: flex; align-items: center; justify-content: space-between;
        padding: 10px 16px 6px;
        font-size: 13px; font-weight: 600;
        color: var(--primary-text-color, #333);
      }
      .hist-header .hist-refresh {
        background: none; border: none; cursor: pointer; padding: 4px;
        color: var(--secondary-text-color, #888);
        display: flex; align-items: center; justify-content: center;
        border-radius: 50%; transition: background .15s;
      }
      .hist-header .hist-refresh:hover { background: var(--secondary-background-color, rgba(0,0,0,.04)); }
      .hist-header .hist-refresh svg { width: 18px; height: 18px; }
      .hist-list { padding: 0 12px 12px; }
      .hist-row {
        display: flex; align-items: center; gap: 10px;
        padding: 8px 4px;
        border-bottom: 1px solid var(--divider-color, #eee);
        cursor: pointer; border-radius: 8px;
        transition: background .15s;
      }
      .hist-row:hover { background: var(--secondary-background-color, rgba(0,0,0,.04)); }
      .hist-row:last-child { border-bottom: none; }
      .hist-ico {
        width: 32px; height: 32px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        flex-shrink: 0;
      }
      .hist-ico svg { width: 18px; height: 18px; }
      .hist-ico.picked { background: #E8F5E9; color: #4CAF50; }
      .hist-ico.missed { background: #FFEBEE; color: #f44336; }
      .hist-ico.autoon { background: #E3F2FD; color: #2196F3; }
      .hist-ico.unknown { background: #F5F5F5; color: #888; }
      .hist-info { flex: 1; min-width: 0; }
      .hist-name {
        font-size: 13px; font-weight: 500;
        color: var(--primary-text-color, #333);
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      .hist-time {
        font-size: 11px; color: var(--secondary-text-color, #888);
      }
      .hist-thumb {
        width: 48px; height: 36px; border-radius: 4px;
        object-fit: cover; flex-shrink: 0;
        background: var(--secondary-background-color, #f0f0f0);
      }
      .hist-thumb-placeholder {
        width: 48px; height: 36px; border-radius: 4px; flex-shrink: 0;
        background: var(--secondary-background-color, #f0f0f0);
      }
      .hist-empty, .hist-loading {
        text-align: center; padding: 24px 0;
        font-size: 13px; color: var(--secondary-text-color, #888);
      }

      /* -- Photo viewer overlay ------------------------------------- */
      .photo-viewer {
        position: absolute; inset: 0; z-index: 10;
        background: rgba(0,0,0,.85);
        display: flex; flex-direction: column;
        align-items: center; justify-content: center;
        cursor: pointer;
      }
      .photo-viewer img {
        max-width: 100%; max-height: 90%;
        object-fit: contain; border-radius: 4px;
      }
      .photo-viewer .pv-close {
        position: absolute; top: 8px; right: 8px;
        color: #fff; background: rgba(255,255,255,.15);
        border: none; border-radius: 50%; width: 32px; height: 32px;
        font-size: 18px; cursor: pointer;
        display: flex; align-items: center; justify-content: center;
      }

      @keyframes spin { to { transform: rotate(360deg); } }
      .spinner {
        display: inline-block; width: 20px; height: 20px;
        border: 2px solid var(--divider-color, #ccc);
        border-top-color: var(--primary-text-color, #333);
        border-radius: 50%;
        animation: spin .6s linear infinite;
      }
    `;
  }

  /* -- Render ------------------------------------------------------ */

  _render() {
    const S = this._state;
    const err = this._error || "";
    const camState = this._hass?.states?.[this._cameraEntity];
    const cam = camState?.attributes?.entity_picture || "";
    const wifiState = this._hass?.states?.[this._wifiEntity]?.state || "unknown";
    const wifiLvl = WIFI_MAP[wifiState] ?? 0;
    const wifiClr = WIFI_COLORS[wifiState] || "#888";

    this.shadowRoot.innerHTML = `
      <style>${this._css()}</style>
      <ha-card>
        <div class="card">

          <div class="video-wrap" id="vw">
            ${S === "idle" && cam
              ? `<img src="${cam}" alt="Snapshot"/>
                 <div class="snapshot-badge">Last snapshot</div>`
              : `<video id="vid" autoplay playsinline muted></video>`}
            ${this._wifiEntity
              ? `<div class="wifi-indicator" id="wifiIco" style="color:${wifiClr}"
                      title="WiFi: ${wifiState}">${wifiIcon(wifiLvl)}</div>`
              : ""}
          </div>

          <div class="controls">
            ${S === "idle" ? `
              <button class="ibtn ibtn-connect" id="btnConnect" title="Connect">${ICONS.video}</button>
            ` : ""}
            ${S === "preview" ? `
              <button class="ibtn ibtn-talk" id="btnTalk" title="Talk">${ICONS.mic}</button>
              <button class="ibtn ibtn-hangup" id="btnHangup" title="Hang up">${ICONS.phoneHangup}</button>
            ` : ""}
            ${S === "call" ? `
              <button class="ibtn ibtn-mute" id="btnMute" title="Mute">${ICONS.mic}</button>
              <button class="ibtn ibtn-hangup" id="btnHangup" title="Hang up">${ICONS.phoneHangup}</button>
            ` : ""}
            ${S === "connecting" ? `
              <button class="ibtn ibtn-hangup" id="btnHangup" title="Cancel">${ICONS.phoneHangup}</button>
            ` : ""}
            ${this._lockEntity && S !== "connecting" ? `
              <button class="ibtn ibtn-unlock" id="btnUnlock" title="Open gate">${ICONS.lockOpen}</button>
            ` : ""}
          </div>

          <div class="status${S === "error" ? " error" : ""}" id="status">
            ${S === "connecting" ? "Connecting\u2026"
              : S === "error" ? err
              : ""}
          </div>

          <div class="call-history">
            <div class="hist-header">
              <span>Call History</span>
              <button class="hist-refresh" id="btnRefreshHist" title="Refresh">${ICONS.history}</button>
            </div>
            <div class="hist-list" id="histList"></div>
          </div>

        </div>
      </ha-card>
    `;

    this._bindButtons();
    this._attachStreams();
    this._renderHistory();
  }

  _attachStreams() {
    const vid = this.shadowRoot.getElementById("vid");
    if (vid && this._videoStream) {
      vid.srcObject = this._videoStream;
      vid.play().catch(() => {});
    }
  }

  _updateWifiIcon() {
    const el = this.shadowRoot?.getElementById("wifiIco");
    if (!el) return;
    const s = this._hass?.states?.[this._wifiEntity]?.state || "unknown";
    el.style.color = WIFI_COLORS[s] || "#888";
    el.title = `WiFi: ${s}`;
    el.innerHTML = wifiIcon(WIFI_MAP[s] ?? 0);
  }

  _bindButtons() {
    const $ = (id) => this.shadowRoot.getElementById(id);
    $("btnConnect")?.addEventListener("click", () => this._connect());
    $("btnTalk")?.addEventListener("click", () => this._pickup());
    $("btnMute")?.addEventListener("click", () => this._toggleMute());
    $("btnHangup")?.addEventListener("click", () => this._hangup());
    $("btnUnlock")?.addEventListener("click", () => this._unlock());
    $("btnRefreshHist")?.addEventListener("click", () => this._loadHistory());
  }

  _setState(s, err) {
    this._state = s;
    this._error = err || null;
    this._render();
  }

  /* -- Inline call history ----------------------------------------- */

  async _loadHistory() {
    this._historyLoading = true;
    this._callHistory = null;
    this._renderHistory();

    try {
      const result = await this._hass.callWS({
        type: "duox/call_history",
        entry_id: this._entryId,
      });
      this._callHistory = result || [];
    } catch (e) {
      console.error("[duox-intercom] call_history error:", e);
      this._callHistory = [];
    }
    this._historyLoading = false;
    this._renderHistory();
    this._loadThumbnails();
  }

  _renderHistory() {
    const list = this.shadowRoot.getElementById("histList");
    if (!list) return;

    if (this._historyLoading) {
      list.innerHTML = `<div class="hist-loading"><div class="spinner"></div></div>`;
      return;
    }

    const items = this._callHistory;
    if (!items || items.length === 0) {
      list.innerHTML = items === null
        ? `<div class="hist-empty" style="cursor:pointer" id="histLoadPrompt">Tap to load</div>`
        : `<div class="hist-empty">No call history</div>`;
      list.querySelector("#histLoadPrompt")?.addEventListener("click", () => this._loadHistory());
      return;
    }

    list.innerHTML = items.map((e, i) => {
      const state = (e.registerCall || "U").toUpperCase();
      const isAutoon = e.isAutoon === true || e.isAutoon === "true";
      let cssClass, icon;
      if (isAutoon) {
        cssClass = "autoon";
        icon = ICONS.autoOn;
      } else if (state === "P") {
        cssClass = "picked";
        icon = ICONS.phoneIn;
      } else if (state === "M") {
        cssClass = "missed";
        icon = ICONS.phoneMissed;
      } else {
        cssClass = "unknown";
        icon = ICONS.phoneIn;
      }
      const name = e.name || this._deviceName;
      const ts = e.callDate ? this._fmtTime(e.callDate) : "";
      const hasPhoto = !!e.photoId;
      return `<div class="hist-row" data-idx="${i}" ${hasPhoto ? 'data-photo="' + e.photoId + '"' : ""}>
        <div class="hist-ico ${cssClass}">${icon}</div>
        <div class="hist-info">
          <div class="hist-name">${name}</div>
          <div class="hist-time">${ts}</div>
        </div>
        ${hasPhoto
          ? `<div class="hist-thumb-placeholder" data-thumb="${e.photoId}"></div>`
          : ""}
      </div>`;
    }).join("");

    list.querySelectorAll(".hist-row[data-photo]").forEach(row => {
      row.addEventListener("click", () => {
        const photoId = row.getAttribute("data-photo");
        if (photoId) this._showPhoto(photoId);
      });
    });
  }

  async _loadThumbnails() {
    const items = this._callHistory;
    if (!items) return;
    const seen = this._thumbCache || {};
    this._thumbCache = seen;

    for (const entry of items) {
      if (!entry.photoId || seen[entry.photoId]) {
        if (seen[entry.photoId]) this._setThumb(entry.photoId, seen[entry.photoId]);
        continue;
      }
      try {
        const result = await this._hass.callWS({
          type: "duox/call_photo",
          entry_id: this._entryId,
          photo_id: entry.photoId,
        });
        if (result?.image_b64) {
          const src = `data:image/jpeg;base64,${result.image_b64}`;
          seen[entry.photoId] = src;
          this._setThumb(entry.photoId, src);
        }
      } catch (_) {}
    }
  }

  _setThumb(photoId, src) {
    const el = this.shadowRoot?.querySelector(`[data-thumb="${photoId}"]`);
    if (el && el.tagName !== "IMG") {
      const img = document.createElement("img");
      img.className = "hist-thumb";
      img.src = src;
      img.alt = "";
      el.replaceWith(img);
      img.dataset.thumb = photoId;
    }
  }

  async _showPhoto(photoId) {
    const cached = this._thumbCache?.[photoId];
    const vw = this.shadowRoot.getElementById("vw");
    if (!vw) return;

    vw.querySelector(".photo-viewer")?.remove();

    const viewer = document.createElement("div");
    viewer.className = "photo-viewer";
    viewer.innerHTML = `<button class="pv-close">\u00d7</button>${
      cached
        ? `<img src="${cached}" alt="Call photo"/>`
        : `<div class="spinner"></div>`
    }`;
    vw.appendChild(viewer);

    viewer.addEventListener("click", () => viewer.remove());

    if (!cached) {
      try {
        const result = await this._hass.callWS({
          type: "duox/call_photo",
          entry_id: this._entryId,
          photo_id: photoId,
        });
        if (result?.image_b64) {
          const src = `data:image/jpeg;base64,${result.image_b64}`;
          this._thumbCache = this._thumbCache || {};
          this._thumbCache[photoId] = src;
          viewer.innerHTML = `<button class="pv-close">\u00d7</button><img src="${src}" alt="Call photo"/>`;
          viewer.addEventListener("click", () => viewer.remove());
        } else {
          viewer.remove();
        }
      } catch (_) {
        viewer.remove();
      }
    }
  }

  _fmtTime(timestamp) {
    try {
      const d = new Date(typeof timestamp === "number" ? timestamp : parseInt(timestamp, 10));
      const now = Date.now();
      const diff = now - d.getTime();
      if (diff < 60000) return "Just now";
      if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
      const time = d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
      if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago · ${time}`;
      if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago · ${time}`;
      return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + ` · ${time}`;
    } catch (_) { return ""; }
  }

  /* -- Connect flow ------------------------------------------------ */

  async _connect() {
    try {
      this._setState("connecting");

      await loadDeps();

      let callInfo = await this._getActiveCall();

      if (!callInfo) {
        console.debug("[duox-intercom] No active call, triggering autoon...");
        callInfo = await this._triggerAutoon();
      }

      if (!callInfo) {
        this._setState("error", "Could not start call");
        return;
      }

      this._callData = callInfo;
      console.debug("[duox-intercom] call info:", callInfo);

      await this._joinAndStream(callInfo);

    } catch (e) {
      console.error("[duox-intercom] connect error", e);
      this._cleanup();
      this._setState("error", e.message || "Connection failed");
    }
  }

  async _joinAndStream(callInfo) {

      const socket = _io(callInfo.socket_url, {
        transports: ["websocket"],
        reconnection: false,
      });
      this._socket = socket;

      socket.on("disconnect", () => {
        this._cleanup();
        this._hass?.callWS({ type: "duox/hangup", entry_id: this._entryId }).catch(() => {});
        this._setState("idle");
      });
      socket.on("end_up", () => {
        this._cleanup();
        this._hass?.callWS({ type: "duox/hangup", entry_id: this._entryId }).catch(() => {});
        this._setState("idle");
      });
      socket.on("connect_error", (e) => {
        this._cleanup();
        this._setState("error", "Signaling error");
      });

      await new Promise((res, rej) => {
        socket.on("connect", res);
        socket.on("connect_error", rej);
        setTimeout(() => rej(new Error("timeout")), 10000);
      });

      const joinResult = await this._emitAck("join_call", {
        roomId: callInfo.room_id,
        appToken: callInfo.gcm_token,
        fermaxOauthToken: callInfo.oauth_token,
        protocolVersion: PROTOCOL_VERSION,
      });

      if (joinResult.error) {
        throw new Error(joinResult.error.code || "join failed");
      }
      const r = joinResult.result;
      console.debug("[duox-intercom] join_call result keys:", Object.keys(r));

      const device = new _mediasoupClient.Device();
      await device.load({ routerRtpCapabilities: safeParse(r.routerRtpCapabilities) });
      this._device = device;

      const iceServers = r.iceServers ? safeParse(r.iceServers) : undefined;

      this._recvVideoTransport = this._createRecvTransport(
        device, r.recvTransportVideo, iceServers
      );

      this._recvAudioTransport = this._createRecvTransport(
        device, r.recvTransportAudio, iceServers
      );

      this._sendTransport = this._createSendTransport(
        device, r.sendTransport, iceServers
      );

      if (r.producerIdVideo) {
        await this._consumeTrack(
          this._recvVideoTransport, r.producerIdVideo, "video"
        );
      }

      this._setState("preview");
  }

  /* -- Pickup / talk ----------------------------------------------- */

  async _pickup() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const audioTrack = stream.getAudioTracks()[0];

      this._micProducer = await this._sendTransport.produce({ track: audioTrack });

      this._setState("call");

    } catch (e) {
      console.error("[duox-intercom] pickup error", e);
      this._setState("error", e.message || "Microphone error");
    }
  }

  _toggleMute() {
    if (!this._micProducer) return;
    const btn = this.shadowRoot.getElementById("btnMute");
    if (this._micProducer.paused) {
      this._micProducer.resume();
      if (btn) { btn.innerHTML = ICONS.mic; btn.title = "Mute"; btn.classList.remove("ibtn-mute-active"); }
    } else {
      this._micProducer.pause();
      if (btn) { btn.innerHTML = ICONS.micOff; btn.title = "Unmute"; btn.classList.add("ibtn-mute-active"); }
    }
  }

  /* -- Hangup ------------------------------------------------------ */

  async _hangup() {
    try {
      if (this._socket?.connected) {
        await this._emitAck("hang_up", {}).catch(() => {});
      }
    } catch (_) {}
    this._cleanup();
    this._callData = null;
    try {
      await this._hass.callWS({
        type: "duox/hangup",
        entry_id: this._entryId,
      });
    } catch (_) {}
    this._setState("idle");
  }

  /* -- Unlock gate ------------------------------------------------- */

  async _unlock() {
    if (!this._hass || !this._lockEntity) return;
    try {
      await this._hass.callService("lock", "open", {
        entity_id: this._lockEntity,
      });
    } catch (e) {
      console.error("[duox-intercom] unlock error", e);
    }
  }

  _cleanup() {
    try { this._micProducer?.close(); } catch (_) {}
    try { this._videoConsumer?.close(); } catch (_) {}
    try { this._audioConsumer?.close(); } catch (_) {}
    try { this._callAudioConsumer?.close(); } catch (_) {}
    try { this._recvVideoTransport?.close(); } catch (_) {}
    try { this._recvAudioTransport?.close(); } catch (_) {}
    try { this._sendTransport?.close(); } catch (_) {}
    try { this._socket?.disconnect(); } catch (_) {}

    this._socket = null;
    this._device = null;
    this._recvVideoTransport = null;
    this._recvAudioTransport = null;
    this._sendTransport = null;
    this._videoConsumer = null;
    this._audioConsumer = null;
    this._callAudioConsumer = null;
    this._micProducer = null;
    this._videoStream = null;
    this._audioStream = null;
    this._callData = null;
  }

  /* -- Transport helpers ------------------------------------------- */

  _createRecvTransport(device, tData, iceServers) {
    const transport = device.createRecvTransport({
      id: tData.id,
      dtlsParameters: safeParse(tData.dtlsParameters),
      iceCandidates: safeParse(tData.iceCandidates),
      iceParameters: safeParse(tData.iceParameters),
      iceServers: iceServers,
    });

    transport.on("connect", ({ dtlsParameters }, callback, errback) => {
      this._emitAck("transport_connect", {
        transportId: transport.id,
        dtlsParameters: dtlsParameters,
      })
      .then(() => callback())
      .catch(errback);
    });

    return transport;
  }

  _createSendTransport(device, tData, iceServers) {
    const transport = device.createSendTransport({
      id: tData.id,
      dtlsParameters: safeParse(tData.dtlsParameters),
      iceCandidates: safeParse(tData.iceCandidates),
      iceParameters: safeParse(tData.iceParameters),
      iceServers: iceServers,
    });

    transport.on("connect", ({ dtlsParameters }, callback, errback) => {
      this._emitAck("transport_connect", {
        transportId: transport.id,
        dtlsParameters: dtlsParameters,
      })
      .then(() => callback())
      .catch(errback);
    });

    transport.on("produce", async ({ kind, rtpParameters, appData }, callback, errback) => {
      try {
        const pickupResult = await this._emitAck("pickup", {
          parameters: { kind, rtpParameters, appData },
          rtpCapabilities: this._device.rtpCapabilities,
        });

        if (pickupResult.error) {
          errback(new Error(pickupResult.error.code || "pickup failed"));
          return;
        }

        const pr = pickupResult.result;
        callback({ id: pr.producerId });

        if (pr.consumer && pr.consumer.producerId) {
          await this._consumeTrack(
            this._recvAudioTransport, pr.consumer.producerId, "audio"
          );
        }
      } catch (e) {
        errback(e);
      }
    });

    return transport;
  }

  async _consumeTrack(transport, producerId, kind) {
    const caps = this._device.rtpCapabilities;
    const resp = await this._emitAck("transport_consume", {
      transportId: transport.id,
      producerId: producerId,
      rtpCapabilities: typeof caps === "string" ? safeParse(caps) : caps,
    });

    if (resp.error) throw new Error(resp.error.code || "consume failed");
    const cr = resp.result;

    const consumer = await transport.consume({
      id: cr.id,
      producerId: cr.producerId,
      kind: cr.kind,
      rtpParameters: safeParse(cr.rtpParameters),
    });

    if (kind === "video") {
      this._videoConsumer = consumer;
      this._videoStream = new MediaStream([consumer.track]);
      const vid = this.shadowRoot.getElementById("vid");
      if (vid) {
        vid.srcObject = this._videoStream;
        vid.play().catch(() => {});
      }
    } else {
      if (this._audioConsumer) {
        this._callAudioConsumer = consumer;
      } else {
        this._audioConsumer = consumer;
      }
      this._audioStream = new MediaStream([consumer.track]);
      const audio = new Audio();
      audio.srcObject = this._audioStream;
      audio.play().catch(() => {});
    }
  }

  /* -- Socket.IO helpers ------------------------------------------- */

  _emitAck(event, data) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error("ack timeout")), 15000);
      this._socket.emit(event, data, (response) => {
        clearTimeout(timeout);
        resolve(response);
      });
    });
  }

  async _getActiveCall() {
    if (!this._hass) return null;
    try {
      return await this._hass.callWS({
        type: "duox/active_call",
        entry_id: this._entryId,
      });
    } catch (e) {
      console.error("[duox-intercom] ws error", e);
      return null;
    }
  }

  async _triggerAutoon() {
    if (!this._hass) return null;
    try {
      console.debug("[duox-intercom] calling duox/autoon...");
      const result = await this._hass.callWS({
        type: "duox/autoon",
        entry_id: this._entryId,
      });
      console.debug("[duox-intercom] autoon result:", result);
      return result;
    } catch (e) {
      console.error("[duox-intercom] autoon error:", e);
      return null;
    }
  }

  /* -- Card editor helpers ----------------------------------------- */

  static getStubConfig() {
    return { entry_id: "", camera_entity: "", lock_entity: "", wifi_entity: "", device_name: "Doorbell" };
  }

  getCardSize() {
    return 8;
  }
}

customElements.define("duox-intercom-card", DuoxIntercomCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "duox-intercom-card",
  name: "Duox Intercom",
  description: "Fermax Duox live video intercom with bidirectional audio",
});
