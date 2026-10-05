from django.contrib import admin
from .models import Client, ChatSession, Message, CallLog


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone', 'email', 'created_at')
    search_fields = ('first_name', 'last_name', 'phone', 'email')
    list_filter = ('created_at',)


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('client', 'channel', 'created_at', 'is_active')
    list_filter = ('channel', 'is_active', 'created_at')
    search_fields = ('client__first_name', 'client__last_name')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'message_type', 'short_content', 'timestamp')
    list_filter = ('message_type', 'timestamp', 'is_transcription')
    search_fields = ('content',)

    def short_content(self, obj):
        return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content

    short_content.short_description = 'Содержание'


@admin.register(CallLog)
class CallLogAdmin(admin.ModelAdmin):
    list_display = ('session', 'start_time', 'duration')
    list_filter = ('start_time',)