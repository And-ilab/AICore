from django.urls import path

from auth.views import auth_context, auth_login, auth_logout


urlpatterns = [
    path("me/", auth_context, name="auth_context"),
    path("login/", auth_login, name="auth_login"),
    path("logout/", auth_logout, name="auth_logout"),
]
