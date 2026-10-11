from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.views.decorators.http import require_POST


@login_required
@require_POST
def complete(request):
    profile = request.user.profile
    if not profile.onboarding_completed:
        profile.onboarding_completed = True
        profile.save(update_fields=["onboarding_completed"])

    return HttpResponse(status=204)
