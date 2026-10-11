import secrets
import time

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.crypto import constant_time_compare, salted_hmac

SESSION_KEY = "pending_registration"
CODE_LENGTH = 6
CODE_TTL_SECONDS = 10 * 60
RESEND_INTERVAL_SECONDS = 60
MAX_ATTEMPTS = 5


class VerificationError(Exception):
    """
    Raised when a code can not be verified. If `restart` is true the pending
    registration has been discarded and the user has to request a new code.
    """

    def __init__(self, message, restart=False):
        super().__init__(message)
        self.message = message
        self.restart = restart


def username_exists(username):
    return User.objects.filter(username__iexact=username).exists()


def email_exists(email):
    return User.objects.filter(email__iexact=email).exists()


def _hash_code(code, email):
    return salted_hmac("linkding.registration", f"{email.lower()}:{code}").hexdigest()


def generate_code():
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


def send_verification_code(request, username, email, password):
    """
    Sends a verification code to the e-mail address and stores the pending
    registration in the session. The user is only created once the code has
    been verified. Returns False if a code was sent to the address recently.
    """
    throttle_key = "registration-code-" + _hash_code("throttle", email)
    if not cache.add(throttle_key, True, RESEND_INTERVAL_SECONDS):
        return False

    code = generate_code()
    request.session[SESSION_KEY] = {
        "username": username,
        "email": email,
        "password_hash": make_password(password),
        "code_hash": _hash_code(code, email),
        "expires_at": time.time() + CODE_TTL_SECONDS,
        "attempts": 0,
    }

    context = {
        "code": code,
        "username": username,
        "expires_in_minutes": CODE_TTL_SECONDS // 60,
    }
    message = EmailMultiAlternatives(
        subject=f"{code} is your linkding verification code",
        body=render_to_string("registration/verification_email.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    message.attach_alternative(
        render_to_string("registration/verification_email.html", context),
        "text/html",
    )
    try:
        message.send()
    except Exception:
        # Do not make the user wait out the throttle for a failed delivery
        cache.delete(throttle_key)
        clear_pending_registration(request)
        raise
    return True


def get_pending_registration(request):
    return request.session.get(SESSION_KEY)


def clear_pending_registration(request):
    request.session.pop(SESSION_KEY, None)


def verify_code_and_create_user(request, code):
    pending = get_pending_registration(request)
    if not pending:
        raise VerificationError(
            "There is no pending registration. Please request a new code.",
            restart=True,
        )

    if time.time() > pending["expires_at"]:
        clear_pending_registration(request)
        raise VerificationError(
            "This code has expired. Please request a new one.", restart=True
        )

    pending["attempts"] += 1
    if not constant_time_compare(
        _hash_code(code, pending["email"]), pending["code_hash"]
    ):
        if pending["attempts"] >= MAX_ATTEMPTS:
            clear_pending_registration(request)
            raise VerificationError(
                "Too many incorrect attempts. Please request a new code.",
                restart=True,
            )
        request.session[SESSION_KEY] = pending
        raise VerificationError("Incorrect code. Please try again.")

    # Somebody else may have taken the name in the meantime
    if username_exists(pending["username"]) or email_exists(pending["email"]):
        clear_pending_registration(request)
        raise VerificationError(
            "This username or e-mail address is no longer available.", restart=True
        )

    user = User.objects.create(
        username=pending["username"],
        email=pending["email"],
        password=pending["password_hash"],
    )
    clear_pending_registration(request)
    return user
