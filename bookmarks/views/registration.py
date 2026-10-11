from django.conf import settings
from django.contrib.auth import login
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from bookmarks.forms import RegistrationForm
from bookmarks.services import registration
from bookmarks.services.registration import VerificationError


def _ensure_enabled():
    if not settings.LD_ENABLE_REGISTRATION:
        raise Http404()


def register(request):
    _ensure_enabled()
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    return render(
        request,
        "registration/register.html",
        {
            "form": RegistrationForm(),
            "code_length": registration.CODE_LENGTH,
            "resend_interval": registration.RESEND_INTERVAL_SECONDS,
        },
    )


@require_POST
def send_code(request):
    _ensure_enabled()
    if request.user.is_authenticated:
        return JsonResponse({"errors": {"__all__": ["You are logged in."]}}, status=403)

    form = RegistrationForm(request.POST)
    if not form.is_valid():
        errors = {
            field: [str(error) for error in field_errors]
            for field, field_errors in form.errors.items()
        }
        return JsonResponse({"errors": errors}, status=422)

    sent = registration.send_verification_code(
        request,
        form.cleaned_data["username"],
        form.cleaned_data["email"],
        form.cleaned_data["password"],
    )
    if not sent:
        message = "A code was sent to this address a moment ago. Please wait before requesting another."
        return JsonResponse({"errors": {"__all__": [message]}}, status=429)

    return JsonResponse({"sent": True})


@require_POST
def verify_code(request):
    _ensure_enabled()
    code = request.POST.get("code", "").strip()
    if len(code) != registration.CODE_LENGTH or not code.isdigit():
        return JsonResponse(
            {
                "error": f"Enter the {registration.CODE_LENGTH}-digit code.",
                "restart": False,
            },
            status=422,
        )

    try:
        user = registration.verify_code_and_create_user(request, code)
    except VerificationError as e:
        return JsonResponse({"error": e.message, "restart": e.restart}, status=422)

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return JsonResponse({"verified": True, "redirect_url": reverse("linkding:root")})
