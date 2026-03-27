"""
Authentication views for login and logout functionality.
"""
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.views.decorators.http import require_http_methods


@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Handle user login.

    GET: Display login form
    POST: Process login credentials
    """
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)

            if user is not None:
                login(request, user)
                messages.success(request, f'欢迎回来, {username}!')
                # 登录成功后跳转到 next 参数，或默认首页
                next_url = request.POST.get('next') or request.GET.get('next') or 'home'
                return redirect(next_url)
            else:
                messages.error(request, '用户名或密码错误。')
        else:
            messages.error(request, '用户名或密码错误。')
    else:
        form = AuthenticationForm()

    return render(request, 'accounts/login.html', {'form': form})


@require_http_methods(["POST"])
def logout_view(request):
    """
    Handle user logout.

    POST: Process logout request
    """
    logout(request)
    messages.info(request, '您已成功登出。')
    return redirect('accounts:login')
