"""Exercise built Chrome ACP with a deterministic ACP agent and real Chromium.

Start test/fixtures/serve-interactive-ui.mjs with SIADA_UI_DIR pointing at a
temporary directory. No model or real user configuration is used.
"""

import argparse
import json
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def exercise_display_settings(page, output_directory, prefix):
    expect(page.locator("textarea")).to_be_enabled(timeout=20000)
    page.wait_for_function("document.documentElement.style.fontSize === '14.4px'")
    textarea = page.locator("textarea")
    baseline = textarea.bounding_box()["height"]
    textarea.fill("这段草稿应在调整显示设置后保留")
    page.get_by_role("button", name="显示设置", exact=True).click()
    scale = page.get_by_role("slider", name="界面缩放")
    lines = page.get_by_role("slider", name="输入框行数")
    scale.focus()
    scale.press("Home")
    page.wait_for_function("document.documentElement.style.fontSize === '12.8px'")
    assert textarea.bounding_box()["height"] < baseline
    lines.focus()
    lines.press("End")
    assert textarea.bounding_box()["height"] > baseline * 3
    expect(textarea).to_have_value("这段草稿应在调整显示设置后保留")
    textarea.fill("\n".join(f"long message {index}" for index in range(60)))
    assert textarea.evaluate("element => element.scrollHeight > element.clientHeight")
    expect(page.get_by_role("slider", name="界面缩放")).to_have_count(0)
    page.get_by_role("button", name="显示设置", exact=True).click()
    page.get_by_role("button", name="恢复默认").click()
    page.wait_for_function("document.documentElement.style.fontSize === '14.4px'")
    assert abs(textarea.bounding_box()["height"] - baseline) < 1
    scale.focus()
    scale.press("Home")
    scale.press("ArrowRight")
    lines.focus()
    lines.press("Home")
    lines.press("ArrowRight")
    page.keyboard.press("Escape")
    textarea.fill("")
    page.wait_for_function("""async () => {
      const values = window.chrome?.storage?.local
        ? (await chrome.storage.local.get('display_settings')).display_settings
        : JSON.parse(localStorage.getItem('display_settings'));
      return values?.scale === 85 && values?.inputLines === 2;
    }""")
    page.reload()
    expect(page.locator("textarea")).to_be_enabled(timeout=20000)
    page.wait_for_function("document.documentElement.style.fontSize === '13.6px'")
    assert abs(page.locator("textarea").bounding_box()["height"] - 54.4) < 1
    page.get_by_role("button", name="显示设置", exact=True).click()
    expect(page.get_by_role("slider", name="界面缩放")).to_have_value("85")
    expect(page.get_by_role("slider", name="输入框行数")).to_have_value("2")
    page.keyboard.press("Escape")
    page.screenshot(path=str(output_directory / f"{prefix}-display.png"), full_page=True)
    print(json.dumps({
        "displaySettings": "PASS", "client": prefix, "scale": 85, "inputLines": 2,
        "inputHeight": page.locator("textarea").bounding_box()["height"],
    }))


