import json
import time
from flask import Flask, request
from gevent import monkey
from playwright.sync_api import sync_playwright

monkey.patch_all()

app = Flask(__name__)
global_a1 = ""
global_cookies = {}


def get_context_page(instance):
    browser = instance.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    return context, page


print("启动 Playwright 签名服务...")
playwright = sync_playwright().start()
browser_context, context_page = get_context_page(playwright)


def _update_a1():
    global global_a1, global_cookies
    cookies = browser_context.cookies()
    global_cookies = {c["name"]: c["value"] for c in cookies}
    for cookie in cookies:
        if cookie["name"] == "a1":
            global_a1 = cookie["value"]


print("跳转小红书首页...")
context_page.goto("https://www.xiaohongshu.com")
time.sleep(5)
context_page.reload()
time.sleep(1)
_update_a1()
print(f"a1 = {global_a1}")
print("签名服务就绪（未登录状态）")


def do_sign(uri, data, a1, web_session):
    global global_a1
    if a1 and a1 != global_a1:
        browser_context.add_cookies([{
            "name": "a1", "value": a1,
            "domain": ".xiaohongshu.com", "path": "/"
        }])
        context_page.reload()
        time.sleep(1)
        _update_a1()

    encrypt_params = context_page.evaluate(
        "([url, data]) => window._webmsxyw(url, data)",
        [uri, data]
    )
    return {
        "x-s": encrypt_params["X-s"],
        "x-t": str(encrypt_params["X-t"]),
    }


@app.route("/sign", methods=["POST"])
def sign():
    body = request.json
    return do_sign(body["uri"], body["data"], body.get("a1", ""), body.get("web_session", ""))


@app.route("/a1", methods=["GET"])
def get_a1():
    return {"a1": global_a1}


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "a1": global_a1, "logged_in": bool(global_cookies.get("web_session"))}


@app.route("/login", methods=["POST"])
def login():
    """传入 cookie 字符串，注入到签名服务的浏览器中。"""
    cookie_str = request.json.get("cookie", "")
    if not cookie_str:
        return {"error": "no cookie provided"}, 400

    cookies = []
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            name, value = item.split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".xiaohongshu.com",
                "path": "/",
            })
    browser_context.add_cookies(cookies)
    context_page.reload()
    time.sleep(2)
    _update_a1()
    return {"status": "ok", "a1": global_a1, "cookies_count": len(global_cookies)}


@app.route("/cookies", methods=["GET"])
def get_cookies():
    _update_a1()
    return global_cookies


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005)
