"""Real-Chromium interaction and responsive-layout checks for KAIA//RX."""

import pytest
from playwright.sync_api import sync_playwright

from utils.radio import rx_dashboard as RX


@pytest.fixture
def rx_dashboard_url(monkeypatch):
    """Serve the real local RX page without starting an SDR or radio watcher."""
    monkeypatch.setattr(
        RX, "_cfg",
        lambda key, default=None: 0 if key == "dashboard_port" else default,
    )
    old, RX._server = RX._server, None
    if old is not None:
        old.shutdown()
        old.server_close()

    base = RX.serve()
    assert base.startswith("http://127.0.0.1:"), "RX dashboard server did not start"
    yield base

    server, RX._server = RX._server, None
    if server is not None:
        server.shutdown()
        server.server_close()


def _layout(page):
    return page.evaluate("""() => {
      const rect = (selector) => {
        const r = document.querySelector(selector).getBoundingClientRect();
        return {x:r.x, y:r.y, right:r.right, width:r.width, height:r.height};
      };
      const canvas = document.querySelector("#spec");
      const before = canvas.getBoundingClientRect();
      window.fit(canvas);
      return {
        viewport: innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        app: rect("#app"),
        vfo: rect("#vfo"),
        dial: rect("#dial"),
        kaia: rect("#kaia"),
        side: rect("#side"),
        touchAction: getComputedStyle(canvas).touchAction,
        canvasScale: canvas.width / Math.max(1, before.width)
      };
    }""")


def test_rx_dashboard_reflows_on_mobile_and_tablet_and_supports_touch_dial(rx_dashboard_url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 390, "height": 844},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
        )
        try:
            response = page.goto(rx_dashboard_url, wait_until="domcontentloaded", timeout=20000)
            assert response is not None and response.ok
            page.wait_for_function("typeof window.fit === 'function'", timeout=10000)

            mobile = _layout(page)
            assert mobile["scrollWidth"] <= mobile["viewport"] + 1
            assert mobile["vfo"]["width"] <= mobile["viewport"]
            assert mobile["dial"]["width"] <= mobile["viewport"]
            assert mobile["side"]["y"] > mobile["kaia"]["y"]
            assert mobile["touchAction"] == "none"
            assert mobile["canvasScale"] <= 2.05

            # Compact phones still keep the frequency readout inside its VFO cell.
            page.set_viewport_size({"width": 320, "height": 740})
            compact = _layout(page)
            freq_bounds = page.evaluate("""() => {
              const f = document.querySelector("#freq").getBoundingClientRect();
              const cell = document.querySelector("#vfo").firstElementChild.getBoundingClientRect();
              return {freqRight:f.right, cellRight:cell.right};
            }""")
            assert compact["scrollWidth"] <= compact["viewport"] + 1
            assert freq_bounds["freqRight"] <= freq_bounds["cellRight"] + 1

            page.set_viewport_size({"width": 390, "height": 844})
            # A touch drag pans the dial; it must not depend on mouse events.
            page.evaluate("""() => {
              const canvas = document.querySelector("#spec");
              const r = canvas.getBoundingClientRect();
              const x = r.left + Math.min(60, r.width * .2);
              const y = r.top + Math.min(30, r.height * .3);
              canvas.dispatchEvent(new PointerEvent("pointerdown", {
                bubbles:true, cancelable:true, pointerId:71, pointerType:"touch",
                isPrimary:true, button:0, clientX:x, clientY:y
              }));
              canvas.dispatchEvent(new PointerEvent("pointermove", {
                bubbles:true, cancelable:true, pointerId:71, pointerType:"touch",
                isPrimary:true, button:0, clientX:x + 75, clientY:y
              }));
              canvas.dispatchEvent(new PointerEvent("pointerup", {
                bubbles:true, cancelable:true, pointerId:71, pointerType:"touch",
                isPrimary:true, button:0, clientX:x + 75, clientY:y
              }));
            }""")
            assert "lit" not in page.locator("#follow").get_attribute("class").split()

            # Ctrl-wheel is left to the browser for page zoom; plain wheel stays
            # reserved for frequency-axis zoom.
            ctrl_wheel_defaulted = page.evaluate("""() => {
              const event = new WheelEvent("wheel", {
                bubbles:true, cancelable:true, ctrlKey:true, deltaY:80
              });
              document.querySelector("#spec").dispatchEvent(event);
              return event.defaultPrevented;
            }""")
            assert not ctrl_wheel_defaulted

            page.set_viewport_size({"width": 820, "height": 1180})
            tablet = _layout(page)
            assert tablet["scrollWidth"] <= tablet["viewport"] + 1
            assert tablet["side"]["x"] > tablet["kaia"]["x"]
            assert abs(tablet["side"]["y"] - tablet["kaia"]["y"]) < 2
        finally:
            page.close()
            browser.close()