def exercise_chat(page, base_url, output_directory, prefix):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.wait_for_load_state("networkidle")
    expect(page.locator("textarea")).to_be_visible(timeout=20000)
    page.locator("textarea").fill("生成交互式经营看板")
    page.locator("textarea").press("Enter")
    section = page.get_by_role("region", name="交互界面：可探索的经营看板")
    expect(section.get_by_role("button", name="Share", exact=True)).to_be_enabled(timeout=20000)
    expect(section.get_by_role("button", name="保存为网页")).to_have_count(0)
    expect(section.get_by_role("button", name="下载 HTML")).to_have_count(0)
    expect(page.get_by_text("生成交互式经营看板", exact=True)).to_be_visible()
    view = section.frame_locator("iframe")
    child = next(frame for frame in page.frames if frame.url.endswith("/frame"))
    page_id = child.url.split("/")[-2]
    child.wait_for_function("document.documentElement.style.zoom === '0.85'")
    state_before = child.evaluate("siadaUI.state")
    page.get_by_role("button", name="显示设置", exact=True).click()
    page.get_by_role("slider", name="界面缩放").focus()
    page.get_by_role("slider", name="界面缩放").press("Home")
    child.wait_for_function("document.documentElement.style.zoom === '0.8'")
    assert child.evaluate("siadaUI.state") == state_before
    page.keyboard.press("Escape")
    expect(view.locator("#visitors")).to_have_text("73.6K")
    view.locator("#range").select_option("7")
    expect(view.locator("#visitors")).to_have_text("15.6K")
    # Send a real key event to the slider, not a script-generated change.
    view.locator("#budget").focus()
    view.locator("#budget").press("ArrowRight")
    expect(view.locator("#budget-label")).to_have_text(" ¥600")
    view.get_by_role("button", name="按当前设置继续分析").click()
    expect(page.get_by_text("已收到界面操作：range=7，budget=600", exact=False)).to_be_visible(timeout=10000)
    section.get_by_role("button", name="Share", exact=True).click()
    expect(section.get_by_role("link", name="打开网页")).to_be_visible()
    url = section.get_by_role("link", name="打开网页").get_attribute("href")
    expect(section.get_by_role("textbox", name="局域网分享链接")).to_have_value(url)
    assert not url.startswith(("http://127.", "http://localhost"))
    assert "token" not in url

    # Spoofed messages from the outer page cannot submit or overwrite frame state.
    page.evaluate(
        """id => window.postMessage({channel:'siada-ui',id,type:'submit',
        prompt:'spoofed action',state:{range:999,budget:999}},'*')""",
        page_id,
    )
    expect(page.get_by_text("spoofed action", exact=True)).to_have_count(0)

    # A failed state write remains visible and can be retried with the current
    # values, rather than claiming a stale snapshot has been saved.
    state_endpoint = f"**/ui/{page_id}/state"
    page.route(state_endpoint, lambda route: route.fulfill(status=500, body="save failed"))
    view.locator("#budget").focus()
    view.locator("#budget").press("ArrowRight")
    expect(section.get_by_text("状态同步失败，请点击 Share 重试")).to_be_visible()
    page.unroute(state_endpoint)
    view.locator("#budget").press("ArrowLeft")
    section.get_by_role("button", name="Share", exact=True).click()
    expect(section.get_by_text("分享网页已生成，同一局域网可访问")).to_be_visible()
    url = section.get_by_role("link", name="打开网页").get_attribute("href")

    # Natural-language agents discover and use these same MCP tools. Verify
    # saving by id keeps the most recently admitted state and listing finds it.
    def call_tool(name, arguments):
        response = page.request.post(
            f"{base_url}/mcp",
            headers={"Authorization": "Bearer interactive-ui-e2e-token"},
            data={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": name, "arguments": arguments}},
        )
        assert response.ok
        result = response.json()["result"]
        assert not result.get("isError"), result
        return result["content"][0]["text"]

    assert page_id in call_tool("browser_save_ui", {"id": page_id})
    assert page_id in call_tool("browser_list_ui", {})
    tool_share = json.loads(call_tool("browser_share_ui", {"id": page_id}))
    assert "/share/" in tool_share["url"]
    assert "token" not in tool_share["url"]

    download_path = output_directory / f"{prefix}-saved.html"
    # Legacy exports remain available to existing saved-page workflows, while
    # the product card has only the Share action.
    download_response = page.request.get(f"{base_url}/ui/{page_id}/download")
    assert download_response.ok
    download_path.write_bytes(download_response.body())
    page.screenshot(path=str(output_directory / f"{prefix}-chat.png"), full_page=True)
    # Source identity remains isolated even if the generated code tries to read
    # host storage; opaque origins cannot read extension or application storage.
    child = next(frame for frame in page.frames if frame.url.endswith("/frame"))
    assert child.evaluate(
        "() => {try {return !!parent.document} catch {return false}}"
    ) is False
    assert not errors, errors
    return url, page_id, download_path


def exercise_shared_page(browser, url, output_directory, prefix):
    context = browser.new_context()
    page = context.new_page()
    page.goto(url)
    expect(page.get_by_role("button", name="下载当前网页")).to_have_count(0)
    view = page.frame_locator("#view")
    expect(view.locator("#visitors")).to_have_text("15.6K")
    expect(view.locator("#budget-label")).to_have_text(" ¥600")
    assert page.request.post(url, data={"state": {"budget": 999}}).status == 404
    origin = url.rsplit("/share/", 1)[0]
    assert page.request.get(f"{origin}/mcp").status == 404
    assert page.request.get(f"{origin}/ui").status == 404
    view.locator("#range").select_option("30")
    expect(page.get_by_role("status")).to_have_text("已保存当前状态")
    page.reload()
    expect(view.locator("#visitors")).to_have_text("73.6K")
    second = browser.new_context()
    other = second.new_page()
    other.goto(url)
    expect(other.frame_locator("#view").locator("#visitors")).to_have_text("15.6K")
    page.screenshot(path=str(output_directory / f"{prefix}-share.png"), full_page=True)
    second.close()
    context.close()
    print(json.dumps({"lanShare": "PASS", "client": prefix, "url": url, "recipientIsolation": "PASS"}))


def exercise_saved_page(context, url, output_directory):
    page = context.new_page()
    page.goto(url)
    view = page.frame_locator("#view")
    expect(view.locator("#visitors")).to_have_text("15.6K")
    expect(view.locator("#budget-label")).to_have_text(" ¥600")
    view.locator("#range").select_option("30")
    expect(view.locator("#visitors")).to_have_text("73.6K")
    page.reload()
    expect(view.locator("#visitors")).to_have_text("73.6K")
    with page.expect_download() as download_info:
        page.get_by_role("button", name="下载当前网页").click()
    path = output_directory / "current-state.html"
    download_info.value.save_as(path)
    page.screenshot(path=str(output_directory / "standalone.png"), full_page=True)
    page.close()
    return path


def exercise_offline(browser, path, expected_visitors, expected_budget):
    # A fresh context has neither cookies nor storage from the original site.
    context = browser.new_context()
    page = context.new_page()
    requests = []
    page.on("request", lambda request: requests.append(request.url))
    page.goto(path.as_uri())
    view = page.frame_locator("#view")
    expect(view.locator("#visitors")).to_have_text(expected_visitors)
    expect(view.locator("#budget-label")).to_have_text(expected_budget)
    view.locator("#range").select_option("7")
    expect(view.locator("#visitors")).to_have_text("15.6K")
    page.reload()
    expect(view.locator("#visitors")).to_have_text("15.6K")
    assert not any(url.startswith(("http:", "https:")) for url in requests), requests
    context.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:9334")
    parser.add_argument("--chromium", required=True)
    parser.add_argument("--extension", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=arguments.chromium)
        context = browser.new_context(viewport={"width": 1100, "height": 900})
        page = context.new_page()
        page.goto(f"{arguments.base_url}/app/?token=interactive-ui-e2e-token")
        exercise_display_settings(page, arguments.output, "web")
        url, page_id, saved = exercise_chat(page, arguments.base_url, arguments.output, "web")
        exercise_shared_page(browser, url, arguments.output, "web")
        current = exercise_saved_page(context, f"{arguments.base_url}/ui/{page_id}", arguments.output)
        exercise_offline(browser, saved, "15.6K", " ¥600")
        exercise_offline(browser, current, "73.6K", " ¥600")
        # Check the independent layout at a narrow mobile width.
        mobile = context.new_page()
        mobile.set_viewport_size({"width": 390, "height": 800})
        mobile.goto(url)
        expect(mobile.frame_locator("#view").locator("#range")).to_be_visible()
        assert mobile.evaluate("document.documentElement.scrollWidth <= innerWidth")
        mobile.screenshot(path=str(arguments.output / "mobile.png"), full_page=True)
        context.close()
        browser.close()
        print(json.dumps({"web": "PASS", "url": url, "id": page_id, "offline": "PASS", "mobile": "PASS"}, ensure_ascii=False))

        if arguments.extension:
            with tempfile.TemporaryDirectory(prefix="siada-ui-extension-") as profile:
                extension = str(arguments.extension.resolve())
                context = playwright.chromium.launch_persistent_context(
                    profile, headless=True, executable_path=arguments.chromium,
                    args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"],
                    viewport={"width": 400, "height": 900},
                )
                worker = context.service_workers[0] if context.service_workers else context.wait_for_event("serviceworker")
                extension_id = worker.url.split("/")[2]
                await_settings = """settings => chrome.storage.local.set({acp_settings:settings})"""
                worker.evaluate(await_settings, {
                    "proxyUrl": arguments.base_url.replace("http", "ws", 1) + "/ws",
                    "token": "interactive-ui-e2e-token",
                })
                # Only bootstrap discovery is simulated; ACP, MCP, saving and
                # the sandboxed HTML all use the real built proxy and extension.
                context.route("**/local-bootstrap", lambda route: route.fulfill(
                    status=200, content_type="application/json", body=json.dumps({
                        "schemaVersion": 1,
                        "proxyUrl": arguments.base_url.replace("http", "ws", 1) + "/ws",
                        "token": "interactive-ui-e2e-token",
                    }),
                ))
                panel = context.new_page()
                panel.goto(f"chrome-extension://{extension_id}/dist/sidepanel.html")
                exercise_display_settings(panel, arguments.output, "extension")
                extension_url, _, _ = exercise_chat(panel, arguments.base_url, arguments.output, "extension")
                recipient_browser = playwright.chromium.launch(headless=True, executable_path=arguments.chromium)
                exercise_shared_page(recipient_browser, extension_url, arguments.output, "extension")
                recipient_browser.close()
                assert panel.evaluate("document.documentElement.scrollWidth <= innerWidth")
                print(json.dumps({"extension": "PASS", "url": extension_url}, ensure_ascii=False))
                context.close()


if __name__ == "__main__":
    main()