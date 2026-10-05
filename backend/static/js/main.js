/**
 * Основной JavaScript файл для системы Беларусбанк AI
 */

// Глобальные переменные
let currentChannel = 'chat';
let callTimer = 0;
let callTimerInterval = null;
let isCallActive = false;
let isMicrophoneEnabled = true;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;

// Web Speech API переменные
let speechRecognizer = null;
let isSpeechRecognitionActive = false;
let finalTranscription = '';

// API URLs
const API_BASE_URL = 'http://localhost:8003'; // AI API
const DJANGO_API_BASE = '/api'; // Django API

// Хранение данных
let currentSessionId = null;
let currentClientId = null;
let currentChatChannelId = null;
let pendingRecommendation = null;

// Хранение истории чатов для каждого канала
const chatHistories = {
    'chat': { client: [], operator: [] },
    'telegram': { client: [], operator: [] },
    'viber': { client: [], operator: [] },
    'whatsapp': { client: [], operator: [] },
    'phone': { client: [], operator: [] }
};

// Хранение сессий для каждого канала
const channelSessions = {
    'chat': null,
    'telegram': null,
    'viber': null,
    'whatsapp': null,
    'phone': null
};

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ Система Беларусбанк AI инициализирована');

    // Проверяем, есть ли данные клиента
    const clientNameElement = document.getElementById('current-user-name');
    if (clientNameElement && clientNameElement.dataset.clientId) {
        currentClientId = clientNameElement.dataset.clientId;
        console.log('Клиент ID:', currentClientId);
    }

    const chatSessionElement = document.getElementById('chat-session-data');
    if (chatSessionElement && chatSessionElement.dataset.sessionId) {
        currentSessionId = chatSessionElement.dataset.sessionId;
        console.log('Сессия ID:', currentSessionId);
    }

    // Проверяем, есть ли данные канала чата
    const chatChannelElement = document.getElementById('chat-channel-data');
    if (chatChannelElement && chatChannelElement.dataset.channelId) {
        currentChatChannelId = chatChannelElement.dataset.channelId;
        console.log('Канал ID:', currentChatChannelId);
    }

    // Инициализация интерфейса
    initEventListeners();
    checkEmptyChats();

    // Проверка API
    checkAPIConnection();

    // Загрузка существующих сообщений если есть
    if (currentChatChannelId) {
        loadExistingMessages();
    }

    // Проверка поддержки распознавания речи
    if (checkSpeechRecognitionSupport()) {
        console.log('✅ Web Speech API поддерживается браузером');
    } else {
        console.warn('⚠️ Web Speech API не поддерживается браузером');
        // Деактивируем кнопку звонка
        const phoneTab = document.querySelector('.channel-tab[data-channel="phone"]');
        if (phoneTab) {
            phoneTab.style.opacity = '0.5';
            phoneTab.style.cursor = 'not-allowed';
            phoneTab.title = 'Распознавание речи не поддерживается вашим браузером';
            phoneTab.onclick = function() {
                alert('Распознавание речи не поддерживается вашим браузером. Пожалуйста, используйте Chrome или Edge.');
            };
        }
    }
});

// Проверка поддержки Web Speech API
function checkSpeechRecognitionSupport() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        console.error('Браузер не поддерживает Web Speech API');
        return false;
    }
    return true;
}

// Инициализация распознавания речи
function initSpeechRecognition() {
    if (!checkSpeechRecognitionSupport()) {
        return false;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    speechRecognizer = new SpeechRecognition();

    // Настройки
    speechRecognizer.continuous = true;
    speechRecognizer.interimResults = true;
    speechRecognizer.lang = 'ru-RU';
    speechRecognizer.maxAlternatives = 1;

    // Обработчики событий
    speechRecognizer.onstart = function() {
        console.log('🎤 Распознавание речи начато');
        isSpeechRecognitionActive = true;
        updateSuflerStatus('Активен', 'success', 'Распознавание речи запущено. Говорите в микрофон...');
    };

    speechRecognizer.onresult = function(event) {
        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;

            if (event.results[i].isFinal) {
                finalTranscript += transcript;
                finalTranscription += transcript + ' ';
            } else {
                interimTranscript += transcript;
            }
        }

        // Обновляем интерфейс
        if (interimTranscript) {
            handlePartialTranscription(interimTranscript);
        }

        if (finalTranscript) {
            handleFinalTranscription(finalTranscript);
        }
    };

    speechRecognizer.onerror = function(event) {
        console.error('Ошибка распознавания речи:', event.error);

        let errorMessage = 'Ошибка распознавания речи';
        let errorType = 'error';

        switch(event.error) {
            case 'no-speech':
                errorMessage = 'Речь не обнаружена. Пожалуйста, говорите громче.';
                errorType = 'warning';
                break;
            case 'audio-capture':
                errorMessage = 'Микрофон недоступен. Проверьте разрешения.';
                errorType = 'error';
                break;
            case 'not-allowed':
                errorMessage = 'Доступ к микрофону запрещен. Разрешите доступ в настройках браузера.';
                errorType = 'error';
                break;
            case 'network':
                errorMessage = 'Ошибка сети при распознавании речи.';
                errorType = 'error';
                break;
            default:
                errorMessage = `Ошибка: ${event.error}`;
        }

        updateSuflerStatus('Ошибка', errorType, errorMessage);
        stopSpeechRecognition();
    };

    speechRecognizer.onend = function() {
        console.log('Распознавание речи остановлено');
        isSpeechRecognitionActive = false;

        // Автоматически перезапускаем, если звонок активен
        if (isCallActive) {
            setTimeout(startSpeechRecognition, 1000);
        }
    };

    return true;
}

