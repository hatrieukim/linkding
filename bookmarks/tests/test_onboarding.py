from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from bookmarks.tests.helpers import BookmarkFactoryMixin, HtmlTestMixin


class OnboardingTestCase(TestCase, BookmarkFactoryMixin, HtmlTestMixin):
    def setUp(self) -> None:
        self.user = self.get_or_create_test_user()
        self.client.force_login(self.user)

    def get_onboarding_element(self, url=None):
        response = self.client.get(url or reverse("linkding:bookmarks.index"))
        soup = self.make_soup(response.content.decode())
        return soup.find("ld-onboarding")

    def test_new_profile_is_not_completed_by_default(self):
        self.assertFalse(self.user.profile.onboarding_completed)

    def test_renders_guide_that_opens_automatically_for_new_user(self):
        element = self.get_onboarding_element()

        self.assertIsNotNone(element)
        self.assertEqual(element["data-auto-open"], "true")
        self.assertEqual(
            element["data-complete-url"], reverse("linkding:onboarding.complete")
        )
        self.assertEqual(element["data-new-url"], reverse("linkding:bookmarks.new"))

    def test_renders_guide_on_other_pages(self):
        element = self.get_onboarding_element(reverse("linkding:settings.general"))

        self.assertIsNotNone(element)
        self.assertEqual(element["data-auto-open"], "true")

    def test_does_not_open_automatically_when_completed(self):
        self.user.profile.onboarding_completed = True
        self.user.profile.save()

        element = self.get_onboarding_element()

        # Still rendered so that it can be re-opened from the menu
        self.assertIsNotNone(element)
        self.assertEqual(element["data-auto-open"], "false")

    def test_nav_menu_has_button_to_reopen_guide(self):
        response = self.client.get(reverse("linkding:bookmarks.index"))
        soup = self.make_soup(response.content.decode())

        triggers = soup.select("button[data-onboarding-open]")

        # Once in the desktop menu, once in the mobile menu
        self.assertEqual(len(triggers), 2)
        for trigger in triggers:
            self.assertEqual(trigger.text.strip(), "Guide")

    def test_does_not_render_guide_when_logged_out(self):
        self.client.logout()

        response = self.client.get(reverse("login"))

        self.assertNotContains(response, "ld-onboarding")

    def test_complete_marks_profile_as_completed(self):
        response = self.client.post(reverse("linkding:onboarding.complete"))

        self.assertEqual(response.status_code, 204)
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.onboarding_completed)
        self.assertEqual(self.get_onboarding_element()["data-auto-open"], "false")

    def test_complete_is_idempotent(self):
        self.client.post(reverse("linkding:onboarding.complete"))
        response = self.client.post(reverse("linkding:onboarding.complete"))

        self.assertEqual(response.status_code, 204)
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.onboarding_completed)

    def test_complete_only_affects_current_user(self):
        other_user = self.setup_user()

        self.client.post(reverse("linkding:onboarding.complete"))

        other_user.profile.refresh_from_db()
        self.assertFalse(other_user.profile.onboarding_completed)

    def test_complete_requires_post(self):
        response = self.client.get(reverse("linkding:onboarding.complete"))

        self.assertEqual(response.status_code, 405)
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.onboarding_completed)

    def test_complete_requires_login(self):
        self.client.logout()

        response = self.client.post(reverse("linkding:onboarding.complete"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(settings.LOGIN_URL))
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.onboarding_completed)

    def test_complete_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        response = client.post(reverse("linkding:onboarding.complete"))

        self.assertEqual(response.status_code, 403)
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.onboarding_completed)


class OnboardingMigrationTestCase(TransactionTestCase):
    migrate_from = [("bookmarks", "0054_bookmarkbundle_filter_shared_and_more")]
    migrate_to = [("bookmarks", "0055_userprofile_onboarding_completed")]

    def tearDown(self):
        # Leave the database at the latest migration for other tests
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_existing_profiles_skip_onboarding(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        OldUser = old_apps.get_model("auth", "User")
        OldProfile = old_apps.get_model("bookmarks", "UserProfile")
        user = OldUser.objects.create(username="existing")
        OldProfile.objects.create(user=user)

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        NewProfile = new_apps.get_model("bookmarks", "UserProfile")

        self.assertTrue(NewProfile.objects.get(user_id=user.id).onboarding_completed)
