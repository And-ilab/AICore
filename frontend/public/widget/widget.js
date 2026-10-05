/**
 * Belarusbank online-chat embed widget — UI aligned with canvases/online-chat-mockups
 * «Виджет клиента»: форма входа → диалог → post-chat (оценка + e-mail).
 *
 * Usage:
 *   <script
 *     src="/widget/widget.js"
 *     data-widget-id="site-belarusbank"
 *     data-placement="website"
 *     defer
 *   ></script>
 */
(function (global) {
  'use strict';

  var SCRIPT = document.currentScript;
  var WIDGET_ID =
    (SCRIPT && SCRIPT.getAttribute('data-widget-id')) || 'demo-widget';
  var PLACEMENT =
    (SCRIPT && SCRIPT.getAttribute('data-placement')) || 'website';
    var API_BASE = (function () {
      var attr = SCRIPT && SCRIPT.getAttribute('data-api-base');
      if (attr) return attr.replace(/\/$/, '');
      if (SCRIPT && SCRIPT.src) {
        try {
          return new URL(SCRIPT.src, global.location.href).origin;
        } catch (err) {
          return '';
        }
      }
      return '';
    })();
  var QUERY_PARAMS = new URLSearchParams(global.location.search || '');
  var SIM_CLIENT = QUERY_PARAMS.get('sim_client') || '';
  var RESUME_DIALOG_ID = QUERY_PARAMS.get('dialog_id') || '';
  var LOGO_SRC =
    (SCRIPT && SCRIPT.getAttribute('data-logo-src')) ||
    '/assets/belarusbank-logo.png';
  var LOCALE = 'ru';
  var WIDGET_CONFIG = null;

  /** Palette from online-chat-mockups WIDGET_PALETTE */
  var WP = {
    headerBrand: '#2B6B4A',
    headerNeutral: '#FAFBFA',
    headerAccentLine: '#3A7D5C',
    primary: '#2E7D52',
    primaryHover: '#256B45',
    primaryWeak: '#D4EBDC',
    accent: '#3A7D5C',
    accentMuted: '#4A8B6A',
    clientBubbleBg: '#E8F5EE',
    clientBubbleBorder: '#B8D9C8',
    clientBubbleText: '#1F4D35',
    operatorBubbleBg: '#F5F5F4',
    chatBg: '#F7F9F8',
    footerBg: '#EEF2EF',
    composerBg: '#FAFBFA',
    fabBg: '#2E7D52',
    fabBadge: '#C62828',
    avatarOperator: '#3A7D5C',
    avatarClient: '#B8D9C8',
    stroke: '#D5DBE8',
    text: '#1F2A24',
    textSecondary: '#5A6B62',
    textTertiary: '#7A8A82',
    surface: '#ffffff',
    font: '"Segoe UI",system-ui,-apple-system,sans-serif',
    radius: 12,
    width: 420,
  };

  var STR = {
    fab: 'Онлайн-чат',
    title: 'Онлайн-консультант',
    bank: 'Беларусбанк',
    welcome: 'Здравствуйте! Чем можем помочь?',
    operatorsOnline: 'Операторы онлайн',
    nameLabel: 'Имя',
    namePlaceholder: 'Анна',
    lastNameLabel: 'Фамилия',
    lastNamePlaceholder: 'Козлова',
    phoneLabel: 'Телефон',
    phonePlaceholder: '+375 29 123-45-67',
    questionLabel: 'Задайте Ваш вопрос',
    questionPlaceholder: 'Опишите ваш вопрос…',
    send: 'Отправить',
    placeholder: 'Напишите сообщение…',
    attach: 'Прикрепить файл',
    close: 'Закрыть',
    you: 'Вы',
    operatorName: 'Иванов И.И.',
    operatorShort: 'Иванов',
    operatorRole: 'Оператор поддержки',
    operatorInitials: 'ИИ',
    joined: 'Иванов И.И. подключился к диалогу',
    typing: 'оператор печатает…',
    online: 'в сети',
    waiting: 'Ожидаем ответа оператора…',
    offline: 'Сейчас операторы недоступны. Оставьте сообщение — ответим позже.',
    requiredHint: 'Заполните все поля',
    farewell: 'Спасибо за обращение! Диалог завершён.',
    rateTitle: 'Оцените консультацию',
    rateHint: 'Насколько вы довольны ответом оператора?',
    rateRequired: 'Выберите оценку от 1 до 5 звёзд',
    commentLabel: 'Комментарий',
    commentPlaceholder: 'Расскажите подробнее (необязательно)',
    emailTitle: 'Получить переписку на e-mail',
    emailPlaceholder: 'email@example.com',
    sendTranscript: 'Отправить транскрипт',
    feedbackSaved: 'Спасибо! Оценка сохранена.',
    transcriptSent: 'Переписка отправлена на e-mail.',
    transcriptFailed: 'Не удалось отправить письмо. Проверьте адрес.',
    emailInvalid: 'Введите корректный e-mail',
    dialogClosedHint: 'Диалог завершён. Оставьте оценку, если хотите.',
    clientBlocked: 'Вы заблокированы и не можете начать чат.',
  };

  function cssText() {
    return [
      ':host{all:initial;font-family:' + WP.font + ';}',
      '*{box-sizing:border-box;}',
      '.root{position:fixed;right:20px;bottom:20px;z-index:2147483000;color:' +
        WP.text +
        ';}',
      '.fab{width:60px;height:60px;border:0;border-radius:30px;cursor:pointer;',
      'background:' +
        WP.fabBg +
        ';box-shadow:0 8px 24px rgba(23,32,51,.16);',
      'display:flex;align-items:center;justify-content:center;position:relative;padding:0;overflow:hidden;}',
      '.fab img{width:44px;height:44px;border-radius:8px;object-fit:cover;display:block;}',
      '.fab-badge{position:absolute;top:-2px;right:-2px;min-width:18px;height:18px;border-radius:9px;',
      'padding:0 5px;background:' +
        WP.fabBadge +
        ';color:#fff;font-size:10px;font-weight:600;',
      'display:flex;align-items:center;justify-content:center;}',
      '.fab-badge[hidden]{display:none!important;}',
      '.fab[aria-expanded="true"]{display:none;}',
      '.panel{width:' +
        WP.width +
        'px;max-width:calc(100vw - 24px);min-height:560px;height:min(680px, calc(100vh - 32px));max-height:calc(100vh - 24px);',
      'display:flex;flex-direction:column;overflow:hidden;border-radius:' +
        WP.radius +
        'px;',
      'background:' +
        WP.surface +
        ';border:1px solid ' +
        WP.stroke +
        ';box-shadow:0 12px 40px rgba(15,28,22,.16);}',
      '.panel[hidden]{display:none!important;}',
      '.header{position:relative;display:flex;align-items:center;gap:10px;',
      'padding:14px 16px;padding-right:48px;}',
      '.header--brand{background:' + WP.headerBrand + ';color:#fff;}',
      '.header--neutral{background:' +
        WP.headerNeutral +
        ';border-bottom:2px solid ' +
        WP.headerAccentLine +
        ';}',
      '.header-logo{width:32px;height:32px;border-radius:6px;object-fit:cover;flex-shrink:0;display:block;}',
      '.header-title{font-size:14px;font-weight:600;line-height:1.25;}',
      '.header--brand .header-title{color:#fff;}',
      '.header--neutral .header-title{color:' + WP.headerBrand + ';}',
      '.header-sub{font-size:11px;margin-top:1px;line-height:1.3;}',
      '.header--brand .header-sub{color:#fff;opacity:.92;}',
      '.header--neutral .header-sub{color:' + WP.accentMuted + ';}',
      '.win{position:absolute;top:0;right:0;display:flex;height:100%;}',
      '.win button{width:44px;height:100%;border:0;background:transparent;cursor:pointer;',
      'font-size:18px;line-height:1;padding:0;display:flex;align-items:center;justify-content:center;}',
      '.header--brand .win button{color:rgba(255,255,255,.92);}',
      '.header--neutral .win button{color:' + WP.textSecondary + ';}',
      '.win button:hover{background:rgba(0,0,0,.06);}',
      '.header--brand .win button:hover{background:rgba(255,255,255,.12);}',
      '.prechat{flex:1;min-height:0;overflow:auto;display:flex;flex-direction:column;',
      'padding:20px;gap:14px;background:' + WP.chatBg + ';}',
      '.welcome{font-size:16px;line-height:1.45;font-weight:500;color:' + WP.text + ';}',
      '.pill-online{display:inline-block;align-self:flex-start;font-size:11px;font-weight:600;color:' +
        WP.accentMuted +
        ';background:' +
        WP.primaryWeak +
        ';padding:4px 10px;border-radius:10px;}',
      '[data-form-fields]{display:flex;flex-direction:column;gap:12px;min-width:0;}',
      '.fields{display:grid;grid-template-columns:1fr;gap:12px;}',
      '.fields.is-pair{grid-template-columns:minmax(0,1fr) minmax(0,1fr);}',
      '.field{min-width:0;}',
      '.field label{display:block;font-size:12px;font-weight:600;margin-bottom:6px;color:' +
        WP.text +
        ';}',
      '.field input,.field textarea,.composer input{width:100%;padding:8px 10px;',
      'border:1px solid ' +
        WP.stroke +
        ';border-radius:6px;font:inherit;font-size:13px;background:#fff;color:' +
        WP.text +
        ';resize:vertical;}',
      '.field input{min-height:36px;padding:0 10px;}',
      '.field textarea{min-height:110px;line-height:1.4;}',
      '.field input:focus,.field textarea:focus,.composer input:focus{outline:2px solid ' +
        WP.primaryWeak +
        ';border-color:' +
        WP.primary +
        ';}',
      '.field input.invalid,.field textarea.invalid{border-color:#C62828;outline:2px solid rgba(198,40,40,.18);}',
      '.field-error{font-size:11px;color:#C62828;margin-top:2px;min-height:14px;}',
      '.btn{border:1px solid ' +
        WP.primary +
        ';border-radius:6px;background:' +
        WP.primary +
        ';color:#fff;font:inherit;font-size:13px;font-weight:600;',
      'cursor:pointer;line-height:1.2;padding:8px 14px;}',
      '.btn:hover{background:' + WP.primaryHover + ';border-color:' + WP.primaryHover + ';}',
      '.btn:disabled{opacity:.55;cursor:not-allowed;}',
      '.btn--block{width:100%;margin-top:4px;}',
      '.btn--sm{padding:6px 12px;font-size:12px;flex-shrink:0;}',
      '.op-strip{padding:10px 16px;background:' +
        WP.footerBg +
        ';border-bottom:1px solid ' +
        WP.clientBubbleBorder +
        ';display:flex;align-items:center;gap:8px;}',
      '.op-strip[hidden]{display:none!important;}',
      '.avatar{width:28px;height:28px;border-radius:14px;display:flex;align-items:center;justify-content:center;',
      'font-size:10px;font-weight:600;color:#fff;flex-shrink:0;overflow:hidden;position:relative;}',
      '.avatar--photo{background-color:' +
        WP.avatarOperator +
        ';background-size:cover;background-position:center;background-repeat:no-repeat;}',
      '.avatar--photo img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block;}',
      '.op-meta{flex:1;min-width:0;}',
      '.op-name{font-size:12px;font-weight:600;color:' + WP.text + ';}',
      '.op-role{font-size:11px;color:' + WP.textSecondary + ';}',
      '.op-online{font-size:11px;font-weight:600;color:' +
        WP.accentMuted +
        ';background:' +
        WP.primaryWeak +
        ';padding:3px 8px;border-radius:10px;flex-shrink:0;}',
      '.messages{flex:1;min-height:0;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:12px;',
      'background:' + WP.chatBg + ';}',
      '.sys{text-align:center;font-size:11px;color:' + WP.accentMuted + ';padding:6px 0;}',
      '.waiting{text-align:center;font-size:12px;color:' + WP.textSecondary + ';padding:8px 0 4px;}',
      '.row{display:flex;gap:8px;align-items:flex-end;}',
      '.row--client{justify-content:flex-end;}',
      '.row--operator{justify-content:flex-start;}',
      '.bubble{max-width:78%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.45;}',
      '.bubble--client{background:' +
        WP.clientBubbleBg +
        ';border:1px solid ' +
        WP.clientBubbleBorder +
        ';color:' +
        WP.clientBubbleText +
        ';border-bottom-right-radius:4px;}',
      '.bubble--operator{background:' +
        WP.operatorBubbleBg +
        ';border:1px solid ' +
        WP.stroke +
        ';color:' +
        WP.text +
        ';border-bottom-left-radius:4px;}',
      '.bubble-label{font-size:10px;margin-bottom:4px;}',
      '.bubble--client .bubble-label{color:' + WP.accentMuted + ';}',
      '.bubble--operator .bubble-label{color:' + WP.textTertiary + ';}',
      '.bubble-quote{font-size:11px;color:' +
        WP.textTertiary +
        ';border-left:2px solid ' +
        WP.accentMuted +
        ';padding-left:8px;margin-bottom:6px;line-height:1.35;',
      'max-height:2.7em;overflow:hidden;text-overflow:ellipsis;}',
      '.bubble-file{display:inline-flex;align-items:center;gap:6px;margin-top:8px;padding:6px 10px;border-radius:8px;',
      'border:1px solid ' +
        WP.accentMuted +
        ';background:rgba(0,122,67,0.08);color:' +
        WP.accent +
        ';font-size:12px;font-weight:600;text-decoration:none;cursor:pointer;}',
      '.bubble-file:hover{text-decoration:underline;}',
      '.bubble-file--disabled{opacity:.65;cursor:default;text-decoration:none;}',
      '.bubble-time{font-size:10px;margin-top:6px;text-align:right;display:flex;justify-content:flex-end;align-items:center;gap:2px;}',
      '.bubble--client .bubble-time{color:' + WP.accentMuted + ';}',
      '.bubble--operator .bubble-time{color:' + WP.textTertiary + ';}',
      '.receipt{display:inline-flex;align-items:center;font-size:11px;font-weight:700;line-height:1;color:' +
        WP.accent +
        ';}',
      '.receipt-mark{display:inline-block;}',
      '.receipt-mark + .receipt-mark{margin-left:-6px;}',
      '.typing{display:flex;align-items:center;gap:6px;padding-left:36px;}',
      '.typing[hidden]{display:none!important;}',
      '.typing-dots{display:flex;gap:4px;padding:8px 12px;border-radius:12px;background:' +
        WP.operatorBubbleBg +
        ';border:1px solid ' +
        WP.stroke +
        ';}',
      '.typing-dots span{width:6px;height:6px;border-radius:3px;background:' +
        WP.accentMuted +
        ';display:inline-block;}',
      '.typing-label{font-size:11px;color:' + WP.accentMuted + ';}',
      '.composer{padding:16px;border-top:1px solid ' +
        WP.clientBubbleBorder +
        ';background:' +
        WP.composerBg +
        ';display:flex;flex-wrap:wrap;gap:8px;align-items:center;}',
      '.composer[hidden]{display:none!important;}',
      '.composer-file{display:none;width:100%;align-items:center;gap:8px;padding:6px 10px;border-radius:8px;border:1px solid ' +
        WP.accentMuted +
        ';background:rgba(0,122,67,0.06);font-size:12px;color:' +
        WP.accent +
        ';}',
      '.composer-file.is-visible{display:flex;}',
      '.composer-file button{border:none;background:transparent;color:' +
        WP.textTertiary +
        ';font-size:16px;line-height:1;cursor:pointer;padding:0 2px;}',
      '.icon-btn{width:32px;height:32px;border:1px solid ' +
        WP.stroke +
        ';border-radius:6px;background:' +
        WP.footerBg +
        ';color:' +
        WP.accent +
        ';cursor:pointer;font-size:16px;line-height:1;flex-shrink:0;}',
      '.chat-body{flex:1;min-height:0;display:flex;flex-direction:column;}',
      '.chat-body[hidden],.prechat[hidden],.postchat[hidden]{display:none!important;}',
      '.postchat{flex:1;min-height:0;overflow:auto;display:flex;flex-direction:column;',
      'padding:20px;gap:16px;background:' + WP.chatBg + ';}',
      '.postchat-farewell{font-size:14px;font-weight:600;line-height:1.4;color:' + WP.text + ';}',
      '.postchat-block-title{font-size:13px;font-weight:600;margin-bottom:6px;color:' + WP.text + ';}',
      '.postchat-hint{font-size:12px;color:' + WP.textSecondary + ';margin-bottom:12px;line-height:1.4;}',
      '.stars{display:flex;gap:6px;align-items:center;}',
      '.star{width:36px;height:36px;border:1px solid ' +
        WP.stroke +
        ';border-radius:8px;background:#fff;cursor:pointer;',
      'font-size:18px;line-height:1;color:#C5D0C9;padding:0;transition:color .12s,background .12s,border-color .12s;}',
      '.star.is-lit{background:' +
        WP.primaryWeak +
        ';border-color:' +
        WP.primary +
        ';color:' +
        WP.primary +
        ';}',
      '.star:focus-visible{outline:2px solid ' + WP.primaryWeak + ';}',
      '.postchat-divider{height:1px;background:' + WP.clientBubbleBorder + ';margin:4px 0;}',
      '.btn--secondary{background:#fff;color:' +
        WP.accent +
        ';border-color:' +
        WP.clientBubbleBorder +
        ';}',
      '.btn--secondary:hover{background:' + WP.primaryWeak + ';}',
      '.postchat-status{font-size:12px;color:' + WP.accentMuted + ';min-height:16px;}',
      '.postchat-status--error{color:#C62828;}',
    ].join('');
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatTime(date) {
    var h = date.getHours();
    var m = date.getMinutes();
    return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
  }

  function createWidget() {
    var host = document.createElement('div');
    host.id = 'bb-chat-widget-host';
    host.setAttribute('data-widget-id', WIDGET_ID);
    host.setAttribute('data-placement', PLACEMENT);
    host.setAttribute('data-locale', LOCALE);
    host.setAttribute('data-testid', 'bb-chat-widget');
    document.body.appendChild(host);

    var shadow = host.attachShadow({ mode: 'open' });
    var style = document.createElement('style');
    style.textContent = cssText();
    shadow.appendChild(style);

    var root = document.createElement('div');
    root.className = 'root';
    root.innerHTML =
      '<button type="button" class="fab" aria-expanded="false" aria-controls="bb-widget-panel" data-testid="widget-fab" title="' +
      STR.fab +
      '">' +
      '<img src="' +
      escapeHtml(LOGO_SRC) +
      '" alt="" />' +
      '<span class="fab-badge" aria-hidden="true" hidden></span>' +
      '</button>' +
      '<section class="panel" id="bb-widget-panel" hidden data-testid="widget-panel" role="dialog" aria-label="' +
      STR.title +
      '">' +
      '<header class="header header--brand" data-header>' +
      '<img class="header-logo" src="' +
      escapeHtml(LOGO_SRC) +
      '" alt="Беларусбанк" />' +
      '<div style="flex:1;min-width:0">' +
      '<div class="header-title">' +
      STR.title +
      '</div>' +
      '<div class="header-sub" data-header-sub>' +
      STR.bank +
      '</div>' +
      '</div>' +
      '<div class="win">' +
      '<button type="button" data-action="close" aria-label="' +
      STR.close +
      '" title="' +
      STR.close +
      '">×</button>' +
      '</div>' +
      '</header>' +
      '<div class="prechat" data-view="prechat">' +
      '<div class="welcome">' +
      STR.welcome +
      '</div>' +
      '<span class="pill-online">' +
      STR.operatorsOnline +
      '</span>' +
      '<div data-form-fields></div>' +
      '<div class="field">' +
      '<label for="bb-widget-question">' +
      STR.questionLabel +
      ' *</label>' +
      '<textarea id="bb-widget-question" data-testid="widget-question" placeholder="' +
      STR.questionPlaceholder +
      '" rows="4" required></textarea>' +
      '</div>' +
      '<div class="field-error" data-form-error hidden>' +
      STR.requiredHint +
      '</div>' +
      '<button type="button" class="btn btn--block" data-action="start" data-testid="widget-start">' +
      STR.send +
      '</button>' +
      '</div>' +
      '<div class="chat-body" data-view="chat" hidden>' +
      '<div class="op-strip" data-op-strip hidden>' +
      '<div class="avatar" style="background:' +
      WP.avatarOperator +
      '">' +
      STR.operatorInitials +
      '</div>' +
      '<div class="op-meta"><div class="op-name">' +
      STR.operatorName +
      '</div><div class="op-role">' +
      STR.operatorRole +
      '</div></div>' +
      '<span class="op-online">' +
      STR.online +
      '</span>' +
      '</div>' +
      '<div class="messages" data-testid="widget-messages"></div>' +
      '<div class="composer">' +
      '<div class="composer-file" data-pending-file hidden>' +
      '<span data-pending-file-name></span>' +
      '<button type="button" aria-label="Убрать файл" data-action="clear-file">×</button>' +
      '</div>' +
      '<input type="file" hidden data-file-input aria-hidden="true" tabindex="-1" />' +
      '<button type="button" class="icon-btn" title="' +
      STR.attach +
      '" aria-label="' +
      STR.attach +
      '" data-action="attach">+</button>' +
      '<input type="text" data-testid="widget-input" placeholder="' +
      STR.placeholder +
      '" />' +
      '<button type="button" class="btn btn--sm" data-action="send" data-testid="widget-send">' +
      STR.send +
      '</button>' +
      '</div>' +
      '</div>' +
      '<div class="postchat" data-view="postchat" hidden data-testid="widget-postchat">' +
      '<div class="postchat-farewell" data-farewell>' +
      STR.farewell +
      '</div>' +
      '<div>' +
      '<div class="postchat-block-title">' +
      STR.rateTitle +
      '</div>' +
      '<div class="postchat-hint">' +
      STR.rateHint +
      '</div>' +
      '<div class="stars" role="radiogroup" aria-label="' +
      STR.rateTitle +
      '" data-stars>' +
      [1, 2, 3, 4, 5]
        .map(function (n) {
          return (
            '<button type="button" class="star" data-action="rate" data-rating="' +
            n +
            '" aria-label="' +
            n +
            '" aria-checked="false" data-testid="widget-star-' +
            n +
            '">★</button>'
          );
        })
        .join('') +
      '</div>' +
      '</div>' +
      '<div class="field">' +
      '<label for="bb-widget-comment">' +
      STR.commentLabel +
      '</label>' +
      '<textarea id="bb-widget-comment" data-testid="widget-comment" placeholder="' +
      STR.commentPlaceholder +
      '" rows="3"></textarea>' +
      '</div>' +
      '<div class="postchat-divider"></div>' +
      '<div>' +
      '<div class="postchat-block-title">' +
      STR.emailTitle +
      '</div>' +
      '<div class="field" style="margin-top:8px">' +
      '<input id="bb-widget-email" type="email" data-testid="widget-email" placeholder="' +
      STR.emailPlaceholder +
      '" autocomplete="email" />' +
      '</div>' +
      '<button type="button" class="btn btn--block" data-action="send-transcript" data-testid="widget-send-transcript" style="margin-top:10px">' +
      STR.sendTranscript +
      '</button>' +
      '</div>' +
      '<div class="postchat-status" data-postchat-status data-testid="widget-postchat-status"></div>' +
      '<button type="button" class="btn btn--block btn--secondary" data-action="finish" data-testid="widget-finish">' +
      STR.close +
      '</button>' +
      '</div>' +
      '</section>';

    shadow.appendChild(root);

    var fab = root.querySelector('.fab');
    var panel = root.querySelector('.panel');
    var header = root.querySelector('[data-header]');
    var headerSub = root.querySelector('[data-header-sub]');
    var messagesEl = root.querySelector('[data-testid="widget-messages"]');
    var inputEl = root.querySelector('[data-testid="widget-input"]');
    var fileInputEl = root.querySelector('[data-file-input]');
    var pendingFileEl = root.querySelector('[data-pending-file]');
    var pendingFileNameEl = root.querySelector('[data-pending-file-name]');
    var fabBadgeEl = root.querySelector('.fab-badge');
    var formFieldsEl = root.querySelector('[data-form-fields]');
    var questionEl = root.querySelector('[data-testid="widget-question"]');
    var formErrorEl = root.querySelector('[data-form-error]');
    var opStrip = root.querySelector('[data-op-strip]');
    var composerEl = root.querySelector('.composer');
    var farewellEl = root.querySelector('[data-farewell]');
    var commentEl = root.querySelector('[data-testid="widget-comment"]');
    var emailEl = root.querySelector('[data-testid="widget-email"]');
    var postchatStatusEl = root.querySelector('[data-postchat-status]');
    var starsEl = root.querySelector('[data-stars]');
    if (questionEl) questionEl.required = true;
    var formInputs = {};
    var STORAGE_KEY =
      'bb-chat-dialog-id:' + WIDGET_ID + (SIM_CLIENT ? ':' + SIM_CLIENT : '');
    var state = {
      open: false,
      view: 'prechat',
      started: false,
      closed: false,
      operatorConnected: false,
      clientInitials: 'АК',
      messages: [],
      dialogId: null,
      seenMessageIds: {},
      ws: null,
      rating: 0,
      hoverRating: 0,
      feedbackSaved: false,
      operatorName: STR.operatorName,
      operatorShort: STR.operatorShort,
      operatorInitials: STR.operatorInitials,
      operatorAvatar: '',
      operatorId: '',
      unreadCount: 0,
      typingDebounceTimer: null,
      typingActive: false,
      wsPingTimer: null,
      catchUpTimer: null,
      pendingFile: null,
    };

    function normalizeFieldKey(key) {
      key = String(key || '').trim().toLowerCase();
      if (key === 'first_name' || key === 'fio') return 'name';
      if (key === 'tel' || key === 'telephone' || key === 'mobile') return 'phone';
      return key;
    }

    function defaultFormFields() {
      return [
        { key: 'name', label: STR.nameLabel, type: 'text', required: true },
        { key: 'phone', label: STR.phoneLabel, type: 'tel', required: true },
      ];
    }

    function resolveFormFields() {
      var raw =
        WIDGET_CONFIG && Array.isArray(WIDGET_CONFIG.form_fields)
          ? WIDGET_CONFIG.form_fields
          : null;
      if (!raw) return defaultFormFields();
      var fields = [];
      var seen = {};
      raw.forEach(function (field) {
        if (!field || !field.key) return;
        var key = normalizeFieldKey(field.key);
        if (!key || key === 'question' || seen[key]) return;
        seen[key] = true;
        fields.push({
          key: key,
          label: String(field.label || key),
          type: String(
            field.type ||
              (key === 'phone' ? 'tel' : key === 'email' ? 'email' : 'text'),
          ),
          required: Boolean(field.required),
        });
      });
      return fields;
    }

    function inputTypeFor(field) {
      if (field.type === 'tel' || field.key === 'phone') return 'tel';
      if (field.type === 'email' || field.key === 'email') return 'email';
      return 'text';
    }

    function autocompleteFor(key) {
      if (key === 'name') return 'given-name';
      if (key === 'last_name') return 'family-name';
      if (key === 'phone') return 'tel';
      if (key === 'email') return 'email';
      return 'on';
    }

    function rebuildFormFields() {
      if (!formFieldsEl) return;
      formInputs = {};
      formFieldsEl.innerHTML = '';
      var fields = resolveFormFields();

      function mountField(field, parent) {
        var wrap = document.createElement('div');
        wrap.className = 'field';
        var id = 'bb-widget-field-' + field.key;
        var label = document.createElement('label');
        label.setAttribute('for', id);
        label.textContent = field.label + (field.required ? ' *' : '');
        var input = document.createElement('input');
        input.id = id;
        input.type = inputTypeFor(field);
        input.setAttribute('data-testid', 'widget-' + field.key.replace(/_/g, '-'));
        input.setAttribute('data-form-key', field.key);
        input.autocomplete = autocompleteFor(field.key);
        input.required = Boolean(field.required);
        if (field.key === 'phone') input.placeholder = STR.phonePlaceholder;
        wrap.appendChild(label);
        wrap.appendChild(input);
        parent.appendChild(wrap);
        formInputs[field.key] = input;
        input.addEventListener('input', function () {
          input.classList.remove('invalid');
          if (formErrorEl) formErrorEl.setAttribute('hidden', '');
        });
        return input;
      }

      var i = 0;
      while (i < fields.length) {
        var current = fields[i];
        var next = fields[i + 1];
        var pairWithName =
          current &&
          next &&
          ((current.key === 'name' && next.key === 'last_name') ||
            (current.key === 'last_name' && next.key === 'name'));
        if (pairWithName) {
          var row = document.createElement('div');
          row.className = 'fields is-pair';
          mountField(current, row);
          mountField(next, row);
          formFieldsEl.appendChild(row);
          i += 2;
          continue;
        }
        mountField(current, formFieldsEl);
        i += 1;
      }
    }

    rebuildFormFields();

    if (SIM_CLIENT) {
      var simNumber = Number(String(SIM_CLIENT).replace(/\D/g, '')) || 1;
      if (formInputs.name) formInputs.name.value = 'Клиент';
      if (formInputs.last_name) formInputs.last_name.value = String(simNumber);
      if (formInputs.phone) {
        formInputs.phone.value =
          '+375 29 ' + String(1000000 + simNumber).slice(-7);
      }
      questionEl.value =
        'Тестовое обращение клиента ' + simNumber + ': нужна консультация.';
    }

    if (WIDGET_CONFIG && WIDGET_CONFIG.offline_message) {
      STR.offline = WIDGET_CONFIG.offline_message;
    }

    function apiUrl(path) {
      var base = (API_BASE || '').replace(/\/$/, '');
      return base + path;
    }

    /** Stable HTTP URL for operator photo (works with data URLs stored server-side). */
    function operatorPhotoApiUrl(operatorId) {
      if (!operatorId) return '';
      var id = String(operatorId);
      return apiUrl(
        '/api/v1/online-chat/operators/' +
          encodeURIComponent(id) +
          '/photo/?v=' +
          encodeURIComponent(id),
      );
    }

    function operatorIdFromAvatarPath(path) {
      var match = String(path || '').match(
        /\/operators\/([0-9a-fA-F-]{36})\/photo\/?/,
      );
      return match ? match[1] : '';
    }

    function resolveMediaUrl(path) {
      if (!path) return '';
      var value = String(path);
      if (
        value.indexOf('data:') === 0 ||
        value.indexOf('http://') === 0 ||
        value.indexOf('https://') === 0
      ) {
        return value;
      }
      if (value.charAt(0) === '/') return apiUrl(value);
      return value;
    }

    function resolveOperatorAvatarSources(message, dialog) {
      var inline =
        (message && message.operator_avatar) ||
        (dialog && dialog.operator_avatar) ||
        '';
      var operatorId =
        (message && message.operator_id) ||
        (dialog && dialog.operator_id) ||
        state.operatorId ||
        operatorIdFromAvatarPath(inline) ||
        '';
      var photoApi = operatorId ? operatorPhotoApiUrl(operatorId) : '';
      if (photoApi) {
        var fallback = inline && String(inline).indexOf('data:') !== 0
          ? resolveMediaUrl(inline)
          : '';
        return { url: photoApi, fallback: fallback === photoApi ? '' : fallback };
      }
      if (inline && String(inline).indexOf('data:') === 0) {
        return { url: inline, fallback: '' };
      }
      return { url: resolveMediaUrl(inline), fallback: '' };
    }

    function resolveOperatorAvatarUrl(message, dialog) {
      return resolveOperatorAvatarSources(message, dialog).url;
    }

    /**
     * Avatar for a bank employee (operator/supervisor) bubble or the op-strip header.
     * Always renders something: employee initials by default and photo when available.
     */
    function createOperatorAvatarNode(url, initials, fallbackUrl) {
      var wrap = document.createElement('div');
      wrap.className = 'avatar avatar--photo';
      var fallbackInitials = String(initials || STR.operatorInitials || 'О')
        .trim()
        .slice(0, 2)
        .toUpperCase();
      var label = document.createElement('span');
      label.textContent = fallbackInitials;
      wrap.appendChild(label);
      if (!url) {
        return wrap;
      }
      function cssUrl(src) {
        return 'url(' + JSON.stringify(String(src)) + ')';
      }
      function showPhoto(src) {
        wrap.style.backgroundImage = cssUrl(src);
        if (label.parentNode) label.remove();
      }
      function clearPhoto() {
        wrap.style.backgroundImage = '';
        var existing = wrap.querySelector('img');
        if (existing) existing.remove();
        if (!label.parentNode) wrap.appendChild(label);
      }
      function mountPhoto(src, nextFallback) {
        showPhoto(src);
        var img = document.createElement('img');
        img.alt = '';
        img.decoding = 'async';
        img.onload = function () {
          showPhoto(src);
        };
        img.onerror = function () {
          if (img.parentNode) img.remove();
          if (nextFallback && nextFallback !== src) {
            mountPhoto(nextFallback, '');
            return;
          }
          clearPhoto();
        };
        wrap.appendChild(img);
        img.src = src;
        if (img.complete && img.naturalWidth) {
          showPhoto(src);
        }
      }
      mountPhoto(url, fallbackUrl && fallbackUrl !== url ? fallbackUrl : '');
      return wrap;
    }

    function wsUrl(path) {
      var base = (API_BASE || '').replace(/\/$/, '');
      if (base) {
        try {
          var u = new URL(base);
          var proto = u.protocol === 'https:' ? 'wss:' : 'ws:';
          return proto + '//' + u.host + path;
        } catch (err) {
          /* fall through */
        }
      }
      var pageProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      return pageProto + '//' + window.location.host + path;
    }

    function persistDialogId(id) {
      try {
        if (id) sessionStorage.setItem(STORAGE_KEY, id);
        else sessionStorage.removeItem(STORAGE_KEY);
      } catch (err) {
        /* private mode */
      }
    }

    function readPersistedDialogId() {
      try {
        return sessionStorage.getItem(STORAGE_KEY) || null;
      } catch (err) {
        return null;
      }
    }

    function renderFabBadge() {
      if (!fabBadgeEl) return;
      if (state.unreadCount > 0) {
        fabBadgeEl.textContent =
          state.unreadCount > 9 ? '9+' : String(state.unreadCount);
        fabBadgeEl.removeAttribute('hidden');
      } else {
        fabBadgeEl.textContent = '';
        fabBadgeEl.setAttribute('hidden', '');
      }
    }

    function setOpen(open) {
      state.open = open;
      fab.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) {
        panel.removeAttribute('hidden');
        state.unreadCount = 0;
        renderFabBadge();
        scheduleMarkMessagesReadAsClient();
      } else {
        panel.setAttribute('hidden', '');
      }
    }

    function sendWsMessage(payload) {
      if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
      try {
        state.ws.send(JSON.stringify(payload));
      } catch (err) {
        /* ignore */
      }
    }

    function stopWsPing() {
      if (state.wsPingTimer) {
        clearInterval(state.wsPingTimer);
        state.wsPingTimer = null;
      }
    }

    function startWsPing() {
      stopWsPing();
      state.wsPingTimer = setInterval(function () {
        sendWsMessage({ type: 'ping' });
      }, 25000);
    }

    function sendTypingStop() {
      if (state.typingDebounceTimer) {
        clearTimeout(state.typingDebounceTimer);
        state.typingDebounceTimer = null;
      }
      if (!state.typingActive) return;
      state.typingActive = false;
      sendWsMessage({ type: 'typing.stop', speaker: 'client' });
    }

    function scheduleClientTyping(draft) {
      if (state.typingDebounceTimer) {
        clearTimeout(state.typingDebounceTimer);
        state.typingDebounceTimer = null;
      }
      var value = String(draft || '');
      if (
        !value ||
        !state.dialogId ||
        state.view !== 'chat' ||
        state.closed ||
        !state.open
      ) {
        sendTypingStop();
        return;
      }
      state.typingDebounceTimer = setTimeout(function () {
        state.typingDebounceTimer = null;
        state.typingActive = true;
        sendWsMessage({
          type: 'typing.start',
          speaker: 'client',
          draft: value,
        });
      }, 300);
    }

    function setComposerEnabled(enabled) {
      if (!composerEl) return;
      if (enabled) composerEl.removeAttribute('hidden');
      else composerEl.setAttribute('hidden', '');
      inputEl.disabled = !enabled;
    }

    function setPostchatStatus(text, isError) {
      if (!postchatStatusEl) return;
      postchatStatusEl.textContent = text || '';
      if (isError) postchatStatusEl.classList.add('postchat-status--error');
      else postchatStatusEl.classList.remove('postchat-status--error');
    }

    function renderStars() {
      if (!starsEl) return;
      var lit = state.hoverRating || state.rating;
      starsEl.querySelectorAll('.star').forEach(function (btn) {
        var value = Number(btn.getAttribute('data-rating') || 0);
        var on = lit > 0 && value <= lit;
        btn.setAttribute('aria-checked', on ? 'true' : 'false');
        if (on) btn.classList.add('is-lit');
        else btn.classList.remove('is-lit');
      });
    }

    function showView(view) {
      state.view = view;
      state.started = view === 'chat' || view === 'postchat';
      root.querySelectorAll('[data-view]').forEach(function (node) {
        var nodeView = node.getAttribute('data-view');
        if (nodeView === view) node.removeAttribute('hidden');
        else node.setAttribute('hidden', '');
      });
      if (view === 'prechat') {
        header.classList.add('header--brand');
        header.classList.remove('header--neutral');
      } else {
        header.classList.remove('header--brand');
        header.classList.add('header--neutral');
      }
      headerSub.textContent = STR.bank;
      setComposerEnabled(view === 'chat' && !state.closed);
    }

    function showChat(started) {
      showView(started ? 'chat' : 'prechat');
    }

    function showPostchat(farewellMessage) {
      state.closed = true;
      setComposerEnabled(false);
      if (farewellEl) {
        farewellEl.textContent = farewellMessage || STR.farewell;
      }
      if (commentEl) commentEl.value = '';
      if (emailEl) emailEl.value = '';
      state.rating = 0;
      state.hoverRating = 0;
      state.feedbackSaved = false;
      renderStars();
      setPostchatStatus('');
      showView('postchat');
      setOpen(true);
      closeDialogSocket();
    }

    function initialsFromName(name) {
      var parts = String(name || '')
        .trim()
        .split(/\s+/)
        .filter(Boolean);
      if (!parts.length) return 'АК';
      return parts
        .map(function (p) {
          return p.charAt(0);
        })
        .join('')
        .slice(0, 2)
        .toUpperCase();
    }

    function addSystem(text) {
      state.messages.push({ speaker: 'system', text: text });
      var el = document.createElement('div');
      el.className = 'sys';
      el.textContent = text;
      messagesEl.appendChild(el);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function setWaitingHint(show) {
      var existing = messagesEl.querySelector('.waiting');
      if (existing) existing.remove();
      if (!show) return;
      var el = document.createElement('div');
      el.className = 'waiting';
      el.textContent = STR.waiting;
      messagesEl.appendChild(el);
    }

    function receiptHtml(status) {
      if (!status) return '';
      var double = status === 'read';
      return (
        '<span class="receipt" data-receipt aria-label="' +
        (double ? 'Прочитано' : 'Доставлено') +
        '" title="' +
        (double ? 'Прочитано' : 'Доставлено') +
        '">' +
        '<span class="receipt-mark">✓</span>' +
        (double ? '<span class="receipt-mark">✓</span>' : '') +
        '</span>'
      );
    }

    function attachmentDownloadUrl(dialogId, messageId) {
      return apiUrl(
        '/api/v1/online-chat/dialogs/' + dialogId + '/attachments/' + messageId + '/',
      );
    }

    function canDownloadMessageAttachment(message) {
      if (!message || message.is_deleted || !message.attachment_name) return false;
      if (!message.attachment_key) return false;
      var status = message.attachment_scan_status || 'not_required';
      return status === 'clean' || status === 'not_required';
    }

    function captionForMessage(text, attachmentName) {
      if (!attachmentName) return text || '';
      var fileLabel = 'Файл: ' + attachmentName;
      if (!text || text === fileLabel) return '';
      return text;
    }

    function downloadAttachmentBlob(dialogId, messageId, filename) {
      return fetch(attachmentDownloadUrl(dialogId, messageId), {
        credentials: 'include',
      }).then(function (response) {
        if (!response.ok) throw new Error('download_failed');
        return response.blob().then(function (blob) {
          var objectUrl = URL.createObjectURL(blob);
          var link = document.createElement('a');
          link.href = objectUrl;
          link.download = filename || 'attachment';
          document.body.appendChild(link);
          link.click();
          link.remove();
          URL.revokeObjectURL(objectUrl);
        });
      });
    }

    function addBubble(speaker, text, label, initials, time, options) {
      options = options || {};
      var messageId = options.id || '';
      var receiptStatus = options.receiptStatus || '';
      var attachmentName = options.attachmentName || '';
      var attachmentDownloadable = !!options.attachmentDownloadable;
      var displayText = captionForMessage(text, attachmentName);
      state.messages.push({
        speaker: speaker,
        text: text,
        id: messageId,
        receiptStatus: receiptStatus,
        attachmentName: attachmentName,
      });
      var isClient = speaker === 'client';
      var row = document.createElement('div');
      row.className = 'row row--' + (isClient ? 'client' : 'operator');
      if (messageId) row.setAttribute('data-message-id', messageId);

      var avatarHtml = isClient
        ? '<div class="avatar" style="background:' +
          WP.avatarClient +
          ';color:' +
          WP.clientBubbleText +
          '">' +
          escapeHtml(initials || state.clientInitials) +
          '</div>'
        : '';

      var timeBlock = time
        ? '<div class="bubble-time">' +
          escapeHtml(time) +
          (isClient ? receiptHtml(receiptStatus || 'delivered') : '') +
          '</div>'
        : '';

      var quotedText = options.quotedText || '';
      var quoteBlock = quotedText
        ? '<div class="bubble-quote">' + escapeHtml(quotedText) + '</div>'
        : '';

      var fileBlock = '';
      if (attachmentName) {
        if (attachmentDownloadable && messageId && state.dialogId) {
          fileBlock =
            '<button type="button" class="bubble-file" data-attachment-download="' +
            escapeHtml(messageId) +
            '" data-attachment-name="' +
            escapeHtml(attachmentName) +
            '">📎 Скачать: ' +
            escapeHtml(attachmentName) +
            '</button>';
        } else {
          fileBlock =
            '<span class="bubble-file bubble-file--disabled">📎 ' +
            escapeHtml(attachmentName) +
            '</span>';
        }
      }

      var textBlock = displayText
        ? '<div data-bubble-text>' + escapeHtml(displayText) + '</div>'
        : '<div data-bubble-text></div>';

      var bubble =
        '<div class="bubble bubble--' +
        (isClient ? 'client' : 'operator') +
        '">' +
        '<div class="bubble-label">' +
        escapeHtml(
          options.operatorLabel ||
            label ||
            (isClient ? STR.you : state.operatorShort),
        ) +
        '</div>' +
        quoteBlock +
        textBlock +
        fileBlock +
        timeBlock +
        '</div>';

      if (isClient) {
        row.innerHTML = bubble + avatarHtml;
      } else {
        row.innerHTML = bubble;
        // Bot ("Виртуальный помощник") keeps its current no-avatar look — the
        // silhouette fallback is only for real bank employees (operators/supervisors).
        if (!options.isBot) {
          var operatorAvatarNode = createOperatorAvatarNode(
            options.avatarUrl || '',
            options.operatorInitials || initialsFromName(options.operatorLabel || state.operatorName),
            options.avatarFallbackUrl || '',
          );
          row.insertBefore(operatorAvatarNode, row.firstChild);
        }
      }
      var downloadBtn = row.querySelector('[data-attachment-download]');
      if (downloadBtn) {
        downloadBtn.addEventListener('click', function () {
          var id = downloadBtn.getAttribute('data-attachment-download');
          var name = downloadBtn.getAttribute('data-attachment-name') || 'attachment';
          if (!id || !state.dialogId) return;
          downloadAttachmentBlob(state.dialogId, id, name).catch(function () {
            addSystem('Не удалось скачать файл.');
          });
        });
      }
      messagesEl.appendChild(row);
      messagesEl.scrollTop = messagesEl.scrollHeight;
      return row;
    }

    function attachmentOptionsFromMessage(message) {
      if (!message || !message.attachment_name) return {};
      return {
        attachmentName: message.attachment_name,
        attachmentDownloadable: canDownloadMessageAttachment(message),
      };
    }

    function setMessageReceipt(messageId, status) {
      if (!messageId) return;
      var row = messagesEl.querySelector('[data-message-id="' + messageId + '"]');
      if (!row) return;
      var receipt = row.querySelector('[data-receipt]');
      if (!receipt) return;
      receipt.setAttribute('aria-label', status === 'read' ? 'Прочитано' : 'Доставлено');
      receipt.setAttribute('title', status === 'read' ? 'Прочитано' : 'Доставлено');
      receipt.innerHTML =
        '<span class="receipt-mark">✓</span>' +
        (status === 'read' ? '<span class="receipt-mark">✓</span>' : '');
      state.messages.forEach(function (item) {
        if (item.id === messageId) item.receiptStatus = status;
      });
    }

    function applyRemoteMessageUpdate(message) {
      if (!message || !message.id) return;
      var row = messagesEl.querySelector(
        '[data-message-id="' + message.id + '"]',
      );
      if (!row) return;
      var bubble = row.querySelector('.bubble');
      if (!bubble) return;
      var bodyEl = bubble.querySelector('[data-bubble-text]');
      var quoteEl = bubble.querySelector('.bubble-quote');
      var editedEl = bubble.querySelector('[data-edited]');
      var receipt = bubble.querySelector('[data-receipt]');
      var displayText = message.is_deleted
        ? 'Сообщение удалено'
        : message.text || '';
      if (bodyEl) {
        bodyEl.textContent = displayText;
        if (message.is_deleted) {
          bodyEl.style.fontStyle = 'italic';
          bodyEl.style.opacity = '0.75';
        } else {
          bodyEl.style.fontStyle = '';
          bodyEl.style.opacity = '';
        }
      }
      if (message.quoted_text) {
        if (!quoteEl) {
          quoteEl = document.createElement('div');
          quoteEl.className = 'bubble-quote';
          bubble.insertBefore(quoteEl, bodyEl || bubble.firstChild);
        }
        quoteEl.textContent = message.quoted_text;
        quoteEl.removeAttribute('hidden');
      } else if (quoteEl) {
        quoteEl.setAttribute('hidden', '');
      }
      if (message.is_deleted) {
        if (receipt) receipt.remove();
        if (editedEl) editedEl.remove();
      } else if (message.edited_at) {
        if (!editedEl) {
          var timeEl = bubble.querySelector('.bubble-time');
          editedEl = document.createElement('span');
          editedEl.setAttribute('data-edited', '1');
          editedEl.style.fontStyle = 'italic';
          editedEl.style.marginRight = '4px';
          editedEl.textContent = 'изм.';
          if (timeEl) timeEl.insertBefore(editedEl, timeEl.firstChild);
        }
      }
      if (!message.is_deleted && message.receipt_status && receipt) {
        setMessageReceipt(message.id, message.receipt_status);
      }
      state.messages.forEach(function (item) {
        if (item.id !== message.id) return;
        item.text = displayText;
        item.receiptStatus = message.receipt_status || item.receiptStatus;
        item.isDeleted = !!message.is_deleted;
      });
    }

    function markMessagesReadAsClient(options) {
      options = options || {};
      if (!state.dialogId || state.closed) return;
      // While the chat panel is open, treat messages as read even if the browser
      // tab is briefly not focused (visibilityState=hidden).
      if (!state.open && !options.force) return;
      fetch(apiUrl('/api/v1/online-chat/dialogs/' + state.dialogId + '/read/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reader: 'client' }),
      }).catch(function () {});
    }

    function scheduleMarkMessagesReadAsClient() {
      markMessagesReadAsClient();
      // Retry covers WS-vs-DB races so ARM gets ✓✓ without a widget refresh.
      window.setTimeout(function () {
        markMessagesReadAsClient();
      }, 120);
      window.setTimeout(function () {
        markMessagesReadAsClient();
      }, 400);
    }

    function shortNameFromFull(name) {
      var cleaned = String(name || '').trim();
      if (!cleaned) return STR.operatorShort;
      return cleaned.split(/\s+/)[0] || STR.operatorShort;
    }

    function applyOperatorIdentity(name, avatar, operatorId) {
      var full = String(name || '').trim() || STR.operatorName;
      state.operatorName = full;
      state.operatorShort = shortNameFromFull(full);
      state.operatorInitials = initialsFromName(full);
      var sources = resolveOperatorAvatarSources(
        {
          operator_id: operatorId || '',
          operator_avatar: typeof avatar === 'string' ? avatar : '',
        },
        null,
      );
      state.operatorAvatar = sources.url;
      state.operatorId = operatorId || state.operatorId || '';
      var nameNode = opStrip.querySelector('.op-name');
      if (nameNode) nameNode.textContent = full;
      var existingAvatar = opStrip.querySelector('.avatar');
      if (existingAvatar) existingAvatar.remove();
      var avatarNode = createOperatorAvatarNode(
        sources.url,
        state.operatorInitials,
        sources.fallback,
      );
      if (avatarNode) {
        var meta = opStrip.querySelector('.op-meta');
        if (meta) opStrip.insertBefore(avatarNode, meta);
        else opStrip.insertBefore(avatarNode, opStrip.firstChild);
      }
    }

    /** Call when operator joins the dialog (API/WS or demo hook). */
    function connectOperator(operatorName, options) {
      options = options || {};
      applyOperatorIdentity(
        operatorName || state.operatorName,
        options.avatar,
        options.operatorId || options.operator_id || '',
      );
      if (state.operatorConnected) return;
      state.operatorConnected = true;
      stopCatchUpPolling();
      setWaitingHint(false);
      opStrip.removeAttribute('hidden');
      if (options.announce !== false) {
        addSystem(state.operatorName + ' подключился к диалогу');
      }
    }

    /** Show/hide typing indicator. */
    function showTyping(show) {
      var existing = messagesEl.querySelector('.typing');
      if (existing) existing.remove();
      if (!show) return;
      var el = document.createElement('div');
      el.className = 'typing';
      el.innerHTML =
        '<div class="typing-dots"><span></span><span></span><span></span></div>' +
        '<span class="typing-label">' +
        STR.typing +
        '</span>';
      messagesEl.appendChild(el);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function rememberMessageId(id) {
      if (!id) return;
      state.seenMessageIds[id] = true;
    }

    function handleRemoteMessage(message) {
      if (!message || !message.id || state.seenMessageIds[message.id]) return;
      rememberMessageId(message.id);
      if (message.speaker === 'system') {
        addSystem(message.text);
        return;
      }
        if (message.speaker === 'operator' || message.speaker === 'bot') {
        if (message.speaker === 'operator') {
          setWaitingHint(false);
        }
        var avatarSources =
          message.speaker === 'bot'
            ? { url: '', fallback: '' }
            : resolveOperatorAvatarSources(message, {
                operator_id: state.operatorId,
                operator_avatar: state.operatorAvatar || '',
              });
        if (
          message.speaker === 'operator' &&
          !state.operatorConnected
        ) {
          connectOperator(message.operator_name || state.operatorName, {
            announce: false,
            avatar: message.operator_avatar || '',
            operatorId: message.operator_id || '',
          });
        }
        var remoteOperatorName =
          message.speaker === 'operator'
            ? message.operator_name || state.operatorName
            : state.operatorName;
        addBubble(
          'operator',
          message.text,
          message.speaker === 'bot'
            ? 'Виртуальный помощник'
            : shortNameFromFull(remoteOperatorName),
          message.speaker === 'bot' ? 'Б' : initialsFromName(remoteOperatorName),
          formatTime(new Date(message.created_at || Date.now())),
          Object.assign(
            {
              id: message.id,
              receiptStatus: message.receipt_status,
              quotedText: message.quoted_text,
              avatarUrl: avatarSources.url,
              avatarFallbackUrl: avatarSources.fallback,
              isBot: message.speaker === 'bot',
              operatorLabel:
                message.speaker === 'bot'
                  ? 'Виртуальный помощник'
                  : shortNameFromFull(remoteOperatorName),
              operatorInitials:
                message.speaker === 'bot' ? '' : initialsFromName(remoteOperatorName),
            },
            attachmentOptionsFromMessage(message),
          ),
        );
        if (!state.open) {
          state.unreadCount += 1;
          renderFabBadge();
        }
        scheduleMarkMessagesReadAsClient();
        return;
      }
      if (message.speaker === 'client') {
        /* Local client bubbles are already rendered; attach id if missing. */
        if (message.id) {
          var orphan = messagesEl.querySelector(
            '.row--client:not([data-message-id])',
          );
          if (orphan) {
            orphan.setAttribute('data-message-id', message.id);
            setMessageReceipt(message.id, message.receipt_status || 'delivered');
          }
        }
        return;
      }
    }

    function closeDialogSocket() {
      sendTypingStop();
      stopWsPing();
      stopCatchUpPolling();
      if (state.ws) {
        try {
          state.ws.close();
        } catch (err) {
          /* ignore */
        }
        state.ws = null;
      }
    }

    function catchUpDialogMessages() {
      if (!state.dialogId) return;
      fetch(apiUrl('/api/v1/online-chat/dialogs/' + state.dialogId + '/'))
        .then(function (response) {
          return response.json();
        })
        .then(function (body) {
          if (!body || !body.ok || !body.dialog) return;
          var messages = body.dialog.messages || [];
          messages.forEach(function (message) {
            if (message && message.is_history) return;
            handleRemoteMessage(message);
          });
          if (
            body.dialog.status === 'active' &&
            body.dialog.operator_name &&
            !state.operatorConnected
          ) {
            connectOperator(body.dialog.operator_name, {
              announce: false,
              avatar: body.dialog.operator_avatar || '',
              operatorId: body.dialog.operator_id || '',
            });
          }
        })
        .catch(function () {});
    }

    function stopCatchUpPolling() {
      if (state.catchUpTimer) {
        clearInterval(state.catchUpTimer);
        state.catchUpTimer = null;
      }
    }

    function startCatchUpPolling() {
      stopCatchUpPolling();
      var attempts = 0;
      state.catchUpTimer = setInterval(function () {
        attempts += 1;
        if (
          state.operatorConnected ||
          state.closed ||
          !state.dialogId ||
          attempts > 30
        ) {
          stopCatchUpPolling();
          return;
        }
        catchUpDialogMessages();
      }, 2000);
    }

    function connectDialogSocket(dialogId) {
      closeDialogSocket();
      if (!dialogId || typeof WebSocket === 'undefined') return;
      var socket = new WebSocket(wsUrl('/ws/online-chat/dialog/' + dialogId + '/'));
      state.ws = socket;
      socket.onopen = function () {
        startWsPing();
      };
      socket.onmessage = function (event) {
        var data;
        try {
          data = JSON.parse(event.data);
        } catch (err) {
          return;
        }
        var type = data && data.type;
        var payload = (data && data.payload) || {};
        if (type === 'status') {
          if (data.status === 'connected') {
            catchUpDialogMessages();
            startCatchUpPolling();
          }
          return;
        }
        if (type === 'operator.joined') {
          connectOperator(payload.operator_name, {
            announce: !payload.system_message,
            avatar: payload.operator_avatar || '',
            operatorId: payload.operator_id || '',
          });
          if (payload.system_message) handleRemoteMessage(payload.system_message);
          return;
        }
        if (type === 'dialog.transferred') {
          if (payload.system_message) handleRemoteMessage(payload.system_message);
          connectOperator(
            payload.to_operator_name || payload.operator_name,
            {
              announce: false,
              avatar: payload.operator_avatar || '',
              operatorId: payload.operator_id || '',
            },
          );
          return;
        }
        if (type === 'message.created') {
          handleRemoteMessage(payload);
          return;
        }
        if (type === 'message.updated') {
          applyRemoteMessageUpdate(payload);
          return;
        }
        if (type === 'messages.read') {
          (payload.message_ids || []).forEach(function (id) {
            setMessageReceipt(id, 'read');
          });
          return;
        }
        if (type === 'typing.start') {
          if (payload.speaker === 'operator') showTyping(true);
          return;
        }
        if (type === 'typing.stop') {
          if (payload.speaker === 'operator') showTyping(false);
          return;
        }
        if (type === 'dialog.closed') {
          if (payload.system_message) handleRemoteMessage(payload.system_message);
          showPostchat(payload.farewell_message || STR.farewell);
          return;
        }
        if (type === 'dialog.blocked') {
          addSystem('Диалог заблокирован.');
          state.closed = true;
          setComposerEnabled(false);
        }
      };
    }

    function submitFeedbackThen(done) {
      if (!state.dialogId) {
        if (done) done(true);
        return;
      }
      if (state.feedbackSaved) {
        if (done) done(true);
        return;
      }
      if (!state.rating || state.rating < 1) {
        if (done) done(true);
        return;
      }
      var comment = (commentEl && commentEl.value) || '';
      fetch(apiUrl('/api/v1/online-chat/dialogs/' + state.dialogId + '/feedback/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rating: state.rating, comment: comment }),
      })
        .then(function (response) {
          return response.json().then(function (body) {
            if (!response.ok || !body.ok) {
              throw new Error((body && body.detail) || 'feedback_failed');
            }
            state.feedbackSaved = true;
            if (done) done(true);
          });
        })
        .catch(function (err) {
          setPostchatStatus(
            (err && err.message) || 'Не удалось сохранить оценку.',
            true,
          );
          if (done) done(false);
        });
    }

    function resetPrechatForm() {
      Object.keys(formInputs).forEach(function (key) {
        formInputs[key].value = '';
      });
      if (questionEl) questionEl.value = '';
      if (commentEl) commentEl.value = '';
      if (emailEl) emailEl.value = '';
      state.rating = 0;
      state.hoverRating = 0;
      state.feedbackSaved = false;
      renderStars();
    }

    function closeWidgetAfterThanks(message) {
      if (farewellEl) {
        farewellEl.textContent = message || STR.farewell;
      }
      setPostchatStatus(message || STR.farewell, false);
      showView('postchat');
      setOpen(true);
      window.setTimeout(function () {
        persistDialogId(null);
        state.dialogId = null;
        state.closed = false;
        state.operatorConnected = false;
        state.seenMessageIds = {};
        messagesEl.innerHTML = '';
        state.messages = [];
        opStrip.setAttribute('hidden', '');
        resetPrechatForm();
        showView('prechat');
        setOpen(false);
      }, 1600);
    }

    function sendTranscript() {
      if (!state.dialogId || !emailEl) return;
      var email = (emailEl.value || '').trim();
      if (!email || email.indexOf('@') < 1) {
        setPostchatStatus(STR.emailInvalid, true);
        emailEl.focus();
        return;
      }
      setPostchatStatus('Отправка…', false);
      submitFeedbackThen(function () {
        fetch(
          apiUrl('/api/v1/online-chat/dialogs/' + state.dialogId + '/send-transcript/'),
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: email }),
          },
        )
          .then(function (response) {
            return response.json().then(function (body) {
              var detail =
                (body &&
                  body.transcript_email &&
                  body.transcript_email.error_detail) ||
                (body && body.detail) ||
                '';
              if (!response.ok || !body.ok) {
                throw new Error(detail || STR.transcriptFailed);
              }
              closeWidgetAfterThanks('Спасибо за обращение! Транскрипт отправлен.');
            });
          })
          .catch(function (err) {
            setPostchatStatus(
              (err && err.message) || STR.transcriptFailed,
              true,
            );
          });
      });
    }

    function finishPostchat() {
      if (state.rating < 1 && commentEl && (commentEl.value || '').trim()) {
        setPostchatStatus(STR.rateRequired, true);
        return;
      }
      submitFeedbackThen(function () {
        closeWidgetAfterThanks(STR.farewell);
      });
    }

    function createDialog(text, profile) {
      profile = profile || {};
      return fetch(apiUrl('/api/v1/online-chat/dialogs/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: text,
          widget_id: WIDGET_ID,
          placement: PLACEMENT,
          channel: 'widget',
          first_name: profile.firstName || '',
          last_name: profile.lastName || '',
          phone: profile.phone || '',
          fields: profile.fields || [],
          locale: LOCALE,
          page_url: global.location.href,
          client_external_id: SIM_CLIENT,
        }),
      })
        .then(function (response) {
          return response.json().then(function (body) {
            if (!response.ok || !body.ok) {
              var err = new Error((body && body.detail) || 'create_failed');
              err.code = body && body.error;
              err.status = response.status;
              throw err;
            }
            return body;
          });
        })
        .then(function (body) {
          state.dialogId = body.dialog && body.dialog.id;
          persistDialogId(state.dialogId);
          if (body.message && body.message.id) rememberMessageId(body.message.id);
          if (state.dialogId) connectDialogSocket(state.dialogId);
          // The backend may create base/offline bot messages in the same request.
          // Hydrate them from HTTP response so the client sees them immediately
          // even if WS subscription starts a moment later.
          var initialMessages =
            body &&
            body.dialog &&
            Array.isArray(body.dialog.messages)
              ? body.dialog.messages
              : [];
          initialMessages.forEach(function (message) {
            handleRemoteMessage(message);
          });
          return body;
        })
        .catch(function (err) {
          if (err && err.code === 'client_blocked') {
            addSystem(err.message || STR.clientBlocked);
            state.closed = true;
            setComposerEnabled(false);
            setWaitingHint(false);
            return null;
          }
          addSystem('Не удалось отправить обращение. Попробуйте ещё раз.');
          return null;
        });
    }

    function postDialogMessage(text, localRow, extras) {
      if (!state.dialogId) return;
      extras = extras || {};
      var payload = { text: text, speaker: 'client' };
      if (extras.attachment_name) payload.attachment_name = extras.attachment_name;
      fetch(apiUrl('/api/v1/online-chat/dialogs/' + state.dialogId + '/messages/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
        .then(function (response) {
          return response.json().then(function (body) {
            if (body && body.message && body.message.id) {
              rememberMessageId(body.message.id);
              if (localRow) {
                localRow.setAttribute('data-message-id', body.message.id);
                setMessageReceipt(
                  body.message.id,
                  body.message.receipt_status || 'delivered',
                );
              }
            }
          });
        })
        .catch(function () {});
    }

    function renderPendingFile() {
      if (!pendingFileEl || !pendingFileNameEl) return;
      if (state.pendingFile) {
        pendingFileNameEl.textContent = '📎 ' + state.pendingFile.name;
        pendingFileEl.classList.add('is-visible');
        pendingFileEl.removeAttribute('hidden');
      } else {
        pendingFileNameEl.textContent = '';
        pendingFileEl.classList.remove('is-visible');
        pendingFileEl.setAttribute('hidden', '');
      }
    }

    function clearPendingFile() {
      state.pendingFile = null;
      if (fileInputEl) fileInputEl.value = '';
      renderPendingFile();
    }

    function queueAttachment(file) {
      if (!file || state.closed || state.view !== 'chat' || !state.dialogId) return;
      state.pendingFile = file;
      renderPendingFile();
    }

    function sendFromComposer() {
      if (state.closed || state.view !== 'chat') return;
      var text = (inputEl.value || '').trim();
      var file = state.pendingFile;
      if (!text && !file) return;
      inputEl.value = '';
      sendTypingStop();
      setWaitingHint(false);
      if (!state.operatorConnected) setWaitingHint(true);

      if (file) {
        var optimisticText = text || ('Файл: ' + file.name);
        var row = addBubble(
          'client',
          optimisticText,
          STR.you,
          state.clientInitials,
          formatTime(new Date()),
          {
            receiptStatus: 'delivered',
            attachmentName: file.name,
            attachmentDownloadable: false,
          },
        );
        var form = new FormData();
        form.append('file', file);
        form.append('speaker', 'client');
        if (text) form.append('text', text);
        clearPendingFile();
        fetch(
          apiUrl(
            '/api/v1/online-chat/dialogs/' +
              state.dialogId +
              '/attachments/',
          ),
          { method: 'POST', body: form, credentials: 'include' },
        )
          .then(function (response) {
            return response.json().then(function (body) {
              if (!response.ok || !body.message) {
                throw new Error((body && body.detail) || 'upload_failed');
              }
              rememberMessageId(body.message.id);
              if (row) row.remove();
              addBubble(
                'client',
                body.message.text || optimisticText,
                STR.you,
                state.clientInitials,
                formatTime(new Date(body.message.created_at || Date.now())),
                Object.assign(
                  {
                    id: body.message.id,
                    receiptStatus: body.message.receipt_status || 'delivered',
                  },
                  attachmentOptionsFromMessage(body.message),
                ),
              );
            });
          })
          .catch(function () {
            if (row) row.remove();
            addSystem('Не удалось загрузить файл. Проверьте тип и размер.');
          });
        return;
      }

      var textRow = addBubble(
        'client',
        text,
        STR.you,
        state.clientInitials,
        formatTime(new Date()),
        { receiptStatus: 'delivered' },
      );
      postDialogMessage(text, textRow);
    }

    function clearFieldErrors() {
      Object.keys(formInputs).forEach(function (key) {
        formInputs[key].classList.remove('invalid');
      });
      if (questionEl) questionEl.classList.remove('invalid');
      if (formErrorEl) formErrorEl.setAttribute('hidden', '');
    }

    function validatePrechat() {
      clearFieldErrors();
      var values = {};
      var missing = [];
      Object.keys(formInputs).forEach(function (key) {
        var input = formInputs[key];
        var value = (input.value || '').trim();
        values[key] = value;
        if (input.required && !value) missing.push(input);
      });
      var question = (questionEl.value || '').trim();
      if (questionEl.required && !question) missing.push(questionEl);
      if (missing.length) {
        missing.forEach(function (el) {
          el.classList.add('invalid');
        });
        if (formErrorEl) formErrorEl.removeAttribute('hidden');
        missing[0].focus();
        return null;
      }
      var labeledFields = [];
      var coreKeys = { name: 1, first_name: 1, last_name: 1, phone: 1, question: 1 };
      resolveFormFields().forEach(function (field) {
        var value = (values[field.key] || '').trim();
        if (!value || coreKeys[field.key]) return;
        labeledFields.push({ label: field.label || field.key, value: value });
      });
      return {
        firstName: values.name || '',
        lastName: values.last_name || '',
        phone: values.phone || '',
        question: question,
        displayQuestion: question,
        values: values,
        fields: labeledFields,
      };
    }

    if (questionEl) {
      questionEl.addEventListener('input', function () {
        questionEl.classList.remove('invalid');
        if (formErrorEl) formErrorEl.setAttribute('hidden', '');
      });
    }

    function startChat() {
      var form = validatePrechat();
      if (!form) return;
      state.clientInitials = initialsFromName(
        (form.firstName + ' ' + form.lastName).trim() || form.phone || 'КЛ',
      );
      state.operatorConnected = false;
      state.closed = false;
      state.feedbackSaved = false;
      state.dialogId = null;
      state.seenMessageIds = {};
      closeDialogSocket();
      persistDialogId(null);
      messagesEl.innerHTML = '';
      state.messages = [];
      opStrip.setAttribute('hidden', '');
      showView('chat');
      var firstRow = addBubble(
        'client',
        form.displayQuestion || form.question,
        STR.you,
        state.clientInitials,
        formatTime(new Date()),
        { receiptStatus: 'delivered' },
      );
      setWaitingHint(true);
      createDialog(form.displayQuestion || form.question, form).then(function (body) {
        if (!body || !body.message || !body.message.id) return;
        firstRow.setAttribute('data-message-id', body.message.id);
        setMessageReceipt(body.message.id, body.message.receipt_status || 'delivered');
      });
    }

    fab.addEventListener('click', function () {
      setOpen(true);
    });

    root.addEventListener('click', function (event) {
      var target = event.target;
      if (!(target instanceof Element)) return;
      var actionBtn = target.closest('[data-action]');
      if (!actionBtn) return;
      var action = actionBtn.getAttribute('data-action');
      if (action === 'close') {
        setOpen(false);
        return;
      }
      if (action === 'start') {
        startChat();
        return;
      }
      if (action === 'send') {
        sendFromComposer();
        return;
      }
      if (action === 'attach') {
        if (fileInputEl) fileInputEl.click();
        return;
      }
      if (action === 'clear-file') {
        clearPendingFile();
        return;
      }
      if (action === 'rate') {
        state.rating = Number(actionBtn.getAttribute('data-rating') || 0);
        state.hoverRating = 0;
        renderStars();
        return;
      }
      if (action === 'send-transcript') {
        sendTranscript();
        return;
      }
      if (action === 'finish') {
        finishPostchat();
        return;
      }
    });

    if (starsEl) {
      starsEl.addEventListener('mouseover', function (event) {
        var target = event.target;
        if (!(target instanceof Element)) return;
        var star = target.closest('.star');
        if (!star || !starsEl.contains(star)) return;
        state.hoverRating = Number(star.getAttribute('data-rating') || 0);
        renderStars();
      });
      starsEl.addEventListener('mouseleave', function () {
        state.hoverRating = 0;
        renderStars();
      });
    }

    inputEl.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        sendFromComposer();
      }
    });

    inputEl.addEventListener('input', function () {
      scheduleClientTyping(inputEl.value || '');
    });

    inputEl.addEventListener('blur', function () {
      sendTypingStop();
    });

    if (fileInputEl) {
      fileInputEl.addEventListener('change', function () {
        var file = fileInputEl.files && fileInputEl.files[0];
        if (file) queueAttachment(file);
        fileInputEl.value = '';
      });
    }

    renderStars();
    renderFabBadge();
    showView('prechat');
    setOpen(false);

    function resumeDialogById(dialogId) {
      if (!dialogId) return Promise.resolve(false);
      return fetch(apiUrl('/api/v1/online-chat/dialogs/' + dialogId + '/'))
        .then(function (response) {
          return response.json().then(function (body) {
            if (!response.ok || !body.ok || !body.dialog) {
              persistDialogId(null);
              return false;
            }
            var dialog = body.dialog;
            state.dialogId = dialog.id;
            persistDialogId(dialog.id);
            if (dialog.status === 'closed' || dialog.status === 'blocked') {
              showPostchat(STR.farewell);
              return true;
            }
            state.clientInitials = initialsFromName(
              (dialog.client_first_name || '') + ' ' + (dialog.client_last_name || ''),
            );
            state.operatorAvatar = resolveOperatorAvatarUrl(null, dialog);
            showView('chat');
            setOpen(true);
            messagesEl.innerHTML = '';
            state.messages = [];
            (dialog.messages || []).forEach(function (message) {
              if (message && message.is_history) return;
              rememberMessageId(message.id);
              if (message.speaker === 'system') {
                addSystem(message.text);
                return;
              }
              if (message.speaker === 'client') {
                addBubble(
                  'client',
                  message.text,
                  STR.you,
                  state.clientInitials,
                  formatTime(new Date(message.created_at || Date.now())),
                  Object.assign(
                    {
                      id: message.id,
                      receiptStatus: message.receipt_status || 'delivered',
                    },
                    attachmentOptionsFromMessage(message),
                  ),
                );
                return;
              }
              if (message.speaker === 'operator' || message.speaker === 'bot') {
                var historyOperatorName =
                  message.speaker === 'operator'
                    ? message.operator_name || dialog.operator_name || state.operatorName
                    : state.operatorName;
                var historyAvatar =
                  message.speaker === 'bot'
                    ? { url: '', fallback: '' }
                    : resolveOperatorAvatarSources(message, dialog);
                addBubble(
                  'operator',
                  message.text,
                  message.speaker === 'bot'
                    ? 'Виртуальный помощник'
                    : shortNameFromFull(historyOperatorName),
                  message.speaker === 'bot'
                    ? 'Б'
                    : initialsFromName(historyOperatorName),
                  formatTime(new Date(message.created_at || Date.now())),
                  Object.assign(
                    {
                      id: message.id,
                      receiptStatus: message.receipt_status,
                      quotedText: message.quoted_text,
                      avatarUrl: historyAvatar.url,
                      avatarFallbackUrl: historyAvatar.fallback,
                      isBot: message.speaker === 'bot',
                      operatorLabel:
                        message.speaker === 'bot'
                          ? 'Виртуальный помощник'
                          : shortNameFromFull(historyOperatorName),
                    },
                    attachmentOptionsFromMessage(message),
                  ),
                );
              }
            });
            if (dialog.status === 'active' && dialog.operator_name) {
              connectOperator(dialog.operator_name, {
                announce: false,
                avatar: dialog.operator_avatar || '',
                operatorId: dialog.operator_id || '',
              });
            } else if (dialog.status === 'waiting') {
              setWaitingHint(true);
            }
            connectDialogSocket(dialog.id);
            scheduleMarkMessagesReadAsClient();
            return true;
          });
        })
        .catch(function () {
          persistDialogId(null);
          return false;
        });
    }

    function findOpenDialogForSimClient() {
      if (!SIM_CLIENT) return Promise.resolve(null);
      return fetch(
        apiUrl(
          '/api/v1/online-chat/history/?external_id=' + encodeURIComponent(SIM_CLIENT),
        ),
      )
        .then(function (response) {
          return response.json().then(function (body) {
            if (!response.ok || !body.ok || !Array.isArray(body.items)) return null;
            var openItem = body.items.find(function (item) {
              return item.status === 'waiting' || item.status === 'active';
            });
            return openItem ? openItem.id : null;
          });
        })
        .catch(function () {
          return null;
        });
    }

    var bootResumeId = RESUME_DIALOG_ID || readPersistedDialogId();
    Promise.resolve(bootResumeId)
      .then(function (id) {
        if (id) return resumeDialogById(id);
        return findOpenDialogForSimClient().then(function (foundId) {
          return foundId ? resumeDialogById(foundId) : false;
        });
      })
      .then(function () {
        /* resume finished or skipped */
      });

    global.BelarusbankChatWidget = {
      open: function () {
        setOpen(true);
      },
      close: function () {
        setOpen(false);
      },
      /** Demo/realtime hooks */
      connectOperator: connectOperator,
      showTyping: showTyping,
      showPostchat: showPostchat,
      widgetId: WIDGET_ID,
      placement: PLACEMENT,
      palette: WP,
      getDialogId: function () {
        return state.dialogId;
      },
    };
  }

  function bootWidget() {
    var base = (API_BASE || '').replace(/\/$/, '');
    fetch(
      base +
        '/api/v1/online-chat/config/widget/' +
        encodeURIComponent(WIDGET_ID) +
        '/',
    )
      .then(function (response) {
        if (!response.ok) return null;
        return response.json();
      })
      .then(function (body) {
        WIDGET_CONFIG = body && body.config ? body.config : null;
        if (!WIDGET_CONFIG) return;
        if (WIDGET_CONFIG.welcome_message) {
          STR.welcome = WIDGET_CONFIG.welcome_message;
        }
        if (WIDGET_CONFIG.queue_message) {
          STR.waiting = WIDGET_CONFIG.queue_message;
        }
        if (WIDGET_CONFIG.offline_message) {
          STR.offline = WIDGET_CONFIG.offline_message;
        }
        var accent =
          WIDGET_CONFIG.theme && WIDGET_CONFIG.theme.accent;
        if (accent && /^#[0-9A-Fa-f]{6}$/.test(accent)) {
          WP.primary = accent;
          WP.fabBg = accent;
          WP.headerBrand = accent;
          WP.avatarOperator = accent;
        }
      })
      .catch(function () {
        WIDGET_CONFIG = null;
      })
      .finally(createWidget);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootWidget);
  } else {
    bootWidget();
  }
})(typeof window !== 'undefined' ? window : this);
