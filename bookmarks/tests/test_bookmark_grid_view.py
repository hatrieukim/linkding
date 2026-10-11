from unittest import mock

from django.test import TestCase
from django.urls import reverse

from bookmarks.models import UserProfile
from bookmarks.tests.helpers import BookmarkFactoryMixin, HtmlTestMixin


class BookmarkViewModeTestCase(TestCase, BookmarkFactoryMixin, HtmlTestMixin):
    def setUp(self) -> None:
        self.user = self.get_or_create_test_user()
        self.client.force_login(self.user)

    def set_grid_view(self):
        self.user.profile.bookmark_view_mode = UserProfile.BOOKMARK_VIEW_MODE_GRID
        self.user.profile.save()

    def get_tiles(self, url="bookmarks.index"):
        response = self.client.get(reverse(f"linkding:{url}"))
        soup = self.make_soup(response.content.decode())
        return soup, soup.select("ul.bookmark-list > li")

    # Switching and persisting the view mode

    def test_default_is_list_view(self):
        self.assertEqual(
            self.user.profile.bookmark_view_mode, UserProfile.BOOKMARK_VIEW_MODE_LIST
        )

    def test_switch_to_grid_persists_for_user(self):
        response = self.client.post(
            reverse("linkding:bookmarks.view_mode"), {"view_mode": "grid"}
        )

        self.assertRedirects(response, reverse("linkding:bookmarks.index"))
        self.user.profile.refresh_from_db()
        self.assertEqual(
            self.user.profile.bookmark_view_mode, UserProfile.BOOKMARK_VIEW_MODE_GRID
        )

        # Still grid on later requests, for example after logging in again
        self.client.logout()
        self.client.force_login(self.user)
        self.setup_bookmark(embeddable=True)
        soup, _ = self.get_tiles()
        self.assertIsNotNone(soup.select_one("ul.bookmark-list.grid-view"))

    def test_switch_back_to_list(self):
        self.set_grid_view()

        self.client.post(reverse("linkding:bookmarks.view_mode"), {"view_mode": "list"})

        self.user.profile.refresh_from_db()
        self.assertEqual(
            self.user.profile.bookmark_view_mode, UserProfile.BOOKMARK_VIEW_MODE_LIST
        )

    def test_view_mode_is_stored_per_user(self):
        other_user = self.setup_user()
        self.client.post(reverse("linkding:bookmarks.view_mode"), {"view_mode": "grid"})

        other_user.profile.refresh_from_db()
        self.assertEqual(
            other_user.profile.bookmark_view_mode, UserProfile.BOOKMARK_VIEW_MODE_LIST
        )

    def test_invalid_view_mode_is_rejected(self):
        response = self.client.post(
            reverse("linkding:bookmarks.view_mode"), {"view_mode": "bogus"}
        )

        self.assertEqual(response.status_code, 400)
        self.user.profile.refresh_from_db()
        self.assertEqual(
            self.user.profile.bookmark_view_mode, UserProfile.BOOKMARK_VIEW_MODE_LIST
        )

    def test_get_is_not_allowed(self):
        response = self.client.get(reverse("linkding:bookmarks.view_mode"))

        self.assertEqual(response.status_code, 405)

    def test_requires_login(self):
        self.client.logout()

        response = self.client.post(
            reverse("linkding:bookmarks.view_mode"), {"view_mode": "grid"}
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/login"))
        self.user.profile.refresh_from_db()
        self.assertEqual(
            self.user.profile.bookmark_view_mode, UserProfile.BOOKMARK_VIEW_MODE_LIST
        )

    def test_redirects_to_safe_return_url_only(self):
        response = self.client.post(
            reverse("linkding:bookmarks.view_mode"),
            {"view_mode": "grid", "return_url": "/bookmarks/archived?q=test"},
        )
        self.assertRedirects(
            response, "/bookmarks/archived?q=test", fetch_redirect_response=False
        )

        response = self.client.post(
            reverse("linkding:bookmarks.view_mode"),
            {"view_mode": "grid", "return_url": "https://evil.example.com"},
        )
        self.assertRedirects(
            response, reverse("linkding:bookmarks.index"), fetch_redirect_response=False
        )

    def test_switch_to_grid_schedules_embed_checks(self):
        with mock.patch(
            "bookmarks.views.bookmarks.tasks.schedule_bookmarks_without_embed_check"
        ) as mock_schedule:
            self.client.post(
                reverse("linkding:bookmarks.view_mode"), {"view_mode": "grid"}
            )
            mock_schedule.assert_called_once_with(self.user)

    def test_switch_to_list_does_not_schedule_embed_checks(self):
        with mock.patch(
            "bookmarks.views.bookmarks.tasks.schedule_bookmarks_without_embed_check"
        ) as mock_schedule:
            self.client.post(
                reverse("linkding:bookmarks.view_mode"), {"view_mode": "list"}
            )
            mock_schedule.assert_not_called()

    # Toggle in the page

    def test_toggle_is_rendered(self):
        soup, _ = self.get_tiles()

        form = soup.select_one("form.view-mode-toggle")
        self.assertIsNotNone(form)
        self.assertEqual(form["action"], reverse("linkding:bookmarks.view_mode"))
        values = [b["value"] for b in form.select("button[name=view_mode]")]
        self.assertEqual(values, ["list", "grid"])
        self.assertEqual(form.select_one("button[value=list]")["aria-pressed"], "true")

    def test_toggle_marks_active_mode(self):
        self.set_grid_view()

        soup, _ = self.get_tiles()

        form = soup.select_one("form.view-mode-toggle")
        self.assertEqual(form.select_one("button[value=grid]")["aria-pressed"], "true")
        self.assertEqual(form.select_one("button[value=list]")["aria-pressed"], "false")

    def test_toggle_is_not_rendered_for_anonymous_users_on_shared_view(self):
        self.user.profile.enable_sharing = True
        self.user.profile.enable_public_sharing = True
        self.user.profile.save()
        self.setup_bookmark(shared=True)
        self.client.logout()

        soup, _ = self.get_tiles("bookmarks.shared")

        self.assertIsNone(soup.select_one("form.view-mode-toggle"))

    # Tiles

    def test_list_view_has_no_iframes(self):
        self.setup_bookmark(embeddable=True)

        soup, tiles = self.get_tiles()

        self.assertEqual(len(tiles), 1)
        self.assertIsNone(soup.select_one("ul.bookmark-list.grid-view"))
        self.assertIsNone(soup.select_one("iframe"))

    def test_embeddable_bookmark_renders_sandboxed_lazy_iframe(self):
        self.set_grid_view()
        bookmark = self.setup_bookmark(
            url="https://example.com/page", title="My page", embeddable=True
        )

        _, tiles = self.get_tiles()

        iframe = tiles[0].select_one("iframe")
        self.assertIsNotNone(iframe)
        self.assertEqual(iframe["src"], bookmark.url)
        self.assertEqual(iframe["loading"], "lazy")
        self.assertEqual(iframe["width"], "414")
        self.assertEqual(iframe["height"], "896")
        sandbox = list(iframe["sandbox"])
        self.assertEqual(sandbox, ["allow-scripts"])
        self.assertEqual(iframe["referrerpolicy"], "no-referrer")

    def test_tile_has_title_and_link_to_original_page(self):
        self.set_grid_view()
        bookmark = self.setup_bookmark(
            url="https://example.com/page", title="My page", embeddable=True
        )

        _, tiles = self.get_tiles()

        link = tiles[0].select_one(".title a")
        self.assertEqual(link["href"], bookmark.url)
        self.assertEqual(link.text.strip(), "My page")

    def test_non_embeddable_bookmark_shows_preview_image(self):
        self.set_grid_view()
        self.setup_bookmark(embeddable=False, preview_image_file="preview.png")

        _, tiles = self.get_tiles()

        self.assertIsNone(tiles[0].select_one("iframe"))
        image = tiles[0].select_one(".page-embed img.page-fallback-image")
        self.assertIsNotNone(image)
        self.assertEqual(image["src"], "/static/preview.png")

    def test_non_embeddable_bookmark_without_preview_shows_title_and_favicon(self):
        self.user.profile.enable_favicons = True
        self.user.profile.save()
        self.set_grid_view()
        self.setup_bookmark(
            title="Blocked page", embeddable=False, favicon_file="favicon.png"
        )

        _, tiles = self.get_tiles()

        self.assertIsNone(tiles[0].select_one("iframe"))
        fallback = tiles[0].select_one(".page-embed .page-fallback")
        self.assertIsNotNone(fallback)
        self.assertEqual(
            fallback.select_one("img.favicon")["src"], "/static/favicon.png"
        )
        self.assertEqual(fallback.select_one("span").text.strip(), "Blocked page")

    def test_unchecked_bookmark_uses_fallback_instead_of_iframe(self):
        self.set_grid_view()
        self.setup_bookmark(embeddable=None, preview_image_file="preview.png")
        self.setup_bookmark(embeddable=None)

        _, tiles = self.get_tiles()

        self.assertEqual(len(tiles), 2)
        for tile in tiles:
            self.assertIsNone(tile.select_one("iframe"))
            self.assertIsNotNone(
                tile.select_one(".page-fallback, .page-fallback-image")
            )

    def test_grid_view_is_used_on_archived_and_shared_views(self):
        self.set_grid_view()
        self.user.profile.enable_sharing = True
        self.user.profile.save()
        self.setup_bookmark(is_archived=True, embeddable=True)
        self.setup_bookmark(shared=True, embeddable=True)

        for url in ["bookmarks.archived", "bookmarks.shared"]:
            with self.subTest(url=url):
                soup, tiles = self.get_tiles(url)
                self.assertIsNotNone(soup.select_one("ul.bookmark-list.grid-view"))
                self.assertEqual(len(tiles), 1)
                self.assertIsNotNone(tiles[0].select_one("iframe"))
