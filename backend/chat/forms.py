from django import forms
from .models import Client

class ClientInfoForm(forms.ModelForm):
    """Форма ввода информации о клиенте"""
    class Meta:
        model = Client
        fields = ['first_name', 'last_name', 'phone', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Введите имя клиента',
                'autofocus': True
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Введите фамилию клиента'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+375 (XX) XXX-XX-XX'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@example.com'
            }),
        }
        labels = {
            'first_name': 'Имя',
            'last_name': 'Фамилия',
            'phone': 'Телефон (необязательно)',
            'email': 'Email (необязательно)',
        }