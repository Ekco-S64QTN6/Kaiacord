"""Pictures shared as links rather than uploads.

A Discord CDN link, an imgur `.jpg`, or a GIF Discord has embedded is a picture
the user meant her to see, but vision read uploads only and the link scraper
skipped any `image/*` response, so she was told the "page wouldn't load". These
links go to the vision path instead, where the fetch is bounded and checked the
same way an upload's is, and the scraper leaves them alone.
"""
from __future__ import annotations

import os
import re
from types import SimpleNamespace
from urllib.parse import urlparse

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")
_URL = re.compile(r"https?://[^\s<>]+")
_TRAILING = ".,;:!?)]}'\""
#: Embed kinds Discord fills with a picture: a bare image link, and a GIF
#: (Tenor, Giphy) whose thumbnail is a still of it.
_PICTURE_EMBEDS = ("image", "gifv")


def is_image_link(url: str) -> bool:
    """A URL whose path names an image file (query and fragment ignored)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and parsed.path.lower().endswith(IMAGE_SUFFIXES)


def image_link_urls(text: str) -> list[str]:
    """Image URLs in the order they appear, without duplicates."""
    found = []
    for raw in _URL.findall(text or ""):
        url = raw.rstrip(_TRAILING)
        if is_image_link(url) and url not in found:
            found.append(url)
    return found


def _embed_picture(embed) -> str:
    if getattr(embed, "type", None) not in _PICTURE_EMBEDS:
        return ""
    for part in ("image", "thumbnail"):
        url = getattr(getattr(embed, part, None), "url", None)
        if url:
            return str(url)
    return ""


def _as_attachment(url: str) -> SimpleNamespace:
    name = os.path.basename(urlparse(url).path) or "linked_image"
    if not name.lower().endswith(IMAGE_SUFFIXES):
        name += ".png"
    return SimpleNamespace(filename=name, url=url, linked=True)


def linked_images(msg) -> list:
    """Attachment-shaped records for the pictures a Discord message links.

    Each has the `.filename` and `.url` the vision path reads. Other platforms
    put their pictures in `attachments` themselves, and their message text is a
    prompt, not something a person pasted.
    """
    if str(getattr(msg, "platform", "discord") or "discord") != "discord":
        return []
    urls = image_link_urls(str(getattr(msg, "content", "") or ""))
    for embed in getattr(msg, "embeds", None) or []:
        if str(getattr(embed, "url", "") or "") in urls:
            continue                     # Discord's proxied copy of a link already found
        url = _embed_picture(embed)
        if url and url not in urls:
            urls.append(url)
    uploaded = {str(getattr(a, "url", "")) for a in getattr(msg, "attachments", None) or []}
    return [_as_attachment(u) for u in urls if u not in uploaded]


def vision_sources(msg) -> list:
    """A message's uploads followed by the pictures it links."""
    return list(getattr(msg, "attachments", None) or []) + linked_images(msg)
