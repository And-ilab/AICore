from __future__ import annotations

from typing import ClassVar

from django.contrib import admin

from online_chat.models import (
    ChannelConnection,
    BotConfiguration,
    ClientBlock,
    Dialog,
    DialogFeedback,
    DialogMessage,
    DialogTranscriptEmail,
    Department,
    DialogEvent,
    InternalMessage,
    OperatorProfile,
    RoutingRule,
    WidgetPlacement,
)


class DialogMessageInline(admin.TabularInline):
    model = DialogMessage
    extra = 0
    readonly_fields = ("id", "speaker", "text", "created_at")


class DialogFeedbackInline(admin.StackedInline):
    model = DialogFeedback
    extra = 0
    readonly_fields = ("id", "rating", "comment", "created_at")


class DialogTranscriptEmailInline(admin.TabularInline):
    model = DialogTranscriptEmail
    extra = 0
    readonly_fields = (
        "id",
        "email",
        "status",
        "error_detail",
        "created_at",
        "sent_at",
    )


@admin.register(Dialog)
class DialogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client_first_name",
        "client_last_name",
        "status",
        "close_topic",
        "channel",
        "updated_at",
    )
    list_filter = ("status", "channel", "close_topic")
    search_fields = ("client_first_name", "client_last_name", "client_phone", "preview")
    inlines: ClassVar[list] = [
        DialogMessageInline,
        DialogFeedbackInline,
        DialogTranscriptEmailInline,
    ]


@admin.register(DialogMessage)
class DialogMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "dialog", "speaker", "created_at")
    list_filter = ("speaker",)


@admin.register(DialogFeedback)
class DialogFeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "dialog", "rating", "created_at")
    list_filter = ("rating",)


@admin.register(DialogTranscriptEmail)
class DialogTranscriptEmailAdmin(admin.ModelAdmin):
    list_display = ("id", "dialog", "email", "status", "created_at", "sent_at")
    list_filter = ("status",)
    search_fields = ("email",)


@admin.register(ClientBlock)
class ClientBlockAdmin(admin.ModelAdmin):
    list_display = (
        "phone_normalized",
        "is_active",
        "blocked_by",
        "created_at",
        "lifted_at",
    )
    list_filter = ("is_active",)
    search_fields = ("phone", "phone_normalized", "reason")
    actions = ("lift_blocks",)

    @admin.action(description="Снять блокировку")
    def lift_blocks(self, request, queryset):
        from online_chat.services import unblock_client

        for block in queryset.filter(is_active=True):
            unblock_client(block, lifted_by=request.user.get_username() or "admin")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "priority", "max_queue_size")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(OperatorProfile)
class OperatorProfileAdmin(admin.ModelAdmin):
    list_display = ("external_id", "display_name", "role", "presence", "is_active")
    list_filter = ("role", "presence", "is_active", "departments")
    search_fields = ("external_id", "display_name", "email")
    filter_horizontal = ("departments",)


@admin.register(WidgetPlacement)
class WidgetPlacementAdmin(admin.ModelAdmin):
    list_display = ("widget_id", "name", "department", "is_active")
    list_filter = ("is_active", "department")
    search_fields = ("widget_id", "name", "site_url")


@admin.register(ChannelConnection)
class ChannelConnectionAdmin(admin.ModelAdmin):
    list_display = ("name", "channel", "department", "is_active", "health_status")
    list_filter = ("channel", "is_active", "health_status")


@admin.register(RoutingRule)
class RoutingRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "priority", "channel", "department", "is_active")
    list_filter = ("is_active", "channel", "department")


@admin.register(BotConfiguration)
class BotConfigurationAdmin(admin.ModelAdmin):
    list_display = ("name", "department", "is_active", "max_bot_turns")
    list_filter = ("is_active", "department")


@admin.register(InternalMessage)
class InternalMessageAdmin(admin.ModelAdmin):
    list_display = ("sender", "recipient", "dialog", "created_at", "read_at")
    search_fields = ("text", "sender__display_name", "recipient__display_name")


@admin.register(DialogEvent)
class DialogEventAdmin(admin.ModelAdmin):
    list_display = ("dialog", "type", "actor_name", "created_at")
    list_filter = ("type",)
    readonly_fields = ("dialog", "type", "actor_name", "payload", "created_at")

