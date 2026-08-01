from .models import User


def notify_new_user_signup(user: User) -> None:
    """Post a new-signup alert into the team's Telegram group."""
    from core.telegram import send_telegram_message

    send_telegram_message(f"\U0001f195 New user signed up: {user.email}")
