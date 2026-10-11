import time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from bookmarks.services import registration
from bookmarks.tests.helpers import BookmarkFactoryMixin, HtmlTestMixin


@override_settings(LD_ENABLE_REGISTRATION=True)
class RegistrationTestCase(TestCase, BookmarkFactoryMixin, HtmlTestMixin):
    valid_data = {
        "username": "newuser",
        "email": "new@example.com",
        "password": "a-Strong-passw0rd!",
    }

    def setUp(self):
        cache.clear()

    def send_code(self, **overrides):
        data = {**self.valid_data, **overrides}
        return self.client.post(reverse("register_send_code"), data)

    def get_sent_code(self):
        self.assertEqual(len(mail.outbox), 1)
        match = [part for part in mail.outbox[0].subject.split() if part.isdigit()]
        self.assertEqual(len(match), 1)
        return match[0]

    def verify(self, code):
        return self.client.post(reverse("register_verify_code"), {"code": code})

    # Availability

    @override_settings(LD_ENABLE_REGISTRATION=False)
    def test_disabled_by_default(self):
        self.assertEqual(self.client.get(reverse("register")).status_code, 404)
        self.assertEqual(self.send_code().status_code, 404)
        self.assertEqual(self.verify("123456").status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

        response = self.client.get(reverse("login"))
        self.assertNotContains(response, "Create an account")

    def test_login_page_links_to_registration(self):
        response = self.client.get(reverse("login"))
        soup = self.make_soup(response.content.decode())

        link = soup.find("a", string="Create an account")
        self.assertIsNotNone(link)
        self.assertEqual(link["href"], reverse("register"))

    def test_registration_page_has_form_fields(self):
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)
        soup = self.make_soup(response.content.decode())

        self.assertIsNotNone(soup.find("input", {"name": "username"}))
        self.assertIsNotNone(soup.find("input", {"name": "email", "type": "email"}))
        self.assertIsNotNone(
            soup.find("input", {"name": "password", "type": "password"})
        )
        self.assertIsNotNone(soup.find("input", {"name": "code"}))

    def test_registration_page_redirects_authenticated_user(self):
        self.client.force_login(self.setup_user())
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 302)

    # Sending the code

    def test_send_code_sends_email_with_six_digit_code(self):
        response = self.send_code()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"sent": True})
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["new@example.com"])
        code = self.get_sent_code()
        self.assertEqual(len(code), 6)
        self.assertIn(code, message.body)
        self.assertIn(code, message.alternatives[0][0])

    def test_send_code_does_not_create_user(self):
        self.send_code()
        self.assertFalse(User.objects.filter(username="newuser").exists())

    def test_send_code_does_not_store_plain_password_or_code(self):
        self.send_code()
        code = self.get_sent_code()

        pending = self.client.session[registration.SESSION_KEY]
        self.assertNotIn(self.valid_data["password"], str(pending))
        self.assertNotIn(code, str(pending))

    def test_send_code_rejects_existing_username(self):
        self.setup_user(name="NewUser")
        response = self.send_code()

        self.assertEqual(response.status_code, 422)
        self.assertIn("username", response.json()["errors"])
        self.assertEqual(len(mail.outbox), 0)

    def test_send_code_rejects_existing_email(self):
        User.objects.create_user("other", "NEW@example.com", "password123")
        response = self.send_code()

        self.assertEqual(response.status_code, 422)
        self.assertIn("email", response.json()["errors"])
        self.assertEqual(len(mail.outbox), 0)

    def test_send_code_rejects_invalid_email(self):
        response = self.send_code(email="not-an-email")

        self.assertEqual(response.status_code, 422)
        self.assertIn("email", response.json()["errors"])

    def test_send_code_rejects_weak_password(self):
        response = self.send_code(password="123")

        self.assertEqual(response.status_code, 422)
        self.assertIn("password", response.json()["errors"])
        self.assertEqual(len(mail.outbox), 0)

    def test_send_code_rejects_missing_fields(self):
        response = self.client.post(reverse("register_send_code"), {})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            set(response.json()["errors"]), {"username", "email", "password"}
        )

    def test_send_code_requires_post(self):
        response = self.client.get(reverse("register_send_code"))
        self.assertEqual(response.status_code, 405)

    def test_send_code_is_throttled_per_address(self):
        self.assertEqual(self.send_code().status_code, 200)
        response = self.send_code()

        self.assertEqual(response.status_code, 429)
        self.assertEqual(len(mail.outbox), 1)

    def test_resending_replaces_previous_code(self):
        self.send_code()
        first_code = self.get_sent_code()
        cache.clear()
        mail.outbox.clear()
        # Make sure the second code differs from the first
        replacement = "000000" if first_code != "000000" else "111111"
        with patch.object(registration, "generate_code", return_value=replacement):
            self.send_code()
        second_code = self.get_sent_code()

        self.assertNotEqual(first_code, second_code)
        response = self.verify(first_code)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.verify(second_code).status_code, 200)

    # Verifying the code

    def test_verify_correct_code_creates_user_and_logs_in(self):
        self.send_code()
        response = self.verify(self.get_sent_code())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"verified": True, "redirect_url": reverse("linkding:root")},
        )
        user = User.objects.get(username="newuser")
        self.assertEqual(user.email, "new@example.com")
        self.assertTrue(user.check_password(self.valid_data["password"]))
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        self.assertTrue(hasattr(user, "profile"))

    def test_verify_clears_pending_registration(self):
        self.send_code()
        code = self.get_sent_code()
        self.verify(code)

        self.assertNotIn(registration.SESSION_KEY, self.client.session)
        self.assertEqual(self.verify(code).status_code, 422)
        self.assertEqual(User.objects.filter(username="newuser").count(), 1)

    def test_verify_wrong_code_returns_error_and_creates_no_user(self):
        self.send_code()
        code = self.get_sent_code()
        wrong = "000000" if code != "000000" else "111111"
        response = self.verify(wrong)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "Incorrect code. Please try again.")
        self.assertFalse(response.json()["restart"])
        self.assertFalse(User.objects.filter(username="newuser").exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_verify_wrong_code_can_be_retried(self):
        self.send_code()
        code = self.get_sent_code()
        wrong = "000000" if code != "000000" else "111111"
        self.verify(wrong)

        self.assertEqual(self.verify(code).status_code, 200)

    def test_verify_invalidates_code_after_too_many_attempts(self):
        self.send_code()
        code = self.get_sent_code()
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(registration.MAX_ATTEMPTS - 1):
            self.assertFalse(self.verify(wrong).json()["restart"])
        response = self.verify(wrong)

        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.json()["restart"])
        # Even the right code no longer works
        self.assertEqual(self.verify(code).status_code, 422)
        self.assertFalse(User.objects.filter(username="newuser").exists())

    def test_verify_rejects_expired_code(self):
        self.send_code()
        code = self.get_sent_code()
        session = self.client.session
        session[registration.SESSION_KEY]["expires_at"] = time.time() - 1
        session.save()
        response = self.verify(code)

        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.json()["restart"])
        self.assertFalse(User.objects.filter(username="newuser").exists())

    def test_verify_without_pending_registration(self):
        response = self.verify("123456")

        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.json()["restart"])

    def test_verify_rejects_malformed_code(self):
        self.send_code()
        for value in ["", "12345", "1234567", "abcdef"]:
            response = self.verify(value)
            self.assertEqual(response.status_code, 422)
            self.assertFalse(response.json()["restart"])

        # malformed input does not use up attempts
        self.assertEqual(self.client.session[registration.SESSION_KEY]["attempts"], 0)

    def test_verify_fails_if_username_was_taken_meanwhile(self):
        self.send_code()
        code = self.get_sent_code()
        self.setup_user(name="newuser")
        response = self.verify(code)

        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.json()["restart"])
        self.assertEqual(User.objects.filter(username="newuser").count(), 1)

    def test_verify_requires_post(self):
        response = self.client.get(reverse("register_verify_code"))
        self.assertEqual(response.status_code, 405)

    def test_failed_delivery_does_not_block_retry(self):
        with override_settings(
            EMAIL_BACKEND="bookmarks.tests.test_registration.FailingEmailBackend"
        ):
            self.client.raise_request_exception = False
            response = self.send_code()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(registration.SESSION_KEY, self.client.session)

        self.assertEqual(self.send_code().status_code, 200)


class FailingEmailBackend:
    def __init__(self, *args, **kwargs):
        pass

    def send_messages(self, messages):
        raise OSError("SMTP unavailable")