// Начать распознавание речи
function startSpeechRecognition() {
    if (!speechRecognizer && !initSpeechRecognition()) {
        return false;
    }

    try {
        finalTranscription = '';
        speechRecognizer.start();
        return true;
    } catch (error) {
        console.error('Ошибка запуска распознавания:', error);
        updateSuflerStatus('Ошибка', 'error', 'Не удалось запустить распознавание речи');
        return false;
    }
}

// Остановить распознавание речи
function stopSpeechRecognition() {
    if (speechRecognizer && isSpeechRecognitionActive) {
        try {
            speechRecognizer.stop();
            isSpeechRecognitionActive = false;
            console.log('Распознавание речи остановлено');
        } catch (error) {
            console.error('Ошибка остановки распознавания:', error);
        }
    }
}

// Обновить статус суфлера
function updateSuflerStatus(status, type, details) {
    const suflerBadge = document.getElementById('sufler-badge');
    const suflerDetails = document.getElementById('sufler-details');

    if (suflerBadge) {
        suflerBadge.textContent = `Суфлёр ${status}`;
        if (type === 'success') {
            suflerBadge.style.background = 'var(--success)';
        } else if (type === 'warning') {
            suflerBadge.style.background = 'var(--warning)';
        } else if (type === 'error') {
            suflerBadge.style.background = 'var(--secondary)';
        } else {
            suflerBadge.style.background = 'var(--gray)';
        }
    }

    if (suflerDetails) {
        suflerDetails.textContent = details;
    }
}

// Инициализация обработчиков событий
function initEventListeners() {
    console.log('Инициализация обработчиков событий');

    // Переключение каналов связи
    document.querySelectorAll('.channel-tab').forEach(tab => {
        tab.addEventListener('click', function() {
            saveCurrentChatHistory();

            document.querySelectorAll('.channel-tab').forEach(t => t.classList.remove('active'));
            this.classList.add('active');

            const newChannel = this.getAttribute('data-channel');
            console.log(`Переключение на канал: ${newChannel}`);

            currentChannel = newChannel;
            updateInterfaceForChannel(newChannel);
            loadChatHistory(newChannel);
            updateChannelIndicators(newChannel);
        });
    });

    // Кнопка завершения звонка
    const endCallBtn = document.getElementById('end-call');
    if (endCallBtn) {
        endCallBtn.addEventListener('click', function() {
            endCall();
            document.querySelector('.channel-tab[data-channel="chat"]').click();
        });
    }

    // Кнопка микрофона
    const toggleMicBtn = document.getElementById('toggle-microphone');
    if (toggleMicBtn) {
        toggleMicBtn.addEventListener('click', function() {
            isMicrophoneEnabled = !isMicrophoneEnabled;

            if (isMicrophoneEnabled) {
                this.innerHTML = '<i class="fas fa-microphone"></i>';
                this.style.background = 'linear-gradient(135deg, var(--warning) 0%, #E89C00 100%)';
                console.log('🎤 Микрофон включен');
            } else {
                this.innerHTML = '<i class="fas fa-microphone-slash"></i>';
                this.style.background = 'linear-gradient(135deg, var(--secondary) 0%, var(--secondary-dark) 100%)';
                console.log('🔇 Микрофон выключен');
            }
        });
    }

    // Отправка сообщения клиентом
    const clientSendBtn = document.getElementById('client-send');
    if (clientSendBtn) {
        clientSendBtn.addEventListener('click', async function() {
            await sendClientMessage();
        });
    }

    // Enter для отправки сообщения клиентом
    const clientInput = document.getElementById('client-input');
    if (clientInput) {
        clientInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') sendClientMessage();
        });
    }

    // Отправка сообщения оператором
    const operatorSendBtn = document.getElementById('operator-send');
    if (operatorSendBtn) {
        operatorSendBtn.addEventListener('click', function() {
            sendOperatorMessage();
        });
    }

    // Enter для отправки сообщения оператором
    const operatorInput = document.getElementById('operator-input');
    if (operatorInput) {
        operatorInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') sendOperatorMessage();
        });
    }

    // Двойной клик по заголовку для смены роли (для тестирования)
    const header = document.querySelector('.header');
    if (header) {
        header.addEventListener('dblclick', function() {
            toggleUserRole();
        });
    }
}

