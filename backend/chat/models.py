from django.db import models
from django.utils import timezone
import uuid


class Client(models.Model):
    """Модель клиента"""
    first_name = models.CharField(max_length=100, verbose_name="Имя")
    last_name = models.CharField(max_length=100, verbose_name="Фамилия")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Телефон")
    email = models.EmailField(blank=True, verbose_name="Email")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    session_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class ChatSession(models.Model):
    """Сессия чата"""
    CHANNEL_CHOICES = [
        ('chat', 'Онлайн-чат'),
        ('telegram', 'Telegram'),
        ('viber', 'Viber'),
        ('whatsapp', 'WhatsApp'),
        ('phone', 'Телефонный звонок'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='chat_sessions', verbose_name="Клиент")
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='chat', verbose_name="Канал")
    ai_session_id = models.CharField(max_length=100, blank=True, verbose_name="ID сессии AI")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Начало сессии")
    ended_at = models.DateTimeField(null=True, blank=True, verbose_name="Окончание сессии")
    is_active = models.BooleanField(default=True, verbose_name="Активна")
    # Добавляем поле для хранения истории каналов
    chat_history = models.JSONField(default=dict, blank=True, verbose_name="История по каналам")

    class Meta:
        verbose_name = "Сессия чата"
        verbose_name_plural = "Сессии чатов"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.client} - {self.get_channel_display()} ({self.created_at.strftime('%d.%m.%Y %H:%M')})"

    def save_channel_history(self, channel, messages):
        """Сохранить историю для канала"""
        if not self.chat_history:
            self.chat_history = {}
        self.chat_history[channel] = messages
        self.save()

    def get_channel_history(self, channel):
        """Получить историю для канала"""
        return self.chat_history.get(channel, [])


class Message(models.Model):
    """Сообщение в чате"""
    MESSAGE_TYPES = [
        ('client', 'Клиент'),
        ('operator', 'Оператор'),
        ('ai_recommendation', 'Рекомендация AI'),
        ('ai_response', 'Ответ AI'),
    ]

    # Убедитесь, что связь правильная
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='messages',  # Это важно!
        verbose_name="Сессия"
    )
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, verbose_name="Тип сообщения")
    content = models.TextField(verbose_name="Текст сообщения")
    timestamp = models.DateTimeField(default=timezone.now, verbose_name="Время отправки")
    is_transcription = models.BooleanField(default=False, verbose_name="Транскрипция")

    class Meta:
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.get_message_type_display()}: {self.content[:50]}..."


class CallLog(models.Model):
    """Лог звонков"""
    session = models.OneToOneField(ChatSession, on_delete=models.CASCADE, related_name='call_log',
                                   verbose_name="Сессия")
    start_time = models.DateTimeField(auto_now_add=True, verbose_name="Время начала")
    end_time = models.DateTimeField(null=True, blank=True, verbose_name="Время окончания")
    duration = models.IntegerField(default=0, verbose_name="Длительность (сек)")
    transcription = models.TextField(blank=True, verbose_name="Транскрипция")

    class Meta:
        verbose_name = "Лог звонка"
        verbose_name_plural = "Логи звонков"

    def __str__(self):
        return f"Звонок {self.session.client} - {self.duration}сек"