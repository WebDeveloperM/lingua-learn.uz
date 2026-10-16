from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import LoginForm, RegisterForm
from .models import User


def register_view(request):
    if request.user.is_authenticated:
        return redirect(request.user.get_home_url())

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('accounts:register_done')
    else:
        form = RegisterForm()

    return render(request, 'accounts/register.html', {'form': form})


def register_done_view(request):
    return render(request, 'accounts/register_done.html', {
        'admin_telegram_url': settings.ADMIN_TELEGRAM_URL,
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect(request.user.get_home_url())

    pending_activation = False
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(request, username=email, password=password)
            if user is not None:
                login(request, user)
                next_url = request.GET.get('next')
                if not url_has_allowed_host_and_scheme(
                    next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
                ):
                    next_url = user.get_home_url()
                return redirect(next_url)

            inactive_user = User.objects.filter(email__iexact=email, is_active=False).first()
            if inactive_user and inactive_user.check_password(password):
                pending_activation = True
            else:
                form.add_error(None, "Login yoki parol noto'g'ri.")
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {
        'form': form,
        'pending_activation': pending_activation,
        'admin_telegram_url': settings.ADMIN_TELEGRAM_URL,
    })


def logout_view(request):
    logout(request)
    return redirect('core:home')