// Проверка пустых чатов
function checkEmptyChats() {
    const clientChat = document.getElementById('client-chat');
    const operatorChat = document.getElementById('operator-chat');

    // Проверяем клиентский чат
    if (clientChat) {
        const messages = clientChat.querySelectorAll('.message:not(.empty-chat-message)');
        const emptyMsg = document.getElementById('empty-client-chat');

        if (messages.length === 0 && !emptyMsg) {
            showEmptyClientChat();
        } else if (messages.length > 0 && emptyMsg) {
            emptyMsg.remove();
        }
    }

    // Проверяем чат оператора
    if (operatorChat) {
        const messages = operatorChat.querySelectorAll('.message:not(.empty-chat-message)');
        const emptyMsg = document.getElementById('empty-operator-chat');

        if (messages.length === 0 && !emptyMsg) {
            showEmptyOperatorChat();
        } else if (messages.length > 0 && emptyMsg) {
            emptyMsg.remove();
        }
    }
}

// Показать пустой клиентский чат
function showEmptyClientChat() {
    const clientChat = document.getElementById('client-chat');
    if (!clientChat) return;

    if (document.getElementById('empty-client-chat')) return;

    const emptyDiv = document.createElement('div');
    emptyDiv.className = 'empty-chat-message';
    emptyDiv.id = 'empty-client-chat';
    emptyDiv.innerHTML = `
        <i class="fas fa-comments" style="font-size: 2rem; margin-bottom: 1rem;"></i><br>
        Чат пуст<br>
        <span style="font-size: 0.9rem;">Начните общение, отправив сообщение</span>
    `;
    clientChat.appendChild(emptyDiv);
}

// Показать пустой чат оператора
function showEmptyOperatorChat() {
    const operatorChat = document.getElementById('operator-chat');
    if (!operatorChat) return;

    if (document.getElementById('empty-operator-chat')) return;

    const emptyDiv = document.createElement('div');
    emptyDiv.className = 'empty-chat-message';
    emptyDiv.id = 'empty-operator-chat';
    emptyDiv.innerHTML = `
        <i class="fas fa-headset" style="font-size: 2rem; margin-bottom: 1rem;"></i><br>
        Диалог с клиентом пуст<br>
        <span style="font-size: 0.9rem;">Начните общение или включите суфлер</span>
    `;
    operatorChat.appendChild(emptyDiv);
}

// Проверка соединения с API
async function checkAPIConnection() {
    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        if (response.ok) {
            console.log('✅ AI API доступен');
        } else {
            console.warn('⚠️ AI API недоступен');
        }
    } catch (error) {
        console.error('❌ Ошибка подключения к AI API:', error);
    }
}

// Загрузка существующих сообщений
async function loadExistingMessages() {
    if (!currentChatChannelId) return;

    try {
        const response = await fetch(`${DJANGO_API_BASE}/chat-messages/${currentChatChannelId}/`);
        if (response.ok) {
            const data = await response.json();

            // Очищаем чаты
            clearChats();

            // Загружаем сообщения
            data.messages.forEach(msg => {
                if (msg.type === 'client') {
                    addClientMessageToOperatorChat(msg.content);
                    addMessageToClientChat('', msg.content, true);
                } else if (msg.type === 'operator') {
                    addOperatorMessage('Оператор', msg.content, false);
                    addMessageToClientChat('Оператор', msg.content, false);
                }
            });

            checkEmptyChats();
        }
    } catch (error) {
        console.error('Ошибка загрузки сообщений:', error);
    }
}

