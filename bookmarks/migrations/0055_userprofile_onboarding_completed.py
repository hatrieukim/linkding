from django.db import migrations, models


def skip_onboarding_for_existing_users(apps, schema_editor):
    # Existing users already know the app, only new profiles get the guide
    UserProfile = apps.get_model("bookmarks", "UserProfile")
    UserProfile.objects.update(onboarding_completed=True)


class Migration(migrations.Migration):
    dependencies = [
        ("bookmarks", "0054_bookmarkbundle_filter_shared_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="onboarding_completed",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(
            skip_onboarding_for_existing_users, migrations.RunPython.noop
        ),
    ]
