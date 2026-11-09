"""Pictures shared as links reach vision, and the scraper leaves them alone."""

import asyncio
from types import SimpleNamespace

from utils.core import image_links
from utils.core.image_links import image_link_urls, is_image_link, linked_images, vision_sources

CDN = ("https://cdn.discordapp.com/attachments/1/2/image0.jpg"
       "?ex=6aeb6bbd&is=6aea1a3d&hm=b1e6a9a3ed2fd84b&")


def test_image_links_are_found_by_their_path_not_their_query():
    text = f"kaia look {CDN} and https://i.imgur.com/abc.PNG. also https://example.com/page?x=.jpg"
    assert image_link_urls(text) == [CDN, "https://i.imgur.com/abc.PNG"]
    assert not is_image_link("https://example.com/photos/")
    assert not is_image_link("ftp://example.com/a.png")


def test_a_discord_message_linking_a_picture_yields_an_attachment_vision_can_read():
    msg = SimpleNamespace(content=f"what is this {CDN}", attachments=[], embeds=[])
    [att] = linked_images(msg)
    assert att.url == CDN and att.filename == "image0.jpg" and att.linked


def test_a_gif_embed_is_seen_through_its_still_and_a_proxied_copy_is_not_doubled():
    gif = SimpleNamespace(type="gifv", url="https://tenor.com/view/cat-gif-123",
                          image=None, thumbnail=SimpleNamespace(url="https://media.tenor.com/x/cat.png"))
    proxied = SimpleNamespace(type="image", url="https://i.imgur.com/abc.png", image=None,
                              thumbnail=SimpleNamespace(url="https://media.discordapp.net/external/q/abc.png"))
    msg = SimpleNamespace(content="https://tenor.com/view/cat-gif-123 https://i.imgur.com/abc.png",
                          attachments=[], embeds=[gif, proxied])
    assert [a.url for a in linked_images(msg)] == [
        "https://i.imgur.com/abc.png", "https://media.tenor.com/x/cat.png"]


def test_uploads_come_first_and_are_not_repeated_as_links():
    upload = SimpleNamespace(filename="photo.jpg", url=CDN)
    msg = SimpleNamespace(content=CDN, attachments=[upload], embeds=[])
    assert vision_sources(msg) == [upload]


def test_only_discord_messages_have_their_links_read():
    """The quip, the overnight log and the forum put prompt text in `content`; the
    forum supplies its pictures as attachments already."""
    msg = SimpleNamespace(content=CDN, attachments=[], embeds=[], platform="overnight")
    assert linked_images(msg) == []


def test_the_link_scraper_does_not_report_a_picture_as_a_page_that_would_not_load(monkeypatch):
    from utils.core.context_enricher import ContextEnricher
    import re

    enricher = ContextEnricher.__new__(ContextEnricher)
    enricher.external_link_pattern = re.compile(r"(?<!<)https?://[^\s>]+")
    scraped = []

    async def scrape(url):
        scraped.append(url)
        return f"Source: {url}\npage text"

    monkeypatch.setattr(enricher, "_scrape_single_url", scrape)
    only_picture = asyncio.run(enricher.resolve_external_urls(SimpleNamespace(content=f"look {CDN}")))
    assert only_picture == "" and scraped == []

    both = asyncio.run(enricher.resolve_external_urls(
        SimpleNamespace(content=f"{CDN} and https://example.com/article")))
    assert scraped == ["https://example.com/article"] and "could not be scraped" not in both


def test_the_vision_path_selects_linked_pictures():
    from utils.core.message_processor import MessageProcessor

    processor = MessageProcessor.__new__(MessageProcessor)
    msg = SimpleNamespace(content=f"{CDN} https://tenor.com/view/x", attachments=[], embeds=[])
    selected, skipped = processor._select_vision_image_attachments(vision_sources(msg))
    assert [a.url for a in selected] == [CDN] and skipped == 0
    assert image_links.IMAGE_SUFFIXES == (".png", ".jpg", ".jpeg", ".gif", ".webp")