// Сохранить текущую историю чата
function saveCurrentChatHistory() {
    const clientChat = document.getElementById('client-chat');
    const operatorChat = document.getElementById('operator-chat');

    if (!clientChat || !operatorChat) return;

    const clientMessages = [];
    const operatorMessages = [];

    // Сохраняем клиентские сообщения
    clientChat.querySelectorAll('.message:not(.empty-chat-message)').forEach(msg => {
        const isUser = msg.classList.contains('message-user');
        const text = msg.querySelector('.message-text') ?
            msg.querySelector('.message-text').textContent :
            msg.textContent.replace(/\d{2}:\d{2}$/, '').trim();
        const time = msg.querySelector('.message-time') ?
            msg.querySelector('.message-time').textContent :
            getCurrentTime();

        clientMessages.push({ text, isUser, time });
    });

    // Сохраняем операторские сообщения
    operatorChat.querySelectorAll('.message:not(.empty-chat-message):not(.message-bot)').forEach(msg => {
        const isOperator = msg.classList.contains('message-operator');
        const sender = isOperator ? 'operator' : 'client';
        const text = msg.querySelector('.message-text') ?
            msg.querySelector('.message-text').textContent :
            msg.textContent.replace(/\d{2}:\d{2}$/, '').trim();
        const time = msg.querySelector('.message-time') ?
            msg.querySelector('.message-time').textContent :
            getCurrentTime();

        operatorMessages.push({ text, sender, time });
    });

    chatHistories[currentChannel] = {
        client: clientMessages,
        operator: operatorMessages
    };
}

// Загрузить историю чата для канала
function loadChatHistory(channel) {
    const history = chatHistories[channel];

    // Очищаем чаты
    clearChats();

    // Загружаем клиентский чат
    if (history.client && history.client.length > 0) {
        history.client.forEach(msg => {
            if (msg.isUser) {
                addMessageToClientChat('', msg.text, true);
            } else {
                addMessageToClientChat('Оператор', msg.text, false);
            }
        });
    }

    // Загружаем чат оператора
    if (history.operator && history.operator.length > 0) {
        history.operator.forEach(msg => {
            if (msg.sender === 'operator') {
                addOperatorMessage('Оператор', msg.text, false);
            } else if (msg.sender === 'client') {
                addClientMessageToOperatorChat(msg.text);
            }
        });
    }

    checkEmptyChats();
}

// Очистить чаты
function clearChats() {
    const clientChat = document.getElementById('client-chat');
    const operatorChat = document.getElementById('operator-chat');

    if (clientChat) {
        clientChat.querySelectorAll('.message:not(.empty-chat-message)').forEach(msg => msg.remove());
    }

    if (operatorChat) {
        operatorChat.querySelectorAll('.message:not(.empty-chat-message)').forEach(msg => msg.remove());
    }

    // Удаляем текущую рекомендацию если есть
    const recommendationDiv = document.getElementById('current-recommendation');
    if (recommendationDiv) {
        recommendationDiv.remove();
    }

    pendingRecommendation = null;
}

// Обновить интерфейс для канала
function updateInterfaceForChannel(channel) {
    const chatInterface = document.getElementById('chat-interface');
    const phoneInterface = document.getElementById('phone-interface');
    const transcriptionContainer = document.getElementById('transcription-container');
    const clientChatHeader = document.getElementById('client-chat-header');
    const clientStatus = document.getElementById('client-status');

    if (!chatInterface || !phoneInterface) return;

    // Сброс стилей мессенджеров
    chatInterface.classList.remove('telegram-interface', 'viber-interface', 'whatsapp-interface');

    if (channel === 'phone') {
        chatInterface.style.display = 'none';
        phoneInterface.style.display = 'flex';
        if (transcriptionContainer) transcriptionContainer.style.display = 'flex';
        if (clientStatus) clientStatus.textContent = 'В разговоре';

        const operatorChatTitle = document.getElementById('operator-chat-title');
        if (operatorChatTitle) operatorChatTitle.textContent = 'Телефонный звонок с клиентом';

        const operatorStatus = document.getElementById('operator-status');
        if (operatorStatus) operatorStatus.textContent = 'В разговоре';

        startCall();
    } else {
        chatInterface.style.display = 'flex';
        phoneInterface.style.display = 'none';
        if (transcriptionContainer) transcriptionContainer.style.display = 'none';

        if (isCallActive) {
            endCall();
        }

        let channelName, logoColor, logoIcon, statusText;

        switch(channel) {
            case 'telegram':
                channelName = 'Telegram';
                logoColor = '#0088cc';
                logoIcon = '<i class="fab fa-telegram"></i>';
                chatInterface.classList.add('telegram-interface');
                statusText = 'Telegram';
                break;
            case 'viber':
                channelName = 'Viber';
                logoColor = '#7360F2';
                logoIcon = '<i class="fab fa-viber"></i>';
                chatInterface.classList.add('viber-interface');
                statusText = 'Viber';
                break;
            case 'whatsapp':
                channelName = 'WhatsApp';
                logoColor = '#25D366';
                logoIcon = '<i class="fab fa-whatsapp"></i>';
                chatInterface.classList.add('whatsapp-interface');
                statusText = 'WhatsApp';
                break;
            default:
                channelName = 'Онлайн-чат';
                logoColor = 'var(--primary)';
                logoIcon = '<i class="fas fa-robot"></i>';
                statusText = 'Online';
        }

        if (clientChatHeader) {
            const messengerLogo = clientChatHeader.querySelector('.messenger-logo');
            const messengerName = clientChatHeader.querySelector('.messenger-name span');

            if (messengerLogo) {
                messengerLogo.innerHTML = logoIcon;
                messengerLogo.style.background = logoColor;
            }

            if (messengerName) {
                messengerName.textContent = `AI-ассистент через ${channelName}`;
            }
        }

        if (clientStatus) clientStatus.textContent = statusText;

        const operatorChatTitle = document.getElementById('operator-chat-title');
        if (operatorChatTitle) operatorChatTitle.textContent = `Диалог в ${channelName}`;

        const operatorStatus = document.getElementById('operator-status');
        if (operatorStatus) operatorStatus.textContent = 'Ожидание сообщения';
    }
}

