from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from .forms import RegisterForm


def home(request):
    """/ — login page if logged out; redirect to leaderboard if logged in."""
    if request.user.is_authenticated:
        return redirect('pool:leaderboard')

    form = AuthenticationForm()
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect('pool:leaderboard')

    return render(request, 'accounts/login.html', {'form': form})


def register(request):
    """/register/ — create a new account."""
    if request.user.is_authenticated:
        return redirect('pool:leaderboard')

    form = RegisterForm()
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome, {user.username}! Your account has been created.')
            return redirect('pool:leaderboard')

    return render(request, 'accounts/register.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('accounts:home')
