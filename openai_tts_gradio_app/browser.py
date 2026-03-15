from __future__ import annotations

from .config import BROWSER_DEBUG_STORAGE_KEY


def live_player_head() -> str:
    return f"""
<script>
(() => {{
  const BASE_START_BUFFER_S = 0.20;
  const MAX_START_BUFFER_S = 0.42;
  const MIN_LEAD_S = 0.10;
  const MAX_LEAD_S = 0.26;
  const POLL_MS = 10;
  const DEBUG_STORAGE_KEY = {BROWSER_DEBUG_STORAGE_KEY!r};
  const state = {{
    ctx: null,
    scheduledUntil: 0,
    pending: [],
    pendingDuration: 0,
    startBufferTarget: BASE_START_BUFFER_S,
    streamStartedAt: 0,
    lastChunkReceivedAt: 0,
    jitterDeficitEwma: 0,
    started: false,
    doneReceived: false,
    activeStreamId: null,
    currentValue: "",
    lastSeq: -1,
    chain: Promise.resolve(),
    sources: new Set(),
    completedBlobUrl: null,
  }};
  let activeDirectController = null;
  let directRequestToken = 0;
  let bootstrapped = false;

  function debug(...args) {{
    try {{
      if (window.localStorage && window.localStorage.getItem(DEBUG_STORAGE_KEY) === "1") {{
        console.debug("[openai-tts]", ...args);
      }}
    }} catch (err) {{
      console.debug("[openai-tts]", ...args);
    }}
  }}

  function clamp(value, minValue, maxValue) {{
    return Math.min(Math.max(value, minValue), maxValue);
  }}

  function nowS() {{
    return window.performance.now() / 1000;
  }}

  function statusEl() {{
    return document.querySelector("#openai-tts-live-player-status");
  }}

  function setStatus(message) {{
    const el = statusEl();
    if (el) el.textContent = message;
  }}

  function escapeHtml(value) {{
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }}

  function buildStatusMarkup(message, ok = true) {{
    const cssClass = ok ? "status-ok" : "status-warn";
    return `<div class="status-box"><p class="${{cssClass}}">${{escapeHtml(message)}}</p></div>`;
  }}

  function currentStatusMarkup() {{
    const root = document.querySelector("#openai-tts-generation-status");
    return root ? root.innerHTML : buildStatusMarkup("No synthesis request submitted yet.", true);
  }}

  function setGenerationStatus(message, ok = true) {{
    const root = document.querySelector("#openai-tts-generation-status");
    if (!root) {{
      return;
    }}
    root.innerHTML = buildStatusMarkup(message, ok);
  }}

  function completedAudioRoot() {{
    return document.querySelector("#openai-tts-output-audio");
  }}

  function findCompletedAudioParts() {{
    const root = completedAudioRoot();
    if (!root) {{
      return {{ root: null, empty: null, container: null, browserAudio: null, nativeAudio: null }};
    }}
    const empty = root.querySelector(".empty");
    const container = root.querySelector("[data-openai-tts-browser-output='1']");
    const browserAudio = root.querySelector("[data-openai-tts-browser-player='1']");
    const nativeAudio = root.querySelector("audio:not([data-openai-tts-browser-player='1'])");
    return {{ root, empty, container, browserAudio, nativeAudio }};
  }}

  function ensureCompletedAudio() {{
    const parts = findCompletedAudioParts();
    if (!parts.root) {{
      return null;
    }}
    if (parts.empty) {{
      parts.empty.style.display = "none";
    }}
    let container = parts.container;
    if (!container) {{
      container = document.createElement("div");
      container.dataset.openaiTtsBrowserOutput = "1";
      container.style.marginTop = "0.75rem";
      parts.root.appendChild(container);
    }}
    container.style.display = "block";
    let audio = parts.browserAudio;
    if (!audio) {{
      audio = document.createElement("audio");
      audio.controls = true;
      audio.preload = "metadata";
      audio.style.width = "100%";
      audio.dataset.openaiTtsBrowserPlayer = "1";
      container.appendChild(audio);
    }}
    return audio;
  }}

  function revokeCompletedAudioUrl() {{
    if (!state.completedBlobUrl) {{
      return;
    }}
    try {{
      URL.revokeObjectURL(state.completedBlobUrl);
    }} catch (err) {{
      console.warn("Failed to revoke completed blob URL", err);
    }}
    state.completedBlobUrl = null;
  }}

  function clearCompletedAudio() {{
    revokeCompletedAudioUrl();
    const {{ empty, container, browserAudio, nativeAudio }} = findCompletedAudioParts();
    if (browserAudio) {{
      try {{
        browserAudio.pause();
      }} catch (err) {{}}
      browserAudio.removeAttribute("src");
      browserAudio.load();
    }}
    if (container && container.dataset.openaiTtsBrowserOutput === "1") {{
      container.style.display = "none";
    }}
    if (empty && !nativeAudio) {{
      empty.style.display = "";
    }}
  }}

  function setCompletedAudioBytes(audioBytes, mimeType = "audio/wav") {{
    clearCompletedAudio();
    const audio = ensureCompletedAudio();
    if (!audio) {{
      debug("completed audio element missing");
      return null;
    }}
    const blob = new Blob([audioBytes], {{ type: mimeType }});
    const blobUrl = URL.createObjectURL(blob);
    state.completedBlobUrl = blobUrl;
    audio.src = blobUrl;
    audio.load();
    debug("completed browser audio ready", {{ bytes: blob.size, mimeType }});
    return blobUrl;
  }}

  function normalizeServerBaseUrl(value) {{
    const normalized = String(value || "").trim().replace(/\\/+$/, "");
    if (!normalized) {{
      throw new Error("Server base URL is required.");
    }}

    const isLocalHost = (hostname) => {{
      const host = String(hostname || "").trim().toLowerCase();
      return host === "localhost" || host === "127.0.0.1" || host === "0.0.0.0" || host === "[::1]";
    }};

    let url;
    try {{
      url = new URL(normalized, window.location.href);
    }} catch (err) {{
      throw new Error(`Invalid server base URL: ${{normalized}}`);
    }}

    const variants = [];
    const originalUrl = url.toString().replace(/\\/+$/, "");
    const rewrittenUrl = new URL(originalUrl);
    if (isLocalHost(rewrittenUrl.hostname) && !isLocalHost(window.location.hostname)) {{
      rewrittenUrl.hostname = window.location.hostname;
    }}
    for (const candidate of [rewrittenUrl.toString().replace(/\\/+$/, ""), originalUrl]) {{
      if (!variants.includes(candidate)) {{
        variants.push(candidate);
      }}
    }}

    const normalizedUrl = variants[0];
    if (normalizedUrl.endsWith("/v1")) {{
      return {{
        rootBase: normalizedUrl.slice(0, -3),
        v1Base: normalizedUrl,
        speechUrl: `${{normalizedUrl}}/audio/speech`,
        speechUrls: variants.map((candidate) =>
          candidate.endsWith("/v1") ? `${{candidate}}/audio/speech` : `${{candidate}}/v1/audio/speech`
        ),
      }};
    }}
    return {{
      rootBase: normalizedUrl,
      v1Base: `${{normalizedUrl}}/v1`,
      speechUrl: `${{normalizedUrl}}/v1/audio/speech`,
      speechUrls: variants.map((candidate) =>
        candidate.endsWith("/v1") ? `${{candidate}}/audio/speech` : `${{candidate}}/v1/audio/speech`
      ),
    }};
  }}

  function concatUint8Arrays(a, b) {{
    const merged = new Uint8Array(a.length + b.length);
    merged.set(a, 0);
    merged.set(b, a.length);
    return merged;
  }}

  function mergeUint8Arrays(chunks, totalLength) {{
    const merged = new Uint8Array(totalLength);
    let offset = 0;
    for (const chunk of chunks) {{
      merged.set(chunk, offset);
      offset += chunk.length;
    }}
    return merged;
  }}

  function bytesToBase64(bytes) {{
    let binary = "";
    const step = 0x8000;
    for (let offset = 0; offset < bytes.length; offset += step) {{
      const slice = bytes.subarray(offset, offset + step);
      binary += String.fromCharCode(...slice);
    }}
    return btoa(binary);
  }}

  function pcmToWavBytes(frames, sampleRate, sampleWidth, numChannels) {{
    const blockAlign = sampleWidth * numChannels;
    const byteRate = sampleRate * blockAlign;
    const buffer = new ArrayBuffer(44 + frames.length);
    const view = new DataView(buffer);
    const bytes = new Uint8Array(buffer);

    function writeAscii(offset, text) {{
      for (let i = 0; i < text.length; i += 1) {{
        view.setUint8(offset + i, text.charCodeAt(i));
      }}
    }}

    writeAscii(0, "RIFF");
    view.setUint32(4, 36 + frames.length, true);
    writeAscii(8, "WAVE");
    writeAscii(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, sampleWidth * 8, true);
    writeAscii(36, "data");
    view.setUint32(40, frames.length, true);
    bytes.set(frames, 44);
    return bytes;
  }}

  function parseWavStreamHeader(prefix) {{
    if (prefix.length < 12) {{
      return null;
    }}
    const view = new DataView(prefix.buffer, prefix.byteOffset, prefix.byteLength);
    const riff = String.fromCharCode(...prefix.slice(0, 4));
    const wave = String.fromCharCode(...prefix.slice(8, 12));
    if (!["RIFF", "RF64"].includes(riff) || wave !== "WAVE") {{
      throw new Error("Streaming audio body is not a WAV file");
    }}

    let pos = 12;
    let fmt = null;
    while (pos + 8 <= prefix.length) {{
      const chunkId = String.fromCharCode(...prefix.slice(pos, pos + 4));
      const chunkSize = view.getUint32(pos + 4, true);
      const chunkStart = pos + 8;

      if (chunkId === "fmt ") {{
        if (prefix.length < chunkStart + 16) {{
          return null;
        }}
        const audioFormat = view.getUint16(chunkStart, true);
        const numChannels = view.getUint16(chunkStart + 2, true);
        const sampleRate = view.getUint32(chunkStart + 4, true);
        const blockAlign = view.getUint16(chunkStart + 12, true);
        const bitsPerSample = view.getUint16(chunkStart + 14, true);
        if (audioFormat !== 1) {{
          throw new Error("Only PCM WAV streaming is supported");
        }}
        fmt = {{
          sampleRate,
          sampleWidth: bitsPerSample / 8,
          numChannels,
          blockAlign,
        }};
      }} else if (chunkId === "data") {{
        if (!fmt) {{
          throw new Error("Invalid WAV stream: missing fmt chunk before data");
        }}
        return {{ ...fmt, dataOffset: chunkStart }};
      }}

      const paddedChunkSize = chunkSize + (chunkSize % 2);
      const nextPos = chunkStart + paddedChunkSize;
      if (prefix.length < nextPos) {{
        return null;
      }}
      pos = nextPos;
    }}

    return null;
  }}

  async function ensureContext() {{
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) {{
      setStatus("WebAudio unavailable");
      throw new Error("WebAudio unavailable");
    }}
    if (!state.ctx) {{
      state.ctx = new AudioCtx();
      state.scheduledUntil = state.ctx.currentTime;
    }}
    if (state.ctx.state === "suspended") {{
      try {{
        await state.ctx.resume();
      }} catch (err) {{
        console.warn("AudioContext resume failed", err);
      }}
    }}
    return state.ctx;
  }}

  async function unlockAudioContext() {{
    try {{
      const ctx = await ensureContext();
      if (ctx.state === "suspended") {{
        await ctx.resume();
      }}
    }} catch (err) {{
      console.warn("AudioContext unlock failed", err);
    }}
  }}

  function clearScheduledSources() {{
    for (const source of state.sources) {{
      try {{
        source.stop();
      }} catch (err) {{}}
      try {{
        source.disconnect();
      }} catch (err) {{}}
    }}
    state.sources.clear();
  }}

  function resetPlayer() {{
    clearScheduledSources();
    state.pending = [];
    state.pendingDuration = 0;
    state.startBufferTarget = BASE_START_BUFFER_S;
    state.streamStartedAt = 0;
    state.lastChunkReceivedAt = 0;
    state.jitterDeficitEwma = 0;
    state.started = false;
    state.doneReceived = false;
    state.activeStreamId = null;
    state.scheduledUntil = state.ctx ? state.ctx.currentTime : 0;
    state.lastSeq = -1;
    state.currentValue = "";
    setStatus("Idle");
  }}

  function bufferedAheadS() {{
    if (!state.ctx) {{
      return 0;
    }}
    return Math.max(state.scheduledUntil - state.ctx.currentTime, 0);
  }}

  function desiredLeadS() {{
    return clamp(
      Math.max(MIN_LEAD_S, MIN_LEAD_S + state.jitterDeficitEwma * 2.0),
      MIN_LEAD_S,
      MAX_LEAD_S,
    );
  }}

  function updateJitterDeficit(gapS, chunkDurationS) {{
    const deficit = Math.max(gapS - chunkDurationS, 0);
    state.jitterDeficitEwma =
      state.jitterDeficitEwma === 0
        ? deficit
        : state.jitterDeficitEwma * 0.75 + deficit * 0.25;
  }}

  function updateStatus() {{
    if (!state.activeStreamId) {{
      setStatus("Idle");
      return;
    }}
    if (!state.started) {{
      setStatus(
        `Buffering | ${{(state.pendingDuration * 1000).toFixed(0)}}/${{(state.startBufferTarget * 1000).toFixed(0)}} ms`
      );
      return;
    }}
    const bufferedMs = bufferedAheadS() * 1000;
    if (state.doneReceived && bufferedMs <= 10) {{
      setStatus("Done");
      return;
    }}
    if (state.doneReceived) {{
      setStatus(`Finishing | ${{bufferedMs.toFixed(0)}} ms buffered`);
      return;
    }}
    setStatus(`Playing | ${{bufferedMs.toFixed(0)}} ms buffered`);
  }}

  function base64ToArrayBuffer(base64) {{
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {{
      bytes[i] = binary.charCodeAt(i);
    }}
    return bytes.buffer;
  }}

  async function decodeChunk(base64Audio) {{
    const ctx = await ensureContext();
    const buffer = base64ToArrayBuffer(base64Audio);
    return ctx.decodeAudioData(buffer.slice(0));
  }}

  async function scheduleBuffer(audioBuffer, {{ enforceLead = false }} = {{}}) {{
    const ctx = await ensureContext();
    const nextStart = Math.max(state.scheduledUntil, ctx.currentTime);
    const startAt = enforceLead
      ? Math.max(nextStart, ctx.currentTime + desiredLeadS())
      : nextStart;
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    source.start(startAt);
    state.sources.add(source);
    source.onended = () => {{
      state.sources.delete(source);
      try {{
        source.disconnect();
      }} catch (err) {{}}
      window.setTimeout(updateStatus, 0);
    }};
    state.scheduledUntil = startAt + audioBuffer.duration;
    updateStatus();
  }}

  async function flushPendingBuffers({{ enforceLead = false }} = {{}}) {{
    if (state.pending.length === 0) {{
      return;
    }}
    const ctx = await ensureContext();
    state.started = true;
    state.scheduledUntil = Math.max(state.scheduledUntil, ctx.currentTime);
    const pending = state.pending;
    state.pending = [];
    state.pendingDuration = 0;
    for (let i = 0; i < pending.length; i += 1) {{
      await scheduleBuffer(pending[i], {{ enforceLead: enforceLead && i === 0 }});
    }}
    updateStatus();
  }}

  async function handleAudioChunk(event, {{ flushImmediately = false }} = {{}}) {{
    const receivedAt = nowS();
    const audioBuffer = await decodeChunk(event.data);
    const previousReceiveAt = state.lastChunkReceivedAt || state.streamStartedAt;
    if (previousReceiveAt > 0) {{
      updateJitterDeficit(receivedAt - previousReceiveAt, audioBuffer.duration);
    }}
    state.lastChunkReceivedAt = receivedAt;

    await ensureContext();
    const currentlyBuffered = bufferedAheadS();
    if (state.started && !state.doneReceived && currentlyBuffered <= 0.015) {{
      state.started = false;
      state.pending = [];
      state.pendingDuration = 0;
      state.startBufferTarget = clamp(
        Math.max(BASE_START_BUFFER_S * 0.75, desiredLeadS() * 1.5),
        MIN_LEAD_S,
        MAX_START_BUFFER_S,
      );
    }}

    if (!state.started) {{
      if (state.pendingDuration === 0) {{
        const startupGap = state.streamStartedAt > 0 ? receivedAt - state.streamStartedAt : 0;
        const startupDeficit = Math.max(startupGap - audioBuffer.duration, 0);
        state.startBufferTarget = clamp(
          Math.max(BASE_START_BUFFER_S, startupDeficit * 1.2 + MIN_LEAD_S),
          BASE_START_BUFFER_S,
          MAX_START_BUFFER_S,
        );
      }}
      state.pending.push(audioBuffer);
      state.pendingDuration += audioBuffer.duration;
      updateStatus();
      if (!flushImmediately && state.pendingDuration < state.startBufferTarget) {{
        return;
      }}
      await flushPendingBuffers({{ enforceLead: true }});
      return;
    }}
    await scheduleBuffer(audioBuffer);
  }}

  async function processEvent(event) {{
    if (!event || typeof event !== "object") return;
    if (event.type === "reset") {{
      resetPlayer();
      clearCompletedAudio();
      return;
    }}
    if (event.type === "start") {{
      if (
        state.activeStreamId &&
        event.stream_id === state.activeStreamId &&
        typeof event.seq === "number" &&
        event.seq <= state.lastSeq
      ) {{
        return;
      }}
      resetPlayer();
      clearCompletedAudio();
      state.activeStreamId = event.stream_id || null;
      state.streamStartedAt = nowS();
      state.lastSeq = typeof event.seq === "number" ? event.seq : -1;
      unlockAudioContext();
      setStatus("Connecting…");
      return;
    }}
    if (!state.activeStreamId) {{
      return;
    }}
    if (event.stream_id && state.activeStreamId && event.stream_id !== state.activeStreamId) {{
      return;
    }}
    if (typeof event.seq === "number" && event.seq <= state.lastSeq) {{
      return;
    }}
    if (typeof event.seq === "number") {{
      state.lastSeq = event.seq;
    }}
    if (event.type === "audio.chunk") {{
      await handleAudioChunk(event);
      return;
    }}
    if (event.type === "done") {{
      state.doneReceived = true;
      if (event.final_chunk_data) {{
        await handleAudioChunk({{ data: event.final_chunk_data }}, {{ flushImmediately: true }});
      }} else if (state.pending.length > 0) {{
        await flushPendingBuffers({{ enforceLead: false }});
      }}
      updateStatus();
      return;
    }}
    if (event.type === "error") {{
      state.doneReceived = true;
      setStatus(`Error: ${{event.error || "unknown"}}`);
    }}
  }}

  async function processIncomingPayload(payload) {{
    if (Array.isArray(payload)) {{
      for (const event of payload) {{
        await processEvent(event);
      }}
      return;
    }}
    if (
      payload &&
      typeof payload === "object" &&
      payload.type === "batch" &&
      Array.isArray(payload.events)
    ) {{
      for (const event of payload.events) {{
        await processEvent(event);
      }}
      return;
    }}
    await processEvent(payload);
  }}

  function dispatchDirectPayload(payload) {{
    state.chain = state.chain.then(() => processIncomingPayload(payload)).catch((err) => {{
      console.error("Direct live player event failed", err);
      setStatus(`Error: ${{err.message || err}}`);
    }});
    return state.chain;
  }}

  async function streamAudioBodyRequest(
    serverBaseUrl,
    modelId,
    voiceId,
    text,
    requestMode
  ) {{
    const requestText = String(text || "").trim();
    if (!requestText) {{
      return buildStatusMarkup("Enter some text to synthesize.", false);
    }}
    if (!modelId) {{
      return buildStatusMarkup("Select a model before generating speech.", false);
    }}

    if (activeDirectController) {{
      activeDirectController.abort();
    }}
    const controller = new AbortController();
    const requestToken = ++directRequestToken;
    activeDirectController = controller;

    const endpoints = normalizeServerBaseUrl(serverBaseUrl);
    const t0 = window.performance.now();
    const streamId = `audio-${{Date.now().toString(16)}}-${{Math.random().toString(16).slice(2)}}`;
    let seq = 1;

    debug("browser audio request start", {{
      requestMode,
      modelId,
      voiceId: voiceId || "default",
      speechUrls: endpoints.speechUrls,
    }});

    clearCompletedAudio();
    setGenerationStatus(
      requestMode === "streaming"
        ? "Streaming audio-body request started."
        : "Auto audio-body request started.",
      true,
    );
    await dispatchDirectPayload({{ type: "reset", ts: Date.now() / 1000 }});
    await dispatchDirectPayload({{ type: "start", stream_id: streamId, seq }});

    try {{
      const requestBody = JSON.stringify({{
        model: modelId,
        input: requestText,
        voice: voiceId || "default",
        response_format: "wav",
        stream: true,
        stream_format: "audio",
      }});
      let response = null;
      let fetchError = null;
      for (const speechUrl of endpoints.speechUrls || [endpoints.speechUrl]) {{
        try {{
          response = await fetch(speechUrl, {{
            method: "POST",
            headers: {{
              Accept: "application/octet-stream",
              "Content-Type": "application/json",
            }},
            body: requestBody,
            signal: controller.signal,
          }});
          break;
        }} catch (err) {{
          if (controller.signal.aborted) {{
            throw err;
          }}
          fetchError = err;
        }}
      }}

      if (!response) {{
        throw fetchError || new Error("Failed to fetch");
      }}

      if (!response.ok) {{
        const detail = (await response.text()) || response.statusText;
        throw new Error(`HTTP ${{response.status}} - ${{detail}}`);
      }}
      if (!response.body || !response.body.getReader) {{
        throw new Error("Browser streaming response bodies are unavailable");
      }}

      const contentType = (response.headers.get("content-type") || "")
        .split(";", 1)[0]
        .trim()
        .toLowerCase();
      const supportsLiveAudioBody = [
        "audio/wav",
        "audio/x-wav",
        "audio/pcm",
      ].includes(contentType);
      if (!supportsLiveAudioBody) {{
        throw new Error(
          `Unsupported audio stream content-type: ${{contentType || "unknown"}}`
        );
      }}

      debug("browser audio response", {{ contentType }});

      const reader = response.body.getReader();
      const pcmChunks = [];
      let totalPcmBytes = 0;
      let ttfaS = null;
      let liveChunkCount = 0;
      let sampleRate = 24000;
      let sampleWidth = 2;
      let numChannels = 1;
      let blockAlign = 2;
      let wavHeaderParsed = contentType === "audio/pcm";
      let wavHeaderBuffer = new Uint8Array(0);
      let pcmBuffer = new Uint8Array(0);

      while (true) {{
        const {{ done, value }} = await reader.read();
        if (done) {{
          break;
        }}
        if (!value || value.length === 0) {{
          continue;
        }}

        if (contentType === "audio/pcm") {{
          pcmBuffer = concatUint8Arrays(pcmBuffer, value);
        }} else if (wavHeaderParsed) {{
          pcmBuffer = concatUint8Arrays(pcmBuffer, value);
        }} else {{
          wavHeaderBuffer = concatUint8Arrays(wavHeaderBuffer, value);
          const parsedHeader = parseWavStreamHeader(wavHeaderBuffer);
          if (!parsedHeader) {{
            continue;
          }}
          sampleRate = parsedHeader.sampleRate;
          sampleWidth = parsedHeader.sampleWidth;
          numChannels = parsedHeader.numChannels;
          blockAlign = parsedHeader.blockAlign;
          pcmBuffer = concatUint8Arrays(
            pcmBuffer,
            wavHeaderBuffer.slice(parsedHeader.dataOffset)
          );
          wavHeaderBuffer = new Uint8Array(0);
          wavHeaderParsed = true;
          debug("parsed browser wav header", {{
            sampleRate,
            sampleWidth,
            numChannels,
            blockAlign,
          }});
        }}

        let playableChunkSize = Math.max(
          Math.floor(sampleRate * sampleWidth * numChannels * 0.20),
          4096,
        );
        playableChunkSize -= playableChunkSize % blockAlign;
        if (playableChunkSize <= 0) {{
          playableChunkSize = blockAlign;
        }}

        while (pcmBuffer.length >= playableChunkSize) {{
          const emitChunk = pcmBuffer.slice(0, playableChunkSize);
          pcmBuffer = pcmBuffer.slice(playableChunkSize);
          pcmChunks.push(emitChunk);
          totalPcmBytes += emitChunk.length;
          if (ttfaS === null) {{
            ttfaS = (window.performance.now() - t0) / 1000;
          }}
          liveChunkCount += 1;
          seq += 1;
          await dispatchDirectPayload({{
            type: "audio.chunk",
            stream_id: streamId,
            seq,
            data: bytesToBase64(
              pcmToWavBytes(emitChunk, sampleRate, sampleWidth, numChannels)
            ),
          }});
          setGenerationStatus("Streaming audio body…", true);
        }}
      }}

      const finalEmitLength = pcmBuffer.length - (pcmBuffer.length % blockAlign);
      let finalChunkData = null;
      if (finalEmitLength > 0) {{
        const finalChunk = pcmBuffer.slice(0, finalEmitLength);
        pcmChunks.push(finalChunk);
        totalPcmBytes += finalChunk.length;
        finalChunkData = bytesToBase64(
          pcmToWavBytes(finalChunk, sampleRate, sampleWidth, numChannels)
        );
      }}

      if (totalPcmBytes <= 0) {{
        throw new Error("server returned an empty audio response");
      }}

      const elapsedS = (window.performance.now() - t0) / 1000;
      const summaryParts = [`Completed in ${{elapsedS.toFixed(1)}}s`];
      if (ttfaS !== null) {{
        summaryParts.push(`TTFA ${{ttfaS.toFixed(2)}}s`);
      }}
      if (liveChunkCount > 0) {{
        summaryParts.push("streaming audio body");
      }} else {{
        summaryParts.push("audio body returned as a single chunk");
      }}

      seq += 1;
      await dispatchDirectPayload({{
        type: "done",
        stream_id: streamId,
        seq,
        final_chunk_data: finalChunkData,
      }});

      if (requestToken !== directRequestToken) {{
        return currentStatusMarkup();
      }}

      const mergedPcm = mergeUint8Arrays(pcmChunks, totalPcmBytes);
      const completedWav = pcmToWavBytes(mergedPcm, sampleRate, sampleWidth, numChannels);
      setCompletedAudioBytes(completedWav, "audio/wav");
      const summary = summaryParts.join(" | ");
      debug("browser audio request complete", {{
        elapsedS,
        ttfaS,
        liveChunkCount,
        totalPcmBytes,
      }});
      setGenerationStatus(summary, true);
      return buildStatusMarkup(summary, true);
    }} catch (err) {{
      if (controller.signal.aborted) {{
        debug("browser audio request aborted");
        return currentStatusMarkup();
      }}
      seq += 1;
      await dispatchDirectPayload({{
        type: "error",
        stream_id: streamId,
        seq,
        error: String(err && err.message ? err.message : err),
      }});
      clearCompletedAudio();
      const message = `Speech generation failed: ${{err && err.message ? err.message : err}}`;
      console.error("Browser audio-body request failed", err);
      setGenerationStatus(message, false);
      return buildStatusMarkup(message, false);
    }} finally {{
      if (activeDirectController === controller) {{
        activeDirectController = null;
      }}
    }}
  }}

  function findEventInput(root = null) {{
    const scope = root || document;
    return scope.querySelector("#openai-tts-live-events textarea, #openai-tts-live-events input");
  }}

  function consumeCurrentValue() {{
    const input = findEventInput();
    if (!input) {{
      return;
    }}
    const value = input.value || "";
    if (value && value !== state.currentValue) {{
      state.currentValue = value;
      try {{
        const payload = JSON.parse(value);
        debug("received live payload", payload);
        state.chain = state.chain.then(() => processIncomingPayload(payload)).catch((err) => {{
          console.error("Live player event failed", err);
          setStatus(`Error: ${{err.message || err}}`);
        }});
      }} catch (err) {{
        console.error("Invalid live event payload", err);
      }}
    }}
  }}

  function attachObserver() {{
    const eventRoot = document.querySelector("#openai-tts-live-events");
    if (!eventRoot) {{
      window.setTimeout(attachObserver, POLL_MS);
      return;
    }}
    const observer = new MutationObserver(() => {{
      window.queueMicrotask(() => {{
        consumeCurrentValue();
      }});
    }});
    observer.observe(eventRoot, {{
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
    }});
    consumeCurrentValue();
  }}

  function poll() {{
    consumeCurrentValue();
    updateStatus();
    window.setTimeout(poll, POLL_MS);
  }}

  function bootstrap() {{
    if (bootstrapped) {{
      return;
    }}
    bootstrapped = true;
    setStatus("Idle");
    attachObserver();
    poll();
  }}

  window.openaiTtsBrowser = {{
    startAudioBodyRequest: async (...args) => [await streamAudioBodyRequest(...args)],
    buildStatusMarkup,
  }};

  document.addEventListener("pointerdown", () => {{
    unlockAudioContext();
  }}, true);

  document.addEventListener("keydown", () => {{
    unlockAudioContext();
  }}, true);

  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", bootstrap, {{ once: true }});
  }} else {{
    bootstrap();
  }}
  window.addEventListener("load", bootstrap, {{ once: true }});
}})();
</script>
"""


def browser_generate_click_js() -> str:
    return """
async (serverBaseUrl, modelId, voiceId, text, requestMode) => {
  if (!window.openaiTtsBrowser || !window.openaiTtsBrowser.startAudioBodyRequest) {
    const message =
      "Browser audio controller is unavailable. Reload the page and try again.";
    return [
      window.openaiTtsBrowser && window.openaiTtsBrowser.buildStatusMarkup
        ? window.openaiTtsBrowser.buildStatusMarkup(message, false)
        : `<div class="status-box"><p class="status-warn">${message}</p></div>`,
    ];
  }
  return await window.openaiTtsBrowser.startAudioBodyRequest(
    serverBaseUrl,
    modelId,
    voiceId,
    text,
    requestMode,
  );
}
"""