// Обновить индикаторы канала
function updateChannelIndicators(channel) {
    const channelNames = {
        'chat': 'Чат',
        'telegram': 'Telegram',
        'viber': 'Viber',
        'whatsapp': 'WhatsApp',
        'phone': 'Звонок'
    };

    const clientIndicator = document.getElementById('current-channel-indicator');
    const operatorIndicator = document.getElementById('operator-channel-indicator');

    if (clientIndicator) clientIndicator.textContent = channelNames[channel];
    if (operatorIndicator) operatorIndicator.textContent = channelNames[channel];
}

// Начало звонка
async function startCall() {
    const hasMicPermission = await checkMicrophonePermission();
    if (!hasMicPermission) {
        alert('Для работы суфлера нужен доступ к микрофону!');
        document.querySelector('.channel-tab[data-channel="chat"]').click();
        return;
    }

    isCallActive = true;
    reconnectAttempts = 0;

    callTimer = 0;
    clearInterval(callTimerInterval);
    callTimerInterval = setInterval(updateCallTimer, 1000);

    const suflerStatus = document.getElementById('sufler-status');
    const suflerBadge = document.getElementById('sufler-badge');

    if (suflerStatus) suflerStatus.style.display = 'block';
    if (suflerBadge) {
        suflerBadge.textContent = 'Суфлёр активен';
        suflerBadge.style.background = 'var(--success)';
    }

    if (!channelSessions.phone) {
        await createNewSessionForChannel('phone');
    }

    // Запускаем распознавание речи
    if (startSpeechRecognition()) {
        console.log('📞 Звонок начат, суфлер активен');
    } else {
        alert('Не удалось запустить распознавание речи');
        endCall();
    }
}

// Завершение звонка
function endCall() {
    isCallActive = false;

    clearInterval(callTimerInterval);
    stopSpeechRecognition();

    const suflerStatus = document.getElementById('sufler-status');
    const suflerBadge = document.getElementById('sufler-badge');
    const suflerDetails = document.getElementById('sufler-details');

    if (suflerStatus) suflerStatus.style.display = 'none';
    if (suflerBadge) {
        suflerBadge.textContent = 'Суфлёр не активен';
        suflerBadge.style.background = 'var(--gray)';
    }
    if (suflerDetails) suflerDetails.textContent = 'Распознавание речи в реальном времени...';

    updateTranscriptionContainer('<div style="color: var(--gray); font-size: 0.85rem; text-align: center; padding: 1rem;">' +
        '<i class="fas fa-microphone"></i> Звонок завершен' +
        '</div>', true);

    console.log('📴 Звонок завершен');
}

// Обновление таймера звонка
function updateCallTimer() {
    callTimer++;
    const minutes = Math.floor(callTimer / 60).toString().padStart(2, '0');
    const seconds = (callTimer % 60).toString().padStart(2, '0');
    const timerElement = document.getElementById('call-timer');
    if (timerElement) timerElement.textContent = `${minutes}:${seconds}`;
}

// Проверка разрешения микрофона
async function checkMicrophonePermission() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        console.log('✅ Микрофон доступен');
        stream.getTracks().forEach(track => track.stop());
        return true;
    } catch (error) {
        console.error('❌ Нет доступа к микрофону:', error);
        alert('Пожалуйста, разрешите доступ к микрофону для работы суфлера');
        return false;
    }
}

// Создание сессии для канала
async function createNewSessionForChannel(channel) {
    try {
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: "Начало диалога",
                session_id: null,
                reset_conversation: true
            })
        });

        if (response.ok) {
            const data = await response.json();
            channelSessions[channel] = data.session_id;
            console.log(`✅ Новая сессия для канала ${channel}:`, data.session_id);
        } else {
            console.error(`❌ Ошибка создания сессии для канала ${channel}:`, response.status);
            channelSessions[channel] = `session_${channel}_${Date.now()}`;
        }
    } catch (error) {
        console.error(`❌ Ошибка при создании сессии для канала ${channel}:`, error);
        channelSessions[channel] = `session_${channel}_${Date.now()}`;
    }
}

