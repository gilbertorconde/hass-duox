/**
 * Duox Intercom Card — Custom Lovelace card for Fermax Duox live video
 * and bidirectional audio via mediasoup WebRTC.
 *
 * Dependencies loaded from CDN:
 *   - mediasoup-client v3 (browser WebRTC)
 *   - socket.io-client v4 (signaling transport)
 */

const CARD_VERSION = "0.1.7";
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
/* Card                                                                */
/* ------------------------------------------------------------------ */

class DuoxIntercomCard extends HTMLElement {
  /* -- Lovelace lifecycle ------------------------------------------ */

  setConfig(config) {
    this._config = config;
    this._entryId = config.entry_id || "";
    this._cameraEntity = config.camera_entity || "";
    this._lockEntity = config.lock_entity || "";
    this._hass = null;
    this._state = "idle";       // idle | connecting | preview | call | error
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
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
  }

  /* -- Render ------------------------------------------------------ */

  _render() {
    const state = this._state;
    const err = this._error || "";
    const cameraProxy = this._cameraEntity
      ? `/api/camera_proxy/${this._cameraEntity}`
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .card {
          background: var(--ha-card-background, var(--card-background-color, #fff));
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.15));
          overflow: hidden;
          position: relative;
        }
        .video-wrap {
          position: relative;
          width: 100%;
          background: #000;
          aspect-ratio: 16/9;
        }
        .video-wrap video, .video-wrap img {
          width: 100%; height: 100%; object-fit: contain; display: block;
        }
        .controls {
          display: flex; gap: 8px; padding: 12px; justify-content: center;
          flex-wrap: wrap;
        }
        button {
          cursor: pointer;
          border: none; border-radius: 24px;
          padding: 10px 24px;
          font-size: 14px; font-weight: 600;
          color: #fff;
          transition: opacity .15s;
        }
        button:hover { opacity: .85; }
        button:disabled { opacity: .4; cursor: default; }
        .btn-connect  { background: #4CAF50; }
        .btn-talk     { background: #2196F3; }
        .btn-mute     { background: #FF9800; }
        .btn-hangup   { background: #f44336; }
        .btn-unlock   { background: #9C27B0; }
        .status {
          text-align: center; padding: 6px 12px;
          font-size: 12px; color: var(--secondary-text-color, #666);
        }
        .status:empty { display: none; }
        .status.error { color: #f44336; }
      </style>

      <ha-card>
        <div class="card">
          <div class="video-wrap" id="vw">
            ${state === "idle" && cameraProxy
              ? `<img src="${cameraProxy}" alt="Snapshot"/>`
              : `<video id="vid" autoplay playsinline muted></video>`}
          </div>
          <div class="controls">
            ${state === "idle"
              ? `<button class="btn-connect" id="btnConnect">Connect</button>`
              : ""}
            ${state === "preview"
              ? `<button class="btn-talk" id="btnTalk">Talk</button>
                 <button class="btn-hangup" id="btnHangup">Hang up</button>`
              : ""}
            ${state === "call"
              ? `<button class="btn-mute" id="btnMute">Mute</button>
                 <button class="btn-hangup" id="btnHangup">Hang up</button>`
              : ""}
            ${state === "connecting"
              ? `<button class="btn-hangup" id="btnHangup">Cancel</button>`
              : ""}
            ${this._lockEntity && state !== "connecting"
              ? `<button class="btn-unlock" id="btnUnlock">\uD83D\uDD11 Open</button>`
              : ""}
          </div>
          <div class="status${state === "error" ? " error" : ""}" id="status">
            ${state === "connecting" ? "Connecting\u2026"
              : state === "preview" ? "Preview \u2014 press Talk to speak"
              : state === "call" ? "In call"
              : state === "error" ? `Error: ${err}`
              : ""}
          </div>
        </div>
      </ha-card>
    `;

    this._bindButtons();
  }

  _bindButtons() {
    const $ = (id) => this.shadowRoot.getElementById(id);
    $("btnConnect")?.addEventListener("click", () => this._connect());
    $("btnTalk")?.addEventListener("click", () => this._pickup());
    $("btnMute")?.addEventListener("click", () => this._toggleMute());
    $("btnHangup")?.addEventListener("click", () => this._hangup());
    $("btnUnlock")?.addEventListener("click", () => this._unlock());
  }

  _setState(s, err) {
    this._state = s;
    this._error = err || null;
    this._render();
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
        this._setState("idle");
      });
      socket.on("end_up", () => {
        this._cleanup();
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

      /* Receive-video transport */
      this._recvVideoTransport = this._createRecvTransport(
        device, r.recvTransportVideo, iceServers
      );

      /* Receive-audio transport */
      this._recvAudioTransport = this._createRecvTransport(
        device, r.recvTransportAudio, iceServers
      );

      /* Send transport (for mic later) */
      this._sendTransport = this._createSendTransport(
        device, r.sendTransport, iceServers
      );

      /* Consume video only — audio is consumed after pickup (matching native app) */
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
    if (this._micProducer.paused) {
      this._micProducer.resume();
      const btn = this.shadowRoot.getElementById("btnMute");
      if (btn) btn.textContent = "Mute";
    } else {
      this._micProducer.pause();
      const btn = this.shadowRoot.getElementById("btnMute");
      if (btn) btn.textContent = "Unmute";
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
      const vid = this.shadowRoot.getElementById("vid");
      if (vid) {
        vid.srcObject = new MediaStream([consumer.track]);
        vid.muted = true;
        vid.play().catch(() => {});
      }
    } else {
      if (this._audioConsumer) {
        this._callAudioConsumer = consumer;
      } else {
        this._audioConsumer = consumer;
      }
      const audio = new Audio();
      audio.srcObject = new MediaStream([consumer.track]);
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
    return { entry_id: "", camera_entity: "", lock_entity: "" };
  }

  getCardSize() {
    return 5;
  }
}

customElements.define("duox-intercom-card", DuoxIntercomCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "duox-intercom-card",
  name: "Duox Intercom",
  description: "Fermax Duox live video intercom with bidirectional audio",
});
