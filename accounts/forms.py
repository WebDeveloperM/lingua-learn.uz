from datetime import date

from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(label="Ism", max_length=150, required=True)
    last_name = forms.CharField(label="Familiya", max_length=150, required=True)
    birth_date = forms.DateField(
        label="Tug'ilgan kun",
        required=True,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    email = forms.EmailField(label="Email", required=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'birth_date', 'email', 'password1', 'password2']

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Bu email bilan allaqachon ro'yxatdan o'tilgan.")
        return email

    def clean_birth_date(self):
        birth_date = self.cleaned_data['birth_date']
        if birth_date >= date.today():
            raise forms.ValidationError("Tug'ilgan kun noto'g'ri kiritildi.")
        age = date.today().year - birth_date.year - (
            (date.today().month, date.today().day) < (birth_date.month, birth_date.day)
        )
        if age < 6:
            raise forms.ValidationError("Yoshingiz kamida 6 bo'lishi kerak.")
        if age > 120:
            raise forms.ValidationError("Tug'ilgan kun noto'g'ri kiritildi.")
        return birth_date

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = False
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    email = forms.EmailField(label="Email")
    password = forms.CharField(label="Parol", widget=forms.PasswordInput)
