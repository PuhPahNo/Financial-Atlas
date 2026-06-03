from app.core.auth import create_session_token
from app.core.config import settings


def authenticate(client):
    client.cookies.set(settings.auth_cookie_name, create_session_token(settings.auth_username))
    return client
