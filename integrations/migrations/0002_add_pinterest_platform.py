from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="socialaccount",
            name="platform",
            field=models.CharField(
                choices=[
                    ("GBP", "Google Business Profile"),
                    ("FACEBOOK", "Facebook"),
                    ("TIKTOK", "TikTok"),
                    ("INSTAGRAM", "Instagram"),
                    ("PINTEREST", "Pinterest"),
                    ("YOUTUBE", "YouTube"),
                    ("LINKEDIN", "LinkedIn"),
                    ("TWITTER", "X / Twitter"),
                ],
                max_length=16,
            ),
        ),
    ]
