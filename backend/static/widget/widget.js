(function () {
  'use strict';

  // --- Найти script-тег и извлечь параметры ---
  var scripts = document.querySelectorAll('script[data-site-id]');
  var scriptTag = scripts[scripts.length - 1];
  if (!scriptTag) return;

  var SITE_UUID = scriptTag.getAttribute('data-site-id');
  var API_BASE = scriptTag.src.replace(/\/static\/widget\/widget\.js.*$/, '');

  // --- Состояние ---
  var config = null;
  var chatId = null;
  var sessionId = localStorage.getItem('mch_session_' + SITE_UUID) || '';
  var lastMessageId = 0;
  var pollInterval = null;
  var isOpen = false;
  var isMobile = window.innerWidth < 768;
  var pendingFiles = [];

  // --- Утилиты ---
  function generateSessionId() {
    return 'mch_' + Math.random().toString(36).slice(2, 14) + Date.now().toString(36);
  }

  function api(method, path, body) {
    var opts = {
      method: method,
      headers: { 'Content-Type': 'application/json' },
    };
    if (body) opts.body = JSON.stringify(body);
    return fetch(API_BASE + '/api/widget/' + SITE_UUID + path, opts).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function apiFormData(path, formData) {
    return fetch(API_BASE + '/api/widget/' + SITE_UUID + path, {
      method: 'POST',
      body: formData,
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  // --- Загрузить конфиг ---
  function loadConfig() {
    return api('GET', '/config/').then(function (data) {
      config = data;
      return data;
    });
  }

  // --- Нормализовать отступ: значения > 50 считаем устаревшими пикселями, сбрасываем к дефолту ---
  function sanitizeOffset(val, def) {
    if (val == null) return def;
    var n = parseFloat(val);
    if (isNaN(n) || n > 45) return def;
    return n;
  }

  // --- Получить настройки для текущего устройства ---
  function getSettings() {
    if (!config || !config.widget_settings) {
      return {
        primaryColor: '#3b82f6',
        textColor: '#ffffff',
        welcomeMessage: 'Здравствуйте! Чем можем помочь?',
        buttonText: 'Чат',
        position: 'right',
        offsetX: 2,
        offsetY: 2,
      };
    }
    var ws = config.widget_settings;
    var desktop = ws.desktop || {};
    var mobile = ws.mobile || {};

    if (isMobile) {
      if (mobile.show === false) return null;
      return {
        primaryColor: desktop.primaryColor || '#3b82f6',
        textColor: desktop.textColor || '#ffffff',
        welcomeMessage: desktop.welcomeMessage || 'Здравствуйте!',
        buttonText: desktop.buttonText || 'Чат',
        position: mobile.position || desktop.position || 'right',
        offsetX: sanitizeOffset(mobile.offsetX, 2),
        offsetY: sanitizeOffset(mobile.offsetY, 2),
        buttonSize: mobile.buttonSize || 'medium',
        fullscreenChat: mobile.fullscreenChat !== false,
        autoOpen: desktop.autoOpen || false,
        autoOpenDelay: desktop.autoOpenDelay || 5,
        soundEnabled: desktop.soundEnabled !== false,
      };
    }

    return {
      primaryColor: desktop.primaryColor || '#3b82f6',
      textColor: desktop.textColor || '#ffffff',
      welcomeMessage: desktop.welcomeMessage || 'Здравствуйте!',
      buttonText: desktop.buttonText || 'Чат',
      position: desktop.position || 'right',
      offsetX: sanitizeOffset(desktop.offsetX, 2),
      offsetY: sanitizeOffset(desktop.offsetY, 2),
      autoOpen: desktop.autoOpen || false,
      autoOpenDelay: desktop.autoOpenDelay || 5,
      soundEnabled: desktop.soundEnabled !== false,
      buttonSize: 'medium',
      fullscreenChat: false,
    };
  }

  // --- Размеры кнопки ---
  function getButtonDimensions(size) {
    switch (size) {
      case 'small': return { width: 48, height: 48, icon: 20 };
      case 'large': return { width: 72, height: 72, icon: 32 };
      default: return { width: 60, height: 60, icon: 26 };
    }
  }

  // --- Создать Shadow DOM ---
  var host = document.createElement('div');
  host.id = 'multichat-widget-host';
  document.body.appendChild(host);
  var shadow = host.attachShadow({ mode: 'open' });

  // --- Render ---
  function render() {
    var s = getSettings();
    if (!s) {
      shadow.innerHTML = '';
      return;
    }

    var btn = getButtonDimensions(s.buttonSize);
    var hasBtnText = !isMobile && s.buttonText;
    var posStyle = s.position === 'left'
      ? 'left:' + s.offsetX + '%;'
      : 'right:' + s.offsetX + '%;';
    var chatPosStyle = s.position === 'left'
      ? 'left:' + s.offsetX + '%;'
      : 'right:' + s.offsetX + '%;';

    var chatWidth = (isMobile && s.fullscreenChat) ? '100vw' : '380px';
    var chatHeight = (isMobile && s.fullscreenChat) ? '100vh' : '520px';
    var chatBottom = (isMobile && s.fullscreenChat) ? '0' : 'calc(' + s.offsetY + '% + ' + (btn.height + 12) + 'px)';
    var chatPos = (isMobile && s.fullscreenChat)
      ? 'bottom:0;left:0;right:0;top:0;border-radius:0;'
      : 'bottom:' + chatBottom + ';' + chatPosStyle;

    var fabShapeStyle = hasBtnText
      ? 'border-radius:50px;padding:0 ' + Math.round(btn.height / 2) + 'px;height:' + btn.height + 'px;min-width:' + btn.width + 'px;gap:8px;'
      : 'border-radius:50%;width:' + btn.width + 'px;height:' + btn.height + 'px;';

    shadow.innerHTML = '\
<style>\
  *{margin:0;padding:0;box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}\
  .mch-fab{position:fixed;bottom:' + s.offsetY + '%;' + posStyle + fabShapeStyle + '\
    background:' + s.primaryColor + ';color:' + s.textColor + ';border:none;cursor:pointer;\
    display:flex;align-items:center;justify-content:center;box-shadow:0 4px 16px rgba(0,0,0,.2);\
    z-index:2147483646;transition:transform .2s;}\
  .mch-fab:hover{transform:scale(1.08);}\
  .mch-fab svg{width:' + btn.icon + 'px;height:' + btn.icon + 'px;fill:' + s.textColor + ';flex-shrink:0;}\
  .mch-fab-text{font-size:14px;font-weight:600;white-space:nowrap;}\
  .mch-badge{position:absolute;top:-4px;right:-4px;width:18px;height:18px;background:#ef4444;\
    border-radius:50%;display:none;align-items:center;justify-content:center;font-size:11px;color:#fff;}\
  .mch-window{position:fixed;' + chatPos + 'width:' + chatWidth + ';height:' + chatHeight + ';\
    background:#fff;border-radius:16px;box-shadow:0 8px 32px rgba(0,0,0,.18);\
    z-index:2147483647;display:none;flex-direction:column;overflow:hidden;}\
  .mch-window.open{display:flex;}\
  .mch-header{background:' + s.primaryColor + ';color:' + s.textColor + ';padding:16px 20px;display:flex;\
    align-items:center;justify-content:space-between;flex-shrink:0;}\
  .mch-header-title{font-size:16px;font-weight:600;}\
  .mch-header-sub{font-size:12px;opacity:.8;}\
  .mch-close{background:none;border:none;color:' + s.textColor + ';cursor:pointer;font-size:20px;padding:4px;}\
  .mch-body{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:8px;}\
  .mch-msg{max-width:80%;padding:10px 14px;border-radius:16px;font-size:14px;line-height:1.4;word-wrap:break-word;}\
  .mch-msg.client{align-self:flex-end;background:' + s.primaryColor + ';color:' + s.textColor + ';border-bottom-right-radius:4px;}\
  .mch-msg.manager,.mch-msg.system{align-self:flex-start;background:#f1f5f9;color:#1e293b;border-bottom-left-radius:4px;}\
  .mch-msg.system{background:#fef3c7;color:#92400e;font-size:13px;}\
  .mch-time{font-size:10px;opacity:.6;margin-top:4px;}\
  .mch-msg-img{max-width:200px;max-height:160px;border-radius:8px;display:block;margin-top:6px;cursor:pointer;}\
  .mch-msg-file{display:flex;align-items:center;gap:6px;margin-top:6px;padding:6px 10px;\
    border-radius:8px;border:1px solid rgba(0,0,0,.12);text-decoration:none;font-size:12px;\
    color:inherit;background:rgba(0,0,0,.04);}\
  .mch-msg-file:hover{background:rgba(0,0,0,.08);}\
  .mch-file-strip{padding:8px 12px 0;display:flex;gap:8px;flex-wrap:wrap;flex-shrink:0;}\
  .mch-file-preview{position:relative;width:52px;height:52px;}\
  .mch-file-preview img{width:52px;height:52px;object-fit:cover;border-radius:6px;border:1px solid #e2e8f0;}\
  .mch-file-icon{width:52px;height:52px;display:flex;flex-direction:column;align-items:center;\
    justify-content:center;border-radius:6px;border:1px solid #e2e8f0;background:#f8fafc;\
    font-size:10px;color:#64748b;gap:2px;}\
  .mch-file-rm{position:absolute;top:-5px;right:-5px;width:16px;height:16px;background:#ef4444;\
    color:#fff;border:none;border-radius:50%;cursor:pointer;font-size:11px;line-height:1;\
    display:flex;align-items:center;justify-content:center;padding:0;}\
  .mch-footer{padding:12px 16px;border-top:1px solid #e2e8f0;display:flex;gap:8px;align-items:center;flex-shrink:0;}\
  .mch-footer input[type=text]{flex:1;border:1px solid #e2e8f0;border-radius:24px;padding:10px 16px;font-size:14px;outline:none;}\
  .mch-footer input[type=text]:focus{border-color:' + s.primaryColor + ';}\
  .mch-btn-clip{background:none;border:none;cursor:pointer;padding:4px;color:#64748b;display:flex;\
    align-items:center;justify-content:center;flex-shrink:0;}\
  .mch-btn-clip:hover{color:' + s.primaryColor + ';}\
  .mch-btn-send{background:' + s.primaryColor + ';color:' + s.textColor + ';border:none;border-radius:50%;\
    width:40px;height:40px;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;}\
  .mch-btn-send:disabled{opacity:.5;cursor:not-allowed;}\
  .mch-welcome{padding:20px;text-align:center;}\
  .mch-welcome-text{font-size:15px;color:#475569;margin-bottom:16px;}\
  .mch-form{display:flex;flex-direction:column;gap:12px;padding:0 20px 20px;}\
  .mch-form input{border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;font-size:14px;outline:none;}\
  .mch-form input:focus{border-color:' + s.primaryColor + ';}\
  .mch-form button{background:' + s.primaryColor + ';color:' + s.textColor + ';border:none;border-radius:8px;\
    padding:12px;font-size:14px;font-weight:600;cursor:pointer;}\
  .mch-form button:hover{opacity:.9;}\
</style>\
<button class="mch-fab" id="mchFab">\
  <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.2L4 17.2V4h16v12z"/></svg>\
  ' + (hasBtnText ? '<span class="mch-fab-text">' + s.buttonText + '</span>' : '') + '\
  <span class="mch-badge" id="mchBadge">0</span>\
</button>\
<div class="mch-window" id="mchWindow">\
  <div class="mch-header">\
    <div>\
      <div class="mch-header-title">' + (config && config.site_name ? config.site_name : 'Чат поддержки') + '</div>\
      <div class="mch-header-sub">Онлайн</div>\
    </div>\
    <button class="mch-close" id="mchClose">&times;</button>\
  </div>\
  <div class="mch-body" id="mchBody"></div>\
  <div class="mch-file-strip" id="mchFileStrip" style="display:none;"></div>\
  <div class="mch-footer" id="mchFooter" style="display:none;">\
    <input type="file" id="mchFileInput" accept="image/*,.pdf" multiple style="display:none;" />\
    <button class="mch-btn-clip" id="mchClip" title="Прикрепить файл">\
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>\
    </button>\
    <input type="text" id="mchInput" placeholder="Введите сообщение..." />\
    <button class="mch-btn-send" id="mchSend"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg></button>\
  </div>\
</div>';

    // Привязать события
    shadow.getElementById('mchFab').onclick = toggleChat;
    shadow.getElementById('mchClose').onclick = closeChat;

    var input = shadow.getElementById('mchInput');
    var sendBtn = shadow.getElementById('mchSend');
    var clipBtn = shadow.getElementById('mchClip');
    var fileInput = shadow.getElementById('mchFileInput');

    if (clipBtn && fileInput) {
      clipBtn.onclick = function () { fileInput.click(); };
      fileInput.onchange = function (e) {
        var files = Array.from(e.target.files || []);
        files.forEach(function (f) {
          if (pendingFiles.length < 5) pendingFiles.push(f);
        });
        fileInput.value = '';
        renderFileStrip();
      };
    }

    if (input && sendBtn) {
      sendBtn.onclick = function () { sendMsg(); };
      input.onkeydown = function (e) { if (e.key === 'Enter') sendMsg(); };
    }

    if (chatId) {
      showChatView();
    } else {
      showWelcomeForm(s);
    }

    // Greeting bubble (приветственный пузырь рядом с кнопкой)
    if (s.welcomeMessage && !chatId) {
      var bubbleShownKey = 'mch_bubble_' + SITE_UUID;
      if (!sessionStorage.getItem(bubbleShownKey)) {
        setTimeout(function () {
          showGreetingBubble(s.welcomeMessage, s.position);
          sessionStorage.setItem(bubbleShownKey, '1');
        }, 1500);
      }
    }

    // Auto-open — один раз за вкладку, независимо от наличия сессии
    if (s.autoOpen && !isOpen) {
      var autoShownKey = 'mch_autoshown_' + SITE_UUID;
      if (!sessionStorage.getItem(autoShownKey)) {
        setTimeout(function () {
          if (!isOpen) {
            openChat();
            hideGreetingBubble();
            sessionStorage.setItem(autoShownKey, '1');
          }
        }, (s.autoOpenDelay || 5) * 1000);
      }
    }
  }

  // --- Превью прикреплённых файлов ---
  function renderFileStrip() {
    var strip = shadow.getElementById('mchFileStrip');
    if (!strip) return;
    if (!pendingFiles.length) {
      strip.style.display = 'none';
      strip.innerHTML = '';
      return;
    }
    strip.style.display = 'flex';
    strip.innerHTML = '';
    pendingFiles.forEach(function (f, idx) {
      var wrap = document.createElement('div');
      wrap.className = 'mch-file-preview';
      if (f.type.startsWith('image/')) {
        var img = document.createElement('img');
        img.src = URL.createObjectURL(f);
        wrap.appendChild(img);
      } else {
        var icon = document.createElement('div');
        icon.className = 'mch-file-icon';
        var ext = f.name.split('.').pop().toUpperCase().slice(0, 4);
        icon.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="#64748b"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/></svg>' + ext;
        wrap.appendChild(icon);
      }
      var rm = document.createElement('button');
      rm.className = 'mch-file-rm';
      rm.textContent = '×';
      rm.onclick = (function (i) { return function () {
        pendingFiles.splice(i, 1);
        renderFileStrip();
      }; })(idx);
      wrap.appendChild(rm);
      strip.appendChild(wrap);
    });
  }

  // --- Greeting bubble (пузырь рядом с кнопкой) ---
  function showGreetingBubble(text, position) {
    hideGreetingBubble();
    var fab = shadow.getElementById('mchFab');
    if (!fab) return;

    var bubble = document.createElement('div');
    bubble.id = 'mchGreetBubble';
    var isLeft = position === 'left';
    bubble.style.cssText = 'position:fixed;bottom:' + (fab.getBoundingClientRect ? '' : '80px;') +
      'z-index:2147483645;background:#fff;color:#1e293b;border-radius:12px;' +
      'padding:10px 14px;font-size:13px;line-height:1.4;max-width:220px;' +
      'box-shadow:0 4px 20px rgba(0,0,0,.18);cursor:pointer;' +
      'border:1px solid #e2e8f0;animation:mchFadeIn .3s ease;';

    // Позиционируем через JS после вставки
    bubble.textContent = text;

    var closeBtn = document.createElement('span');
    closeBtn.textContent = ' ×';
    closeBtn.style.cssText = 'float:right;margin-left:8px;opacity:.5;font-size:15px;line-height:1;cursor:pointer;';
    closeBtn.onclick = function (e) { e.stopPropagation(); hideGreetingBubble(); };
    bubble.appendChild(closeBtn);

    bubble.onclick = function () { openChat(); hideGreetingBubble(); };

    // Добавляем стиль анимации в shadow если ещё нет
    if (!shadow.getElementById('mchBubbleStyle')) {
      var st = document.createElement('style');
      st.id = 'mchBubbleStyle';
      st.textContent = '@keyframes mchFadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}';
      shadow.appendChild(st);
    }

    shadow.appendChild(bubble);

    // Позиционируем относительно FAB
    requestAnimationFrame(function () {
      var fabEl = shadow.getElementById('mchFab');
      if (!fabEl || !bubble) return;
      var fabRect = fabEl.getBoundingClientRect();
      bubble.style.bottom = (window.innerHeight - fabRect.top + 10) + 'px';
      if (isLeft) {
        bubble.style.left = fabRect.left + 'px';
      } else {
        bubble.style.right = (window.innerWidth - fabRect.right) + 'px';
      }
    });
  }

  function hideGreetingBubble() {
    var b = shadow.getElementById('mchGreetBubble');
    if (b) b.parentNode.removeChild(b);
  }

  // --- Welcome форма ---
  function showWelcomeForm(s) {
    var body = shadow.getElementById('mchBody');
    var footer = shadow.getElementById('mchFooter');
    var strip = shadow.getElementById('mchFileStrip');
    footer.style.display = 'none';
    if (strip) strip.style.display = 'none';

    body.innerHTML = '\
<div class="mch-welcome">\
  <div class="mch-welcome-text">' + (s.welcomeMessage || 'Здравствуйте! Чем можем помочь?') + '</div>\
</div>\
<div class="mch-form">\
  <input type="text" id="mchName" placeholder="Ваше имя" />\
  <input type="email" id="mchEmail" placeholder="Email (для продолжения чата)" />\
  <input type="text" id="mchFirstMsg" placeholder="Ваш вопрос..." />\
  <button id="mchStartBtn">Начать чат</button>\
</div>';

    shadow.getElementById('mchStartBtn').onclick = function () {
      var name = shadow.getElementById('mchName').value.trim();
      var email = shadow.getElementById('mchEmail').value.trim();
      var msg = shadow.getElementById('mchFirstMsg').value.trim();

      if (!name) {
        shadow.getElementById('mchName').style.borderColor = '#ef4444';
        return;
      }

      if (!sessionId) {
        sessionId = generateSessionId();
        localStorage.setItem('mch_session_' + SITE_UUID, sessionId);
      }

      api('POST', '/chat/', {
        client_name: name,
        client_email: email,
        initial_message: msg,
        session_id: sessionId,
      }).then(function (data) {
        chatId = data.id;
        localStorage.setItem('mch_chat_' + SITE_UUID, chatId);
        showChatView();
        loadMessages();
        startPolling();
      }).catch(function (err) {
        console.error('[MultiChat] Ошибка создания чата:', err);
      });
    };
  }

  // --- Chat view ---
  function showChatView() {
    var body = shadow.getElementById('mchBody');
    var footer = shadow.getElementById('mchFooter');
    body.innerHTML = '';
    footer.style.display = 'flex';
  }

  // --- Загрузить сообщения ---
  function loadMessages() {
    if (!chatId) return;
    var afterParam = lastMessageId ? '?after_id=' + lastMessageId : '';
    api('GET', '/chat/' + chatId + '/messages/' + afterParam).then(function (messages) {
      if (!messages.length) return;
      var body = shadow.getElementById('mchBody');
      messages.forEach(function (m) {
        appendMessage(body, m);
        if (m.id > lastMessageId) lastMessageId = m.id;
      });
      body.scrollTop = body.scrollHeight;
    }).catch(function () {});
  }

  function appendMessage(body, m) {
    var div = document.createElement('div');
    div.className = 'mch-msg ' + m.sender_type;
    var time = new Date(m.timestamp);
    var timeStr = time.getHours().toString().padStart(2, '0') + ':' + time.getMinutes().toString().padStart(2, '0');

    var html = '';
    if (m.content) {
      html += '<div>' + escHtml(m.content) + '</div>';
    }
    if (m.files && m.files.length) {
      m.files.forEach(function (f) {
        var rawUrl = f.url || f.file || '';
        var url = rawUrl.startsWith('http') ? rawUrl : API_BASE + rawUrl;
        if (f.mime_type && f.mime_type.startsWith('image/')) {
          html += '<a href="' + url + '" target="_blank"><img class="mch-msg-img" src="' + url + '" alt="' + escHtml(f.filename) + '" /></a>';
        } else {
          html += '<a class="mch-msg-file" href="' + url + '" download="' + escHtml(f.filename) + '" target="_blank">\
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/></svg>\
            ' + escHtml(f.filename) + '</a>';
        }
      });
    }
    html += '<div class="mch-time">' + timeStr + '</div>';
    div.innerHTML = html;
    body.appendChild(div);
  }

  function escHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // --- Отправить сообщение ---
  function sendMsg() {
    var input = shadow.getElementById('mchInput');
    var text = input ? input.value.trim() : '';
    if (!text && !pendingFiles.length) return;
    if (!chatId) return;
    if (input) input.value = '';

    var filesToSend = pendingFiles.slice();
    pendingFiles = [];
    renderFileStrip();

    // Оптимистичное отображение текста (только если нет файлов — иначе API-ответ покажет всё)
    if (text && !filesToSend.length) {
      var body = shadow.getElementById('mchBody');
      appendMessage(body, {
        sender_type: 'client',
        content: text,
        timestamp: new Date().toISOString(),
        id: 0,
        files: [],
      });
      body.scrollTop = body.scrollHeight;
    }

    if (filesToSend.length) {
      var form = new FormData();
      if (text) form.append('content', text);
      filesToSend.forEach(function (f) { form.append('files', f); });
      apiFormData('/chat/' + chatId + '/messages/', form)
        .then(function (msg) {
          if (msg.id > lastMessageId) lastMessageId = msg.id;
          // Refresh to show files
          var body = shadow.getElementById('mchBody');
          appendMessage(body, msg);
          body.scrollTop = body.scrollHeight;
        })
        .catch(function (err) {
          console.error('[MultiChat] Ошибка отправки файла:', err);
        });
    } else {
      api('POST', '/chat/' + chatId + '/messages/', { content: text })
        .then(function (msg) {
          if (msg.id > lastMessageId) lastMessageId = msg.id;
        })
        .catch(function (err) {
          console.error('[MultiChat] Ошибка отправки:', err);
        });
    }
  }

  // --- Polling ---
  function startPolling() {
    if (pollInterval) return;
    pollInterval = setInterval(function () {
      if (!chatId) return;
      var afterParam = lastMessageId ? '?after_id=' + lastMessageId : '';
      api('GET', '/chat/' + chatId + '/messages/' + afterParam).then(function (messages) {
        if (!messages.length) return;
        var body = shadow.getElementById('mchBody');
        var hadNew = false;
        messages.forEach(function (m) {
          if (m.id > lastMessageId) {
            if (m.sender_type !== 'client') {
              appendMessage(body, m);
              hadNew = true;
            }
            lastMessageId = m.id;
          }
        });
        if (hadNew) {
          body.scrollTop = body.scrollHeight;
          if (!isOpen) {
            var badge = shadow.getElementById('mchBadge');
            var count = parseInt(badge.textContent || '0') + 1;
            badge.textContent = count;
            badge.style.display = 'flex';
          }
        }
      }).catch(function () {});
    }, 3000);
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  // --- Открыть / закрыть ---
  function openChat() {
    isOpen = true;
    hideGreetingBubble();
    var win = shadow.getElementById('mchWindow');
    if (win) win.classList.add('open');
    var badge = shadow.getElementById('mchBadge');
    if (badge) {
      badge.style.display = 'none';
      badge.textContent = '0';
    }
  }

  function closeChat() {
    isOpen = false;
    var win = shadow.getElementById('mchWindow');
    if (win) win.classList.remove('open');
  }

  function toggleChat() {
    if (isOpen) closeChat();
    else openChat();
  }

  // --- Восстановление сессии ---
  function restoreSession() {
    var savedChat = localStorage.getItem('mch_chat_' + SITE_UUID);
    if (savedChat && sessionId) {
      chatId = parseInt(savedChat);
      render();
      showChatView();
      loadMessages();
      startPolling();
    } else {
      render();
    }
  }

  // --- Очистка при закрытии страницы ---
  window.addEventListener('beforeunload', stopPolling);

  // --- Реакция на resize (desktop <-> mobile) ---
  window.addEventListener('resize', function () {
    var wasMobile = isMobile;
    isMobile = window.innerWidth < 768;
    if (wasMobile !== isMobile) {
      render();
      if (chatId) {
        showChatView();
        loadMessages();
      }
    }
  });

  // --- Запуск ---
  loadConfig().then(function () {
    restoreSession();
  }).catch(function (err) {
    console.error('[MultiChat] Не удалось загрузить конфиг:', err);
  });

})();