// Получение рекомендации от AI
async function getAIRecommendation(userMessage, channel = null) {
    const targetChannel = channel || currentChannel;

    if (!channelSessions[targetChannel]) {
        await createNewSessionForChannel(targetChannel);
    }

    try {
        const operatorStatus = document.getElementById('operator-status');
        if (operatorStatus) operatorStatus.textContent = 'AI анализирует запрос...';

        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: userMessage,
                session_id: channelSessions[targetChannel],
                reset_conversation: false
            })
        });

        if (response.ok) {
            const data = await response.json();
            console.log(`✅ Ответ от AI для канала ${targetChannel}:`, data.response);

            showAIRecommendation(data.response, userMessage);

            if (operatorStatus) operatorStatus.textContent = 'Рекомендация готова';

        } else {
            console.error('❌ Ошибка API:', response.status);
            showAIRecommendation("Извините, произошла ошибка при обработке запроса. Пожалуйста, ответьте клиенту самостоятельно.", userMessage);
            if (operatorStatus) operatorStatus.textContent = 'Ошибка AI';
        }

    } catch (error) {
        console.error('❌ Ошибка сети:', error);
        showAIRecommendation("Ошибка соединения с AI. Пожалуйста, ответьте клиенту на основе ваших знаний.", userMessage);
        if (operatorStatus) operatorStatus.textContent = 'Ошибка сети';
    }
}

// Показать рекомендацию AI оператору
function showAIRecommendation(recommendation, originalMessage) {
    const emptyChat = document.getElementById('empty-operator-chat');
    if (emptyChat) {
        emptyChat.remove();
    }

    const prevRecommendation = document.getElementById('current-recommendation');
    if (prevRecommendation) {
        prevRecommendation.remove();
    }

    const recommendationDiv = document.createElement('div');
    recommendationDiv.className = 'message message-bot';
    recommendationDiv.id = 'current-recommendation';

    recommendationDiv.innerHTML = `
        <div class="message-sender">Суфлёр</div>
        <div class="prompter-box">
            <div class="prompter-title">Рекомендуемый ответ на: "${originalMessage}"</div>
            ${recommendation}
            <div class="recommendation-actions">
                <button class="recommendation-btn reject" onclick="window.rejectRecommendation()">
                    <i class="fas fa-times"></i> Отклонить
                </button>
                <button class="recommendation-btn send" onclick="window.sendRecommendation()">
                    <i class="fas fa-paper-plane"></i> Отправить
                </button>
            </div>
        </div>
        <div class="message-time">${getCurrentTime()}</div>
    `;

    pendingRecommendation = {
        text: recommendation,
        originalMessage: originalMessage
    };

    const operatorChat = document.getElementById('operator-chat');
    if (operatorChat) {
        operatorChat.appendChild(recommendationDiv);
        operatorChat.scrollTop = operatorChat.scrollHeight;
    }

    // Сохраняем в историю
    chatHistories[currentChannel].operator.push({
        text: recommendation,
        sender: 'ai_recommendation',
        time: getCurrentTime()
    });
}

// Отправить рекомендацию как ответ оператора
async function sendRecommendation() {
    if (!pendingRecommendation) return;

    const operatorChat = document.getElementById('operator-chat');
    const recommendationDiv = document.getElementById('current-recommendation');

    if (recommendationDiv) {
        recommendationDiv.remove();
    }

    // Добавляем сообщение оператора
    const operatorMessageDiv = document.createElement('div');
    operatorMessageDiv.className = 'message message-operator';
    operatorMessageDiv.innerHTML = `
        <div class="message-sender">Оператор</div>
        <div class="message-text">${pendingRecommendation.text}</div>
        <div class="message-time">${getCurrentTime()}</div>
    `;

    if (operatorChat) {
        operatorChat.appendChild(operatorMessageDiv);
        operatorChat.scrollTop = operatorChat.scrollHeight;
    }

    // Отправляем сообщение в чат клиента
    addMessageToClientChat('Оператор', pendingRecommendation.text, false);

    // Обновляем статус
    const operatorStatus = document.getElementById('operator-status');
    if (operatorStatus) operatorStatus.textContent = 'Сообщение отправлено';

    // Сохраняем в БД
    await saveMessageToDB('operator', pendingRecommendation.text);
    await saveMessageToDB('ai_response', pendingRecommendation.text, false);

    // Сохраняем в историю
    chatHistories[currentChannel].operator.push({
        text: pendingRecommendation.text,
        sender: 'operator',
        time: getCurrentTime()
    });

    chatHistories[currentChannel].client.push({
        text: pendingRecommendation.text,
        isUser: false,
        time: getCurrentTime()
    });

    pendingRecommendation = null;

    // Очищаем поле ввода оператора
    const operatorInput = document.getElementById('operator-input');
    if (operatorInput) operatorInput.value = '';
}

