"""Real browser coverage for source revisions, 3D controls and Share state."""
import argparse
import json
import tempfile
from pathlib import Path
from playwright.sync_api import expect, sync_playwright


def exercise(page, browser, base_url, output, label):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    expect(page.locator("textarea")).to_be_enabled(timeout=20000)
    page.locator("textarea").fill("integration-3d")
    page.locator("textarea").press("Enter")
    expect(page.get_by_text("3D integration ready", exact=True)).to_be_visible(timeout=30000)
    section = page.get_by_role("region", name="交互界面：3D source integration")
    expect(section).to_have_count(1)
    expect(section.locator("iframe")).to_have_count(1)
    view = section.frame_locator("iframe")
    expect(view.get_by_role("heading", name="V8 发动机 · 更新后")).to_be_visible(timeout=30000)
    child = next(frame for frame in page.frames if "/ui/" in frame.url and "/frame" in frame.url)
    child.wait_for_function("() => window.uiInspection?.ready === true")
    assert "?revision=" in child.url
    section.scroll_into_view_if_needed()
    page.evaluate("""() => {
        const frame=document.querySelector('section[aria-label="交互界面：3D source integration"] iframe');
        const id=new URL(frame.src).pathname.split('/')[2];
        frame.contentWindow.postMessage({channel:'siada-ui',id,type:'visibility',visible:false},'*');
    }""")
    suspended = child.evaluate("""async () => {
        const angle=uiInspection.getState().angle;
        await new Promise(resolve=>setTimeout(resolve,200));
        return angle===uiInspection.getState().angle && !uiInspection.getState().paused;
    }""")
    assert suspended
    before_resume = child.evaluate("() => uiInspection.getState().angle")
    page.evaluate("""() => {
        const frame=document.querySelector('section[aria-label="交互界面：3D source integration"] iframe');
        const id=new URL(frame.src).pathname.split('/')[2];
        frame.contentWindow.postMessage({channel:'siada-ui',id,type:'visibility',visible:true},'*');
    }""")
    child.wait_for_function("angle => uiInspection.getState().angle !== angle", arg=before_resume)
    view.get_by_label("曲轴角度", exact=True).press("Home")
    child.wait_for_function("() => uiInspection.getState().angle === 0 && uiInspection.getState().paused")
    first = child.evaluate("() => uiInspection.metrics().pistonMm")
    for _ in range(180):
        view.get_by_label("曲轴角度", exact=True).press("ArrowRight")
    second = child.evaluate("() => uiInspection.metrics().pistonMm")
    assert abs(first - second - 89) < 1e-6, (first, second)
    view.get_by_label("视角", exact=True).select_option("side")
    view.get_by_label("剖切", exact=True).select_option("section")
    view.get_by_label("气缸", exact=True).select_option("6")
    view.get_by_label("隔离当前气缸", exact=True).check()
    view.get_by_label("拆解程度", exact=True).press("End")
    for _ in range(5):
        view.get_by_label("拆解程度", exact=True).press("ArrowLeft")
    canvas = view.locator("canvas")
    canvas.scroll_into_view_if_needed()
    box = canvas.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 30, y + 20, steps=4)
    page.mouse.up()
    expected = child.evaluate("() => uiInspection.getState()")
    assert expected["angle"] == 180 and expected["cylinder"] == 6
    assert expected["explode"] == 0.75 and expected["cut"] == "section"
    assert expected["camera"]["az"] != 1.57
    child.evaluate("() => uiInspection.render()")
    assert child.evaluate("() => uiInspection.metrics().rootY") > 0
    view.get_by_role("button", name="请助手解释当前气缸", exact=True).click()
    expect(page.get_by_text("cylinder=6，angle=180", exact=False)).to_be_visible(timeout=10000)
    section.get_by_role("button", name="Share", exact=True).click()
    expect(section.get_by_role("link", name="打开网页")).to_be_visible(timeout=10000)
    url = section.get_by_role("link", name="打开网页").get_attribute("href")
    assert "/share/" in url and "token" not in url
    snapshot = child.evaluate("() => uiInspection.getState()")
    context = browser.new_context(viewport={"width": 400, "height": 1000})
    recipient = context.new_page()
    recipient.goto(url)
    frame = recipient.frames[1]
    frame.wait_for_function("() => uiInspection?.ready === true")
    actual = frame.evaluate("() => uiInspection.getState()")
    assert actual == snapshot, (actual, snapshot)
    frame.get_by_label("气缸", exact=True).select_option("2")
    recipient.reload()
    recipient.frames[1].wait_for_function("() => uiInspection?.ready === true")
    assert recipient.frames[1].evaluate("() => uiInspection.getState().cylinder") == 2
    fresh = browser.new_context()
    fresh_page = fresh.new_page()
    fresh_page.goto(url)
    fresh_page.frames[1].wait_for_function("() => uiInspection?.ready === true")
    assert fresh_page.frames[1].evaluate("() => uiInspection.getState()") == snapshot
    recipient.screenshot(path=str(output / f"{label}-shared.png"), full_page=True)
    page.screenshot(path=str(output / f"{label}-chat.png"), full_page=True)
    fresh.close()
    context.close()
    assert not errors, errors
    print(json.dumps({"client": label, "revisions": "PASS", "pistonStrokeMm": first - second,
                      "controls": "PASS", "action": "PASS", "shareState": "PASS",
                      "recipientReload": "PASS", "recipientIsolation": "PASS", "url": url}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--chromium", required=True)
    parser.add_argument("--extension", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=args.chromium)
        context = browser.new_context(viewport={"width": 400, "height": 1000})
        context.route("**/local-bootstrap", lambda route: route.fulfill(status=200, content_type="application/json",
            body=json.dumps({"schemaVersion": 1, "proxyUrl": args.base_url.replace("http", "ws", 1) + "/ws",
                             "token": "interactive-ui-e2e-token"})))
        page = context.new_page()
        page.goto(f"{args.base_url}/app/?token=interactive-ui-e2e-token")
        exercise(page, browser, args.base_url, args.output, "web")
        context.close()
        if args.extension:
            with tempfile.TemporaryDirectory(prefix="teardown-extension-test-") as profile:
                extension = str(args.extension.resolve())
                extension_context = playwright.chromium.launch_persistent_context(profile, headless=True,
                    executable_path=args.chromium, args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"],
                    viewport={"width": 400, "height": 1000})
                worker = extension_context.service_workers[0] if extension_context.service_workers else extension_context.wait_for_event("serviceworker")
                extension_id = worker.url.split("/")[2]
                bootstrap = {"schemaVersion": 1, "proxyUrl": args.base_url.replace("http", "ws", 1) + "/ws", "token": "interactive-ui-e2e-token"}
                worker.evaluate("settings => chrome.storage.local.set({acp_settings:settings})", bootstrap)
                extension_context.route("**/local-bootstrap", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(bootstrap)))
                panel = extension_context.new_page()
                panel.goto(f"chrome-extension://{extension_id}/dist/sidepanel.html")
                exercise(panel, browser, args.base_url, args.output, "extension")
                extension_context.close()
        browser.close()


if __name__ == "__main__":
    main()