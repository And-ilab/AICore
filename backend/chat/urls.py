from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('client-info/', views.client_info, name='client_info'),
    path('chat/', views.chat_interface, name='chat_interface'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('reports/', views.reports, name='reports'),
    path('settings/', views.settings_view, name='settings'),
    path('chat/history/<int:session_id>/', views.chat_history, name='chat_history'),
    path('api/save-message/', views.save_message, name='save_message'),
    path('api/end-session/', views.end_session, name='end_session'),
    path('api/session-messages/<int:session_id>/', views.get_session_messages, name='get_session_messages'),
    path('api/save-session-history/', views.save_session_history, name='save_session_history'),
    path('api/session-history/<int:session_id>/<str:channel>/', views.get_session_history, name='get_session_history'),
]