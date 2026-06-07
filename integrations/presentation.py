from integrations.models import Platform

PLATFORM_META = {
    Platform.FACEBOOK: {
        "icon": "f",
        "label": "Facebook",
        "class": "platform-facebook",
    },
    Platform.INSTAGRAM: {
        "icon": "IG",
        "label": "Instagram",
        "class": "platform-instagram",
    },
    Platform.PINTEREST: {
        "icon": "P",
        "label": "Pinterest",
        "class": "platform-pinterest",
    },
    Platform.GBP: {
        "icon": "G",
        "label": "Google Business",
        "class": "platform-google",
    },
    Platform.TIKTOK: {
        "icon": "TT",
        "label": "TikTok",
        "class": "platform-tiktok",
    },
    Platform.YOUTUBE: {
        "icon": "YT",
        "label": "YouTube",
        "class": "platform-youtube",
    },
    Platform.LINKEDIN: {
        "icon": "in",
        "label": "LinkedIn",
        "class": "platform-linkedin",
    },
    Platform.TWITTER: {
        "icon": "X",
        "label": "X",
        "class": "platform-x",
    },
}


def platform_meta(platform: str) -> dict:
    return PLATFORM_META.get(
        platform,
        {
            "icon": platform[:2].upper(),
            "label": platform.title(),
            "class": "platform-default",
        },
    )
