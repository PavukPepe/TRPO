from django.conf import settings
from django.core.mail import send_mail


def _send(subject, body, to_email):
    send_mail(
        subject=subject,
        message='',
        html_message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to_email],
        fail_silently=False,
    )


def _base_html(title, content):
    return f"""
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f4f4f5; margin: 0; padding: 32px; }}
  .card {{ background: #fff; border-radius: 12px; max-width: 480px;
           margin: 0 auto; padding: 40px; box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
  h1 {{ font-size: 22px; color: #0f172a; margin: 0 0 12px; }}
  p  {{ font-size: 15px; color: #475569; line-height: 1.6; margin: 0 0 20px; }}
  a.btn {{ display: inline-block; background: #3b82f6; color: #fff;
           text-decoration: none; padding: 12px 28px; border-radius: 8px;
           font-size: 15px; font-weight: 600; }}
  .footer {{ font-size: 12px; color: #94a3b8; margin-top: 28px; }}
</style></head>
<body>
  <div class="card">
    <h1>{title}</h1>
    {content}
    <p class="footer">MultiChat Hub &mdash; письмо отправлено автоматически, не отвечайте на него.</p>
  </div>
</body>
</html>"""


def send_invite_email(user, token):
    url = f"{settings.FRONTEND_URL}/set-password?token={token.token}"
    content = f"""
    <p>Администратор пригласил вас в систему <strong>MultiChat Hub</strong>.</p>
    <p>Нажмите кнопку ниже, чтобы задать пароль и войти в систему.
       Ссылка действует <strong>72 часа</strong>.</p>
    <p><a class="btn" href="{url}">Задать пароль</a></p>
    <p>Если вы не ожидали это письмо — просто проигнорируйте его.</p>"""
    _send('Приглашение в MultiChat Hub', _base_html('Добро пожаловать!', content), user.email)


def send_password_reset_email(user, token):
    url = f"{settings.FRONTEND_URL}/set-password?token={token.token}&mode=reset"
    content = f"""
    <p>Мы получили запрос на сброс пароля для аккаунта <strong>{user.email}</strong>.</p>
    <p>Нажмите кнопку ниже, чтобы задать новый пароль.
       Ссылка действует <strong>2 часа</strong>.</p>
    <p><a class="btn" href="{url}">Сбросить пароль</a></p>
    <p>Если вы не запрашивали сброс — просто проигнорируйте это письмо.</p>"""
    _send('Сброс пароля — MultiChat Hub', _base_html('Сброс пароля', content), user.email)