// Отклонить рекомендацию
function rejectRecommendation() {
    const recommendationDiv = document.getElementById('current-recommendation');
    if (recommendationDiv) {
        recommendationDiv.remove();
    }

    const operatorChat = document.getElementById('operator-chat');
    if (operatorChat) {
        const rejectionDiv = document.createElement('div');
        rejectionDiv.className = 'message message-bot';
        rejectionDiv.innerHTML = `
            <div class="message-sender">Суфлёр AI</div>
            <div style="color: var(--gray); font-style: italic; padding: 0.5rem;">
                <i class="fas fa-times"></i> Рекомендация отклонена. Введите ответ вручную.
            </div>
        `;

        operatorChat.appendChild(rejectionDiv);
        operatorChat.scrollTop = operatorChat.scrollHeight;
    }

    const operatorStatus = document.getElementById('operator-status');
    if (operatorStatus) operatorStatus.textContent = 'Введите ответ вручную';

    const operatorInput = document.getElementById('operator-input');
    if (operatorInput) operatorInput.focus();

    pendingRecommendation = null;
}

// Добавить сообщение клиента в чат оператора
function addClientMessageToOperatorChat(message) {
    const emptyChat = document.getElementById('empty-operator-chat');
    if (emptyChat) {
        emptyChat.remove();
    }

    const operatorChat = document.getElementById('operator-chat');
    if (!operatorChat) return;

    const clientMessageDiv = document.createElement('div');
    clientMessageDiv.className = 'message message-user';
    clientMessageDiv.innerHTML = `
        <div class="message-sender">Клиент</div>
        <div class="message-text">${message}</div>
        <div class="message-time">${getCurrentTime()}</div>
    `;

    operatorChat.appendChild(clientMessageDiv);
    operatorChat.scrollTop = operatorChat.scrollHeight;

    chatHistories[currentChannel].operator.push({
        text: message,
        sender: 'client',
        time: getCurrentTime()
    });
}

// Добавить сообщение в чат клиента
function addMessageToClientChat(sender, message, isUser = false) {
    const chatContainer = document.getElementById('client-chat');
    if (!chatContainer) return;

    const emptyChat = document.getElementById('empty-client-chat');
    if (emptyChat) {
        emptyChat.remove();
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = isUser ? 'message message-user' : 'message message-bot';

    if (!isUser) {
        messageDiv.innerHTML = `
            <div class="message-sender">${sender}</div>
            <div class="message-text">${message}</div>
            <div class="message-time">${getCurrentTime()}</div>
        `;
    } else {
        messageDiv.innerHTML = `
            <div class="message-text">${message}</div>
            <div class="message-time">${getCurrentTime()}</div>
        `;
    }

    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;

    chatHistories[currentChannel].client.push({
        text: message,
        isUser: isUser,
        time: getCurrentTime()
    });
}

// Отправить сообщение клиента
async function sendClientMessage() {
    const input = document.getElementById('client-input');
    if (!input) return;

    const message = input.value.trim();

    if (message) {
        addMessageToClientChat('', message, true);
        addClientMessageToOperatorChat(message);

        // Сохраняем в БД
        await saveMessageToDB('client', message);

        // Получаем рекомендацию от AI
        await getAIRecommendation(message);

        input.value = '';
    }
}

// Отправить сообщение оператора
async function sendOperatorMessage() {
    const input = document.getElementById('operator-input');
    if (!input) return;

    const message = input.value.trim();

    if (message) {
        const recommendationDiv = document.getElementById('current-recommendation');
        if (recommendationDiv) {
            recommendationDiv.remove();
            pendingRecommendation = null;
        }

        const operatorChat = document.getElementById('operator-chat');
        if (operatorChat) {
            const operatorMessageDiv = document.createElement('div');
            operatorMessageDiv.className = 'message message-operator';
            operatorMessageDiv.innerHTML = `
                <div class="message-sender">Оператор</div>
                <div class="message-text">${message}</div>
                <div class="message-time">${getCurrentTime()}</div>
            `;

            operatorChat.appendChild(operatorMessageDiv);
            operatorChat.scrollTop = operatorChat.scrollHeight;
        }

        addMessageToClientChat('Оператор', message, false);

        input.value = '';

        const operatorStatus = document.getElementById('operator-status');
        if (operatorStatus) operatorStatus.textContent = 'Сообщение отправлено';

        // Сохраняем в БД
        await saveMessageToDB('operator', message);
        await saveMessageToDB('ai_response', message, false);

        chatHistories[currentChannel].operator.push({
            text: message,
            sender: 'operator',
            time: getCurrentTime()
        });
    }
}

// Сохранить сообщение в БД
async function saveMessageToDB(messageType, content, isTranscription = false) {
    if (!currentSessionId) return;

    try {
        const response = await fetch(`${DJANGO_API_BASE}/save-message/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                session_id: currentSessionId,
                message_type: messageType,
                content: content,
                is_transcription: isTranscription
            })
        });

        if (response.ok) {
            const data = await response.json();
            console.log('Сообщение сохранено:', data);
        } else {
            console.error('Ошибка API:', await response.text());
        }
    } catch (error) {
        console.error('Ошибка сохранения сообщения:', error);
    }
}

// Сохранить транскрипцию в БД
async function saveTranscriptionToDB(content) {
    if (!currentSessionId) return;

    try {
        const response = await fetch(`${DJANGO_API_BASE}/save-message/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                session_id: currentSessionId,
                message_type: 'client',
                content: content,
                is_transcription: true
            })
        });

        if (response.ok) {
            const data = await response.json();
            console.log('Транскрипция сохранена:', data);
        }
    } catch (error) {
        console.error('Ошибка сохранения транскрипции:', error);
    }
}

