/**
 * Vendly Web Widget — embeddable chat widget
 *
 * Usage:
 *   <script src="https://your-vendly-instance.com/static/widget.js"
 *           data-vendly-org="your-org-slug"></script>
 *
 * Public API (after load):
 *   window.VendlyWidget.open()
 *   window.VendlyWidget.close()
 */
(function (window, document) {
  'use strict';

  // ── Locate our script tag ──────────────────────────────────────────────────
  const scriptTag =
    document.currentScript ||
    (function () {
      const tags = document.querySelectorAll('script[data-vendly-org]');
      return tags[tags.length - 1];
    })();

  const orgSlug = scriptTag ? scriptTag.getAttribute('data-vendly-org') || '' : '';
  const scriptSrc = scriptTag ? scriptTag.src || '' : '';

  // Derive API base URL from the script src (strip /static/widget.js suffix)
  const apiBase = scriptSrc
    ? scriptSrc.replace(/\/static\/widget\.js(\?.*)?$/, '')
    : window.location.origin;

  if (!orgSlug) {
    console.warn('[Vendly] data-vendly-org not set on widget script tag');
    return;
  }

  // ── Session management (12 h TTL) ─────────────────────────────────────────
  const SESSION_TTL_MS = 12 * 60 * 60 * 1000;
  const STORAGE_KEY = 'vendly_session_' + orgSlug;

  function loadSession() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      var s = JSON.parse(raw);
      if (Date.now() - s.created_at > SESSION_TTL_MS) {
        localStorage.removeItem(STORAGE_KEY);
        return null;
      }
      return s;
    } catch (e) {
      return null;
    }
  }

  function saveSession(sessionId, sessionToken) {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ session_id: sessionId, session_token: sessionToken, created_at: Date.now() })
      );
    } catch (e) {}
  }

  function generateSessionId() {
    if (window.crypto && window.crypto.getRandomValues) {
      var arr = new Uint8Array(16);
      window.crypto.getRandomValues(arr);
      return Array.from(arr)
        .map(function (b) { return b.toString(16).padStart(2, '0'); })
        .join('');
    }
    return Math.random().toString(36).slice(2) + Date.now().toString(36);
  }

  // ── State ──────────────────────────────────────────────────────────────────
  var config = null;
  var sessionId = null;
  var sessionToken = null;
  var ws = null;
  var wsReady = false;
  var isOpen = false;
  var consentGiven = false;
  var greetingShown = false;
  var seenMessageIds = {};

  // ── DOM refs ───────────────────────────────────────────────────────────────
  var container = null;
  var chatPanel = null;
  var messagesDiv = null;
  var inputEl = null;
  var launcherBtn = null;

  // ── API helpers ────────────────────────────────────────────────────────────
  function apiFetch(path, options) {
    return fetch(apiBase + path, Object.assign({ headers: { 'Content-Type': 'application/json', Accept: 'application/json' } }, options));
  }

  async function loadConfig() {
    try {
      var res = await apiFetch('/api/channels/webapp/public/' + encodeURIComponent(orgSlug) + '/');
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  async function fetchSessionToken(sId) {
    try {
      var res = await apiFetch('/api/channels/webchat/session/', {
        method: 'POST',
        body: JSON.stringify({ organization_slug: orgSlug, session_id: sId }),
      });
      if (!res.ok) return null;
      var data = await res.json();
      return data.session_token || null;
    } catch (e) {
      return null;
    }
  }

  async function initSession() {
    var saved = loadSession();
    if (saved) {
      sessionId = saved.session_id;
      sessionToken = saved.session_token;
      return;
    }
    sessionId = generateSessionId();
    sessionToken = await fetchSessionToken(sessionId);
    if (sessionToken) saveSession(sessionId, sessionToken);
  }

  // ── WebSocket ──────────────────────────────────────────────────────────────
  function connectWS() {
    if (!sessionId || !sessionToken) return;
    var proto = apiBase.startsWith('https') ? 'wss' : 'ws';
    var host = apiBase.replace(/^https?:\/\//, '');
    var url =
      proto + '://' + host + '/ws/webchat/' +
      encodeURIComponent(orgSlug) + '/' +
      encodeURIComponent(sessionId) + '/?session_token=' +
      encodeURIComponent(sessionToken);

    try {
      ws = new WebSocket(url);
    } catch (e) {
      return;
    }

    ws.onopen = function () { wsReady = true; };
    ws.onmessage = function (ev) {
      try {
        var data = JSON.parse(ev.data);
        if (data.type === 'new_message' && data.message) {
          var msg = data.message;
          if ((msg.role === 'bot' || msg.role === 'agent') && !seenMessageIds[msg.id]) {
            seenMessageIds[msg.id] = true;
            appendMessage('assistant', msg.content, msg.id);
          }
        }
      } catch (e) {}
    };
    ws.onclose = function () {
      wsReady = false;
      setTimeout(function () {
        if (sessionId && sessionToken) connectWS();
      }, 4000);
    };
    ws.onerror = function () { ws.close(); };
  }

  // ── Send message ───────────────────────────────────────────────────────────
  async function sendMessage(text) {
    if (!text || !text.trim()) return;
    appendMessage('user', text, 'user-' + Date.now());
    showTyping(true);

    try {
      var res = await apiFetch('/api/channels/webchat/messages/', {
        method: 'POST',
        body: JSON.stringify({
          organization_slug: orgSlug,
          session_id: sessionId,
          session_token: sessionToken || '',
          message: text,
        }),
      });
      showTyping(false);
      if (res.ok) {
        var payload = await res.json();
        // Fallback: show bot reply from REST if WS not connected
        if (!wsReady && payload.messages) {
          payload.messages.forEach(function (m) {
            if ((m.role === 'bot' || m.role === 'agent') && !seenMessageIds[m.id]) {
              seenMessageIds[m.id] = true;
              appendMessage('assistant', m.content, m.id);
            }
          });
        }
      } else {
        appendMessage('assistant', 'No pude procesar tu mensaje. Intenta de nuevo.', 'err-' + Date.now());
      }
    } catch (e) {
      showTyping(false);
      appendMessage('assistant', 'Sin conexión. Verifica tu internet e intenta de nuevo.', 'err-' + Date.now());
    }
  }

  // ── DOM helpers ────────────────────────────────────────────────────────────
  function appendMessage(role, content, id) {
    if (!messagesDiv) return;
    if (id && seenMessageIds[id]) return;
    if (id) seenMessageIds[id] = true;

    var color = (config && config.brand_color) ? config.brand_color : '#0f766e';
    var row = document.createElement('div');
    row.style.cssText =
      'display:flex;align-items:flex-end;gap:8px;margin-bottom:10px;' +
      (role === 'user' ? 'flex-direction:row-reverse;' : '');

    var bubble = document.createElement('div');
    bubble.style.cssText =
      'max-width:82%;padding:10px 14px;border-radius:18px;font-size:13px;line-height:1.55;word-break:break-word;' +
      (role === 'user'
        ? 'background:' + color + ';color:#fff;border-bottom-right-radius:4px;'
        : 'background:#fff;color:#1a1a1a;border:1px solid rgba(0,0,0,0.09);box-shadow:0 1px 3px rgba(0,0,0,0.07);border-bottom-left-radius:4px;');
    bubble.textContent = content;
    row.appendChild(bubble);
    messagesDiv.appendChild(row);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  }

  function showTyping(show) {
    var existing = messagesDiv ? messagesDiv.querySelector('#vw-typing') : null;
    if (show && !existing && messagesDiv) {
      var el = document.createElement('div');
      el.id = 'vw-typing';
      el.style.cssText = 'display:flex;align-items:center;margin-bottom:10px;';
      el.innerHTML =
        '<div style="display:flex;gap:4px;padding:10px 14px;background:#fff;border-radius:18px;border-bottom-left-radius:4px;border:1px solid rgba(0,0,0,0.09);">' +
        [0, 140, 280].map(function (d) {
          return '<div style="width:6px;height:6px;border-radius:50%;background:#94a3b8;animation:vw-bounce 1s ' + d + 'ms infinite"></div>';
        }).join('') +
        '</div>';
      messagesDiv.appendChild(el);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    } else if (!show && existing) {
      existing.remove();
    }
  }

  // ── Build widget UI ────────────────────────────────────────────────────────
  function buildWidget() {
    var color = (config && config.brand_color) ? config.brand_color : '#0f766e';
    var name = (config && config.widget_name) ? config.widget_name : 'Asistente';
    var label = (config && config.launcher_label) ? config.launcher_label : 'Soporte';
    var greeting = (config && config.greeting_message) ? config.greeting_message : 'Hola. ¿En qué puedo ayudarte?';
    var position = (config && config.position) ? config.position : 'bottom-right';
    var requireConsent = config ? !!config.require_consent : false;

    // Inject keyframe animation
    if (!document.getElementById('vw-styles')) {
      var style = document.createElement('style');
      style.id = 'vw-styles';
      style.textContent =
        '@keyframes vw-bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}' +
        '@keyframes vw-fadein{from{opacity:0;transform:translateY(10px) scale(0.97)}to{opacity:1;transform:translateY(0) scale(1)}}' +
        '#vendly-widget *{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}';
      document.head.appendChild(style);
    }

    // Root container
    container = document.createElement('div');
    container.id = 'vendly-widget';
    var isRight = position.indexOf('left') === -1;
    var isBottom = position.indexOf('top') === -1;
    container.style.cssText =
      'position:fixed;z-index:2147483647;' +
      (isRight ? 'right:20px;' : 'left:20px;') +
      (isBottom ? 'bottom:20px;' : 'top:20px;');

    // ── Chat panel ────────────────────────────────────────────────────────────
    chatPanel = document.createElement('div');
    chatPanel.style.cssText =
      'display:none;flex-direction:column;width:360px;height:520px;max-height:80vh;' +
      'background:#f8fafc;border-radius:20px;overflow:hidden;' +
      'box-shadow:0 8px 48px rgba(0,0,0,0.18);animation:vw-fadein 0.2s ease;margin-bottom:12px;';

    // Header
    var header = document.createElement('div');
    header.style.cssText =
      'background:' + color + ';color:#fff;padding:14px 16px;display:flex;align-items:center;' +
      'justify-content:space-between;flex-shrink:0;';
    header.innerHTML =
      '<div style="display:flex;align-items:center;gap:10px;">' +
      '<div style="width:36px;height:36px;border-radius:50%;background:rgba(255,255,255,0.2);display:flex;align-items:center;justify-content:center;">' +
      '<svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>' +
      '</div>' +
      '<div>' +
      '<div style="font-size:14px;font-weight:700;">' + escapeHtml(name) + '</div>' +
      '<div style="font-size:11px;opacity:0.85;">En línea · Respuesta inmediata</div>' +
      '</div></div>' +
      '<button id="vw-close" style="background:none;border:none;cursor:pointer;color:#fff;padding:6px;border-radius:8px;opacity:0.85;line-height:0;">' +
      '<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">' +
      '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>';

    // Messages area
    messagesDiv = document.createElement('div');
    messagesDiv.id = 'vw-messages';
    messagesDiv.style.cssText =
      'flex:1;overflow-y:auto;padding:16px 14px;display:flex;flex-direction:column;scroll-behavior:smooth;';

    // Input area
    var inputArea = document.createElement('div');
    inputArea.style.cssText =
      'padding:10px 12px;border-top:1px solid rgba(0,0,0,0.07);background:#fff;flex-shrink:0;';
    inputArea.innerHTML =
      '<div style="display:flex;align-items:center;gap:8px;background:#f1f5f9;border-radius:24px;padding:8px 14px;">' +
      '<input id="vw-input" type="text" placeholder="Escribe tu mensaje..." ' +
      'style="flex:1;background:none;border:none;outline:none;font-size:13px;color:#111;min-width:0;" />' +
      '<button id="vw-send" style="background:' + color + ';color:#fff;border:none;border-radius:50%;' +
      'width:32px;height:32px;min-width:32px;display:flex;align-items:center;justify-content:center;cursor:pointer;">' +
      '<svg width="14" height="14" fill="currentColor" viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>' +
      '</button></div>' +
      '<p style="margin:5px 0 0;font-size:10px;color:#94a3b8;text-align:center;">Powered by <strong>Vendly</strong></p>';

    chatPanel.appendChild(header);
    chatPanel.appendChild(messagesDiv);
    chatPanel.appendChild(inputArea);

    // ── Launcher button ───────────────────────────────────────────────────────
    launcherBtn = document.createElement('button');
    launcherBtn.style.cssText =
      'display:flex;align-items:center;gap:8px;background:' + color + ';color:#fff;border:none;cursor:pointer;' +
      'padding:14px 20px;border-radius:28px;box-shadow:0 4px 24px rgba(0,0,0,0.18);' +
      'font-size:14px;font-weight:600;transition:transform 0.15s,box-shadow 0.15s;';
    launcherBtn.innerHTML =
      '<svg width="20" height="20" fill="currentColor" viewBox="0 0 24 24">' +
      '<path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>' +
      '<span>' + escapeHtml(label) + '</span>';
    launcherBtn.addEventListener('mouseover', function () {
      launcherBtn.style.transform = 'scale(1.04)';
      launcherBtn.style.boxShadow = '0 6px 28px rgba(0,0,0,0.22)';
    });
    launcherBtn.addEventListener('mouseout', function () {
      launcherBtn.style.transform = 'scale(1)';
      launcherBtn.style.boxShadow = '0 4px 24px rgba(0,0,0,0.18)';
    });
    launcherBtn.addEventListener('click', openWidget);

    container.appendChild(chatPanel);
    container.appendChild(launcherBtn);
    document.body.appendChild(container);

    // ── Wire events ───────────────────────────────────────────────────────────
    document.getElementById('vw-close').addEventListener('click', closeWidget);

    inputEl = document.getElementById('vw-input');
    document.getElementById('vw-send').addEventListener('click', submitInput);
    inputEl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitInput(); }
    });

    // ── Show initial content ──────────────────────────────────────────────────
    if (requireConsent && !consentGiven) {
      showConsentBanner(color, greeting);
    } else {
      showGreeting(greeting);
    }
  }

  function showConsentBanner(color, greeting) {
    if (!messagesDiv) return;
    var banner = document.createElement('div');
    banner.id = 'vw-consent';
    banner.style.cssText =
      'background:#fff;border-radius:14px;padding:16px;border:1px solid rgba(0,0,0,0.09);' +
      'box-shadow:0 1px 4px rgba(0,0,0,0.07);margin-bottom:12px;font-size:12px;color:#555;';
    banner.innerHTML =
      '<p style="margin:0 0 10px 0;line-height:1.5;">Al continuar, aceptas que esta conversación sea procesada para brindarte soporte.</p>' +
      '<button id="vw-consent-accept" style="background:' + (config && config.brand_color ? config.brand_color : '#0f766e') +
      ';color:#fff;border:none;border-radius:20px;padding:8px 18px;font-size:12px;font-weight:600;cursor:pointer;">' +
      'Entendido, continuar</button>';
    messagesDiv.appendChild(banner);

    document.getElementById('vw-consent-accept').addEventListener('click', function () {
      consentGiven = true;
      var b = document.getElementById('vw-consent');
      if (b) b.remove();
      showGreeting(greeting);
    });
  }

  function showGreeting(greeting) {
    if (greetingShown) return;
    greetingShown = true;
    appendMessage('assistant', greeting, 'vw-greeting');
  }

  function openWidget() {
    isOpen = true;
    chatPanel.style.display = 'flex';
    launcherBtn.style.display = 'none';
    if (inputEl) inputEl.focus();
  }

  function closeWidget() {
    isOpen = false;
    chatPanel.style.display = 'none';
    launcherBtn.style.display = 'flex';
  }

  function submitInput() {
    var text = inputEl ? inputEl.value.trim() : '';
    if (!text) return;
    if (config && config.require_consent && !consentGiven) return;
    inputEl.value = '';
    sendMessage(text);
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Bootstrap ──────────────────────────────────────────────────────────────
  async function init() {
    config = await loadConfig();
    if (!config || !config.is_active) return;

    await initSession();
    buildWidget();
    connectWS();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // ── Public API ─────────────────────────────────────────────────────────────
  window.VendlyWidget = {
    open: openWidget,
    close: closeWidget,
    send: sendMessage,
  };
})(window, document);
