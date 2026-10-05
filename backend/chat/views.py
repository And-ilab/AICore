from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import uuid
from .models import Client, ChatSession, Message, CallLog
from .forms import ClientInfoForm
from django.utils import timezone
from datetime import timedelta
import json
from django.db.models import Count


def dashboard(request):
    """Дашборд с историей чатов"""
    # Получаем всех клиентов и сессии
    clients = Client.objects.all().order_by('-created_at')[:50]
    recent_sessions = ChatSession.objects.all().order_by('-created_at')[:20]

    # Статистика - считаем ВСЕ сообщения через отдельный запрос
    total_clients = Client.objects.count()
    total_messages = Message.objects.count()  # Это должно работать!
    total_calls = CallLog.objects.count()

    # Добавляем количество сообщений к каждой сессии
    for session in recent_sessions:
        session.message_count = Message.objects.filter(session=session).count()

    context = {
        'clients': clients,
        'recent_sessions': recent_sessions,
        'total_clients': total_clients,
        'total_messages': total_messages,
        'total_calls': total_calls,
    }

    return render(request, 'dashboard.html', context)


def reports(request):
    """Страница отчетов с реальной статистикой"""
    # Общая статистика
    total_sessions = ChatSession.objects.count()
    total_messages = Message.objects.count()  # Используем прямой подсчет
    total_clients = Client.objects.count()

    # Сегодняшние данные
    today = timezone.now().date()
    new_sessions_today = ChatSession.objects.filter(created_at__date=today).count()
    new_clients_today = Client.objects.filter(created_at__date=today).count()

    # Средние значения
    avg_messages_per_session = total_messages / total_sessions if total_sessions > 0 else 0
    avg_messages_per_session = round(avg_messages_per_session, 1)

    # Статистика по звонкам
    call_logs = CallLog.objects.all()
    call_duration = sum([log.duration for log in call_logs]) // 60 if call_logs else 0  # в минутах
    avg_call_duration = round(call_duration / len(call_logs) if call_logs else 0, 1)

    # Распределение по каналам
    channel_stats = []
    channel_counts = ChatSession.objects.values('channel').annotate(count=Count('id'))
    total_channel_sessions = sum([item['count'] for item in channel_counts])

    CHANNEL_DISPLAY_NAMES = {
        'chat': 'Онлайн-чат',
        'telegram': 'Telegram',
        'viber': 'Viber',
        'whatsapp': 'WhatsApp',
        'phone': 'Телефонный звонок'
    }

    for item in channel_counts:
        percentage = round((item['count'] / total_channel_sessions) * 100, 1) if total_channel_sessions > 0 else 0
        channel_stats.append({
            'name': item['channel'],
            'display_name': CHANNEL_DISPLAY_NAMES.get(item['channel'], item['channel']),
            'count': item['count'],
            'percentage': percentage
        })

    # Активность за последние 7 дней
    activity_days = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        day_sessions = ChatSession.objects.filter(created_at__date=date).count()
        # Также считаем сообщения за день
        day_messages = Message.objects.filter(timestamp__date=date).count()
        activity_days.append({
            'date': date.strftime('%d.%m'),
            'count': day_sessions,
            'messages': day_messages
        })

    # Находим пиковый день
    peak_day = max(activity_days, key=lambda x: x['count'], default={'day': 'Нет данных', 'count': 0})
    avg_sessions_per_day = round(sum([day['count'] for day in activity_days]) / 7, 1)

    # Статистика AI рекомендаций
    # Сначала получим все сообщения типа рекомендаций
    ai_recommendations = Message.objects.filter(message_type='ai_recommendation').count()
    ai_responses = Message.objects.filter(message_type='ai_response').count()

    ai_stats = {
        'total_recommendations': ai_recommendations,
        'accepted': ai_responses,  # считаем, что все ответы AI были приняты
        'rejected': 0,  # нужно добавить логику отслеживания отклонений
        'accepted_percentage': round((ai_responses / ai_recommendations * 100) if ai_recommendations > 0 else 0, 1),
        'rejected_percentage': 0
    }

    # Топ клиентов по активности - используем сырые SQL запросы для точного подсчета
    from django.db import connection

    # Запрос для получения топ клиентов с количеством сообщений
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                c.id,
                c.first_name,
                c.last_name,
                c.email,
                COUNT(DISTINCT cs.id) as session_count,
                COUNT(m.id) as message_count,
                MAX(cs.created_at) as last_active
            FROM chat_client c
            LEFT JOIN chat_chatsession cs ON c.id = cs.client_id
            LEFT JOIN chat_message m ON cs.id = m.session_id
            GROUP BY c.id, c.first_name, c.last_name, c.email
            ORDER BY message_count DESC
            LIMIT 5
        """)
        rows = cursor.fetchall()

    top_clients = []
    for row in rows:
        client_id, first_name, last_name, email, session_count, message_count, last_active = row
        top_clients.append({
            'full_name': f"{first_name} {last_name}",
            'email': email if email else '',
            'session_count': session_count or 0,
            'message_count': message_count or 0,
            'last_active': last_active
        })

    context = {
        'total_sessions': total_sessions,
        'total_messages': total_messages,
        'total_clients': total_clients,
        'new_sessions_today': new_sessions_today,
        'new_clients_today': new_clients_today,
        'avg_messages_per_session': avg_messages_per_session,
        'call_duration': call_duration,
        'avg_call_duration': avg_call_duration,
        'channel_stats': channel_stats,
        'activity_days': activity_days,
        'peak_day': peak_day,
        'avg_sessions_per_day': avg_sessions_per_day,
        'ai_stats': ai_stats,
        'top_clients': top_clients,
    }

    return render(request, 'reports.html', context)


def index(request):
    """Главная страница - форма ввода данных клиента"""
    return redirect('client_info')


def client_info(request):
    """Ввод данных клиента"""
    if request.method == 'POST':
        form = ClientInfoForm(request.POST)
        if form.is_valid():
            client = form.save()

            # Сохраняем данные клиента в сессии
            request.session['client_id'] = client.id
            request.session['client_name'] = f"{client.first_name} {client.last_name}"
            request.session['client_session_id'] = str(client.session_id)

            return redirect('chat_interface')
    else:
        form = ClientInfoForm()

    return render(request, 'client_info.html', {'form': form})


def chat_interface(request):
    """Основной интерфейс чата"""
    # Проверяем, есть ли данные клиента в сессии
    if 'client_id' not in request.session:
        return redirect('client_info')

    client_id = request.session['client_id']
    client_name = request.session['client_name']

    # Получаем или создаем активную сессию чата
    client = get_object_or_404(Client, id=client_id)

    # Ищем активную сессию или создаем новую
    chat_session, created = ChatSession.objects.get_or_create(
        client=client,
        is_active=True,
        defaults={
            'channel': 'chat',
            'ai_session_id': str(uuid.uuid4())
        }
    )

    # Загружаем историю сообщений
    messages = chat_session.messages.all().order_by('timestamp')

    context = {
        'client': client,
        'client_name': client_name,
        'chat_session': chat_session,
        'messages': messages,
        'api_url': 'http://localhost:8000',  # URL AI API
    }

    return render(request, 'index.html', context)

def settings_view(request):
    """Страница настроек"""
    return render(request, 'settings.html')


def chat_history(request, session_id):
    """История конкретного чата"""
    chat_session = get_object_or_404(ChatSession, id=session_id)
    messages = chat_session.messages.all().order_by('timestamp')

    context = {
        'chat_session': chat_session,
        'messages': messages,
    }

    return render(request, 'chat_history.html', context)


@csrf_exempt
@require_POST
def save_message(request):
    """Сохранение сообщения через AJAX"""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        message_type = data.get('message_type')
        content = data.get('content')
        is_transcription = data.get('is_transcription', False)

        print(f"Сохранение сообщения: session_id={session_id}, type={message_type}, content={content}")

        chat_session = get_object_or_404(ChatSession, id=session_id)

        message = Message.objects.create(
            session=chat_session,
            message_type=message_type,
            content=content,
            is_transcription=is_transcription,
            timestamp=timezone.now()
        )

        print(f"Сообщение сохранено с ID: {message.id}")

        return JsonResponse({
            'success': True,
            'message_id': message.id,
            'timestamp': message.timestamp.strftime('%H:%M')
        })
    except Exception as e:
        print(f"Ошибка сохранения сообщения: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
@require_POST
def end_session(request):
    """Завершение сессии"""
    if 'client_id' in request.session:
        del request.session['client_id']
    if 'client_name' in request.session:
        del request.session['client_name']
    if 'client_session_id' in request.session:
        del request.session['client_session_id']

    return JsonResponse({'success': True})


def get_session_messages(request, session_id):
    """Получение сообщений сессии"""
    chat_session = get_object_or_404(ChatSession, id=session_id)
    messages = chat_session.messages.all().order_by('timestamp')

    messages_data = []
    for msg in messages:
        messages_data.append({
            'id': msg.id,
            'type': msg.message_type,
            'content': msg.content,
            'sender': msg.sender_name(),
            'timestamp': msg.timestamp.strftime('%H:%M'),
            'is_transcription': msg.is_transcription,
        })

    return JsonResponse({'messages': messages_data})


@csrf_exempt
@require_POST
def save_session_history(request):
    """Сохранение истории сессии по каналам"""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        channel = data.get('channel')
        messages = data.get('messages', [])

        chat_session = get_object_or_404(ChatSession, id=session_id)

        # Сохраняем историю в JSON поле
        if not chat_session.chat_history:
            chat_session.chat_history = {}

        chat_session.chat_history[channel] = messages
        chat_session.save()

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
def get_session_history(request, session_id, channel):
    """Получение истории сессии по каналу"""
    try:
        chat_session = get_object_or_404(ChatSession, id=session_id)
        history = chat_session.chat_history.get(channel, [])

        return JsonResponse({'history': history})
    except Exception as e:
        return JsonResponse({'error': str(e)})