// Обработка частичной транскрипции
function handlePartialTranscription(text) {
    const container = document.getElementById('transcription-container');
    if (!container) return;

    let partialElement = document.getElementById('partial-transcription');
    if (partialElement) {
        partialElement.remove();
    }

    if (!text || text.trim() === '') return;

    console.log('Частичная транскрипция:', text);

    partialElement = document.createElement('div');
    partialElement.id = 'partial-transcription';
    partialElement.className = 'transcription-message partial-transcription';
    partialElement.innerHTML = `
        <div style="display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.3rem;">
            <i class="fas fa-microphone-alt" style="color: var(--warning);"></i>
            <span style="font-weight: 600; color: var(--warning);">Клиент говорит:</span>
        </div>
        <div>"${text}"</div>
        <div style="font-size: 0.7rem; color: var(--warning); margin-top: 0.4rem;">
            <i class="fas fa-sync-alt fa-spin"></i> Распознается...
        </div>
    `;

    container.appendChild(partialElement);
    container.scrollTop = container.scrollHeight;
}

// Обработка полной транскрипции
async function handleFinalTranscription(text) {
    const container = document.getElementById('transcription-container');
    if (!container) return;

    const partialElement = document.getElementById('partial-transcription');
    if (partialElement) {
        partialElement.remove();
    }

    if (!text || text.trim() === '') return;

    console.log('Полная транскрипция:', text);

    // Добавляем транскрипцию в историю
    const messageDiv = document.createElement('div');
    messageDiv.className = 'transcription-message';
    messageDiv.innerHTML = `
        <div style="display: flex; align-items: center; gap: 0.4rem; margin-bottom: 0.3rem;">
            <i class="fas fa-user" style="color: var(--primary);"></i>
            <span style="font-weight: 600; color: var(--primary);">Клиент сказал:</span>
        </div>
        <div style="margin-bottom: 0.4rem;">"${text}"</div>
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 0.7rem; color: var(--gray);">
                <i class="fas fa-clock"></i> ${getCurrentTime()}
            </span>
            <span style="font-size: 0.7rem; color: var(--gray);">
                <i class="fas fa-sync-alt fa-spin"></i> Запрос к AI...
            </span>
        </div>
    `;

    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight;

    // Сохраняем транскрипцию в БД
    await saveTranscriptionToDB(text);

    // Получаем рекомендацию от AI
    await getAIRecommendation(text, 'phone');
}

// Обновление контейнера транскрипции
function updateTranscriptionContainer(content, clear = false) {
    const container = document.getElementById('transcription-container');
    if (!container) return;

    if (clear) {
        container.innerHTML = content;
    } else {
        container.innerHTML += content;
    }
    container.scrollTop = container.scrollHeight;
}

// Получить текущее время
function getCurrentTime() {
    const now = new Date();
    return `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
}

// Получить CSRF токен
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Переключение роли пользователя (для тестирования)
function toggleUserRole() {
    const userNameElement = document.getElementById('current-user-name');
    const userRoleElement = document.getElementById('current-user-role');

    if (!userNameElement || !userRoleElement) return;

    if (userNameElement.textContent === 'Александр Петров') {
        userNameElement.textContent = 'Мария Иванова';
        userRoleElement.textContent = 'Оператор Контакт-центра';
    } else {
        userNameElement.textContent = 'Александр Петров';
        userRoleElement.textContent = 'Клиент банка';
    }
}

// Сделать функции глобальными
window.sendRecommendation = sendRecommendation;
window.rejectRecommendation = rejectRecommendation;
window.startCall = startCall;
window.endCall = endCall;