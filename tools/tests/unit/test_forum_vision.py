"""Images posted on the forum have to reach the vision model.

2026-09-19. BradZax posted a picture in thread 443378 and Kaia drafted
"those symbols again? what are you trying to do? are you building something?"
— a reply to text that did not exist. The forum path builds a `MockMessage`,
`MockMessage.attachments` was always `[]`, and the vision branch in
`message_processor` keys off nothing else, so the picture was invisible.

The scraper did not extract images at all: `PostInfo` had no field for them.
"""
import copy
import re

import pytest
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from utils.infrastructure.system.messaging import MockAttachment, MockMessage, MockUser, MockChannel
from utils.social.kaia_forum import _FORUM_UI_IMAGES

BASE = "https://www.project1999.com/forums"

POST_HTML = """
<div id="post_message_3801037">
  Look at this thing I found:
  <img src="attachment.php?attachmentid=12345&d=1" />
  <img src="https://i.imgur.com/photo.png" />
  <img src="images/smilies/thumbup.gif" />
  <img src="/images/styles/spacer.gif" />
  <img src="//cdn.example.com/hosted.jpeg" />
  <div><table><tr><td>Quote: Originally Posted by Ekco
    <img src="https://i.imgur.com/QUOTED.png" /></td></tr></table></div>
</div>"""


def _extract(html=POST_HTML):
    """Mirror of the scraper's extraction, against real vBulletin markup."""
    div = BeautifulSoup(html, "html.parser").find("div", id=re.compile(r"^post_message_"))
    own = copy.copy(div)
    for tbl in own.find_all("table"):
        wrapper = tbl.find_parent("div")
        (wrapper if wrapper is not None and wrapper is not own else tbl).decompose()
    out = []
    for img in own.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src or src.startswith("data:"):
            continue
        if any(j in src.lower() for j in _FORUM_UI_IMAGES):
            continue
        src = "https:" + src if src.startswith("//") else urljoin(BASE + "/", src)
        if src not in out:
            out.append(src)
    return out


def test_real_images_are_found():
    urls = _extract()
    assert "https://i.imgur.com/photo.png" in urls
    assert "https://cdn.example.com/hosted.jpeg" in urls
    assert any("attachmentid=12345" in u for u in urls)


def test_forum_chrome_is_not_treated_as_a_picture():
    """vBulletin serves its whole UI as images from the same host. Unfiltered,
    the vision model gets a 1x1 spacer and a thumbs-up emoji."""
    urls = _extract()
    assert not any("smilies" in u for u in urls)
    assert not any("spacer" in u for u in urls)


def test_an_image_inside_a_quote_box_belongs_to_the_person_quoted():
    assert not any("QUOTED" in u for u in _extract())


@pytest.mark.parametrize("src,expected", [
    ("attachment.php?attachmentid=9", "https://www.project1999.com/forums/attachment.php?attachmentid=9"),
    ("//cdn.x/y.jpg", "https://cdn.x/y.jpg"),
    ("https://i.imgur.com/z.png", "https://i.imgur.com/z.png"),
])
def test_relative_sources_resolve_against_the_forum(src, expected):
    got = "https:" + src if src.startswith("//") else urljoin(BASE + "/", src)
    assert got == expected


# ── Delivery ─────────────────────────────────────────────────────────

def test_an_extensionless_attachment_url_still_looks_fetchable():
    """The vision branch tests the filename suffix. vBulletin serves uploads as
    `attachment.php?attachmentid=...`, which has no extension, so without a
    guess every uploaded image is silently skipped."""
    a = MockAttachment("https://www.project1999.com/forums/attachment.php?attachmentid=12345")
    assert any(a.filename.lower().endswith(e)
               for e in (".png", ".jpg", ".jpeg", ".gif", ".webp"))


def test_a_real_extension_is_preserved():
    assert MockAttachment("https://i.imgur.com/x.png").filename == "x.png"
    assert MockAttachment("https://i.imgur.com/y.GIF").filename.lower().endswith(".gif")


def test_mock_message_carries_attachments():
    msg = MockMessage("hi", MockUser(1, "BradZax", "BradZax"), MockChannel(1),
                      platform="vbulletin",
                      attachments=[MockAttachment("https://i.imgur.com/a.png")])
    assert len(msg.attachments) == 1
    assert msg.attachments[0].url.endswith("a.png")


def test_mock_message_still_defaults_to_no_attachments():
    msg = MockMessage("hi", MockUser(1, "x", "x"), MockChannel(1))
    assert msg.attachments == []


def test_the_drafting_path_passes_images_through():
    import inspect
    from utils.social import forum_drafting
    from utils.infrastructure.system.external_mention import process_external_mention

    src = inspect.getsource(forum_drafting.draft_forum_reply)
    assert "image_urls=images" in src, "the forum draft no longer forwards post images"
    assert "image_urls" in inspect.signature(process_external_mention).parameters


def test_visual_grounding_is_worded_for_the_platform():
    """"The user attached an image from their physical environment" is wrong for
    a picture in a public thread, and invites her to treat a stranger's
    screenshot as their living room."""
    import inspect
    from utils.core.message_processor import MessageProcessor

    src = inspect.getsource(MessageProcessor)
    assert "Someone posted an image in this forum thread" in src
    assert "belonging to whoever posted it" in src
