#!/usr/bin/env python3
"""Drive a headless Chromium-family browser over --remote-debugging-pipe.

Standard library only. The browser never loads anything from disk or the network:
every request is answered here from an allow-list (see Renderer.render), anything
else is refused. Protocol: JSON messages terminated by a NUL byte; the browser
reads commands on file descriptor 3 and writes replies and events on 4.
"""
from contextlib import ExitStack
import base64
import math
import signal
import time
import json
import os
import select
import shutil
import subprocess
import tempfile

ORIGIN = "https://compose.listing-kit.invalid"

CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "microsoft-edge", "brave-browser",
]

MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8", ".json": "application/json",
        ".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml", ".ttf": "font/ttf", ".otf": "font/otf"}


class BrowserError(Exception):
    pass


def find_browser():
    env = os.environ.get("LK_BROWSER")
    for cand in ([env] if env else CANDIDATES):
        path = cand if os.path.isabs(cand) else shutil.which(cand)
        if path and os.access(path, os.X_OK):
            return path
    return None


def timeout_seconds():
    try:
        timeout = float(os.environ.get("LK_BROWSER_TIMEOUT", "60"))
        if math.isfinite(timeout) and 0 < timeout <= 86400:
            return timeout
    except ValueError:
        pass
    raise BrowserError("LK_BROWSER_TIMEOUT must be a positive number of seconds (up to 86400)")


def new_deadline():
    return time.monotonic() + timeout_seconds()


def time_left(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise BrowserError("browser render timed out")
    return remaining


class Browser:
    def __init__(self, path=None, extra_args=None):
        self.path = path or find_browser()
        if not self.path:
            raise BrowserError("Framed screenshots need Chrome, Chromium, Edge or Brave. Found none.")
        self.timeout = timeout_seconds()
        self.start_deadline()
        with ExitStack() as resources, ExitStack() as child_ends:
            self.profile = tempfile.mkdtemp(prefix="lk-browser-")
            resources.callback(shutil.rmtree, self.profile, ignore_errors=True)
            to_browser_r, self._w = os.pipe()
            resources.callback(os.close, self._w)
            child_ends.callback(os.close, to_browser_r)
            self._r, from_browser_w = os.pipe()
            resources.callback(os.close, self._r)
            child_ends.callback(os.close, from_browser_w)
            os.set_blocking(self._w, False)
            self._spawn(to_browser_r, from_browser_w, extra_args)
            resources.callback(self._stop)
            self._resources = resources.pop_all()
        self._buf = b""
        self._id = 0

    def _spawn(self, to_browser_r, from_browser_w, extra_args):
        def wire():  # the browser expects exactly fds 3 (in) and 4 (out)
            a, b = os.dup(to_browser_r), os.dup(from_browser_w)
            os.dup2(a, 3); os.dup2(b, 4)
            for fd in (a, b):
                if fd not in (3, 4):
                    os.close(fd)

        args = [self.path, "--headless=new", "--remote-debugging-pipe",
                "--user-data-dir=" + self.profile, "--no-first-run", "--no-default-browser-check",
                "--disable-extensions", "--disable-background-networking", "--disable-sync",
                "--disable-component-update", "--hide-scrollbars",
                # No keychain or password store: with an unusual HOME (CI, sandboxes) the real
                # ones can block the browser's start forever.
                "--use-mock-keychain", "--password-store=basic", "--disable-features=DialMediaRouteProvider", "--force-color-profile=srgb",
                "--font-render-hinting=none",
                # Second barrier: nothing reaches a network, loopback included.
                "--proxy-server=socks5://127.0.0.1:1", "--proxy-bypass-list=<-loopback>",
                "about:blank"]
        args[1:1] = (extra_args or []) + os.environ.get("LK_BROWSER_ARGS", "").split()
        self.proc = subprocess.Popen(args, preexec_fn=wire, pass_fds=(3, 4), close_fds=True, start_new_session=True,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
    def start_deadline(self):
        self.deadline = time.monotonic() + self.timeout

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise BrowserError("browser render timed out after %g seconds" % self.timeout)
        return remaining

    def version_major(self):
        product = self.call("Browser.getVersion").get("product", "")
        return product.partition("/")[2].partition(".")[0] or "unknown"

    def _stop(self):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(self.proc.pid, sig)
            except (ProcessLookupError, PermissionError):
                # macOS can report EPERM while the last group member is exiting.
                pass
            try:
                self.proc.wait(timeout=2)
                return
            except subprocess.TimeoutExpired:
                if sig == signal.SIGKILL:
                    raise

    def close(self):
        self._resources.close()

    def _read(self):
        self.remaining()
        while b"\0" not in self._buf:
            # A browser that never answers must not hang the caller forever.
            ready, _, _ = select.select([self._r], [], [], self.remaining())
            if not ready:
                raise BrowserError("the browser did not answer within %g seconds (%s)" % (self.timeout, self.path))
            chunk = os.read(self._r, 1 << 20)
            if not chunk:
                raise BrowserError("the browser closed the connection (exit %s)" % self.proc.poll())
            self._buf += chunk
        raw, self._buf = self._buf.split(b"\0", 1)
        try:
            message = json.loads(raw)
        except ValueError as exc:
            raise BrowserError("invalid JSON on the browser control pipe") from exc
        if not isinstance(message, dict):
            raise BrowserError("expected an object on the browser control pipe")
        return message

    def send(self, method, params=None, session=None):
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        data = memoryview(json.dumps(msg).encode() + b"\0")
        while data:
            _, ready, _ = select.select([], [self._w], [], self.remaining())
            if ready:
                try:
                    data = data[os.write(self._w, data):]
                except BlockingIOError:
                    continue
        return self._id

    def call(self, method, params=None, session=None, on_event=None):
        """Send a command and return its result, handing events to on_event meanwhile."""
        want = self.send(method, params, session)
        while True:
            msg = self._read()
            if msg.get("id") == want:
                if "error" in msg:
                    raise BrowserError("%s: %s" % (method, msg["error"].get("message")))
                return msg.get("result", {})
            if on_event:
                on_event(msg)

    def pump(self, on_event, until):
        while not until():
            msg = self._read()
            on_event(msg)


class Renderer:
    """Render pages whose every request is served from `assets` (url path -> file path or bytes)."""

    def __init__(self, browser):
        self.b = browser
        self.refused = []

    def render(self, assets, width, height, page="/index.html", probe=None, csp=True, background=False, deadline=None):
        """csp=False drops the Content-Security-Policy header so tests can prove the request
        interception refuses everything off the allow-list by itself."""
        b = self.b
        self.refused = []
        if deadline is None:
            b.start_deadline()
        else:
            b.deadline = deadline
        target = b.call("Target.createTarget", {"url": "about:blank"})["targetId"]
        try:
            return self._page(target, assets, width, height, page, probe, csp, background)
        finally:
            # A timed-out connection is cleaned up by Browser.close().
            if time.monotonic() < b.deadline:
                b.call("Target.closeTarget", {"targetId": target})

    def _page(self, target, assets, width, height, page, probe, csp, background):
        b = self.b
        session = b.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        state = {"loaded": False}

        auto = {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True}
        intercept = {"patterns": [{"urlPattern": "*"}]}
        pending = {}

        def serve(msg):
            m, p, sid = msg.get("method"), msg.get("params", {}), msg.get("sessionId")
            command = pending.pop((sid, msg.get("id")), None)
            if command:
                method, child_target = command
                if "error" in msg:
                    b.send("Target.closeTarget", {"targetId": child_target})
                    raise BrowserError("%s: %s" % (method, msg["error"]["message"]))
                if method == "Fetch.enable":
                    ident = b.send("Target.setAutoAttach", auto, sid)
                    pending[sid, ident] = ("Target.setAutoAttach", child_target)
                else:
                    b.send("Runtime.runIfWaitingForDebugger", {}, sid)
            elif m == "Target.attachedToTarget":
                child = p["sessionId"]
                ident = b.send("Fetch.enable", intercept, child)
                pending[child, ident] = ("Fetch.enable", p["targetInfo"]["targetId"])
            elif m == "Fetch.requestPaused":
                url = p["request"]["url"]
                body = None
                if url.startswith(ORIGIN + "/"):
                    path = "/" + url[len(ORIGIN) + 1:].split("?", 1)[0].split("#", 1)[0]
                    src = assets.get(path)
                    if isinstance(src, (bytes, bytearray)):
                        body = bytes(src)
                    elif src:
                        with open(src, "rb") as f:
                            body = f.read()
                if body is None:
                    self.refused.append(url)
                    b.send("Fetch.failRequest", {"requestId": p["requestId"], "errorReason": "AccessDenied"}, sid)
                else:
                    ext = os.path.splitext(url.split("?", 1)[0])[1].lower()
                    b.send("Fetch.fulfillRequest", {
                        "requestId": p["requestId"], "responseCode": 200,
                        "responseHeaders": [
                            {"name": "Content-Type", "value": MIME.get(ext, "application/octet-stream")}
                        ] + ([{"name": "Content-Security-Policy",
                               "value": "default-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self'; font-src 'self'; script-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; connect-src 'none'; base-uri 'none' "}]
                             if csp else []),
                        "body": base64.b64encode(body).decode()}, sid)
            elif m == "Page.loadEventFired" and sid == session:
                state["loaded"] = True

        b.call("Fetch.enable", intercept, session, serve)
        b.call("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True},
               session, serve)
        b.call("Page.enable", {}, session, serve)
        b.call("Emulation.setDeviceMetricsOverride",
               {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False}, session, serve)
        b.call("Page.navigate", {"url": ORIGIN + page}, session, serve)
        b.pump(serve, lambda: state["loaded"])
        def evaluate(expression):
            response = b.call("Runtime.evaluate", {"expression": expression, "awaitPromise": True,
                                                    "returnByValue": True}, session, serve)
            if "exceptionDetails" in response:
                exc = response["exceptionDetails"]
                reason = exc.get("exception", {}).get("description", exc.get("text"))
                raise BrowserError("template asset or probe failed: %s" % reason)
            return response["result"].get("value")

        names = {url: src for url, src in assets.items() if isinstance(src, str)}
        ready = r"""(async()=>{
            const names = %s;
            const asset = url => names[new URL(url, location.href).pathname] || url;
            await Promise.all(Array.from(document.images, async img => {
                try { await img.decode(); if (img.naturalWidth && img.naturalHeight) return; } catch {}
                throw Error('image failed to decode: ' + asset(img.getAttribute('src')));
            }));
            await Promise.all(Array.from(document.fonts, async face => {
                try { await face.load(); } catch {
                    for (const sheet of document.styleSheets) for (const rule of sheet.cssRules) {
                        if (!(rule instanceof CSSFontFaceRule) || rule.style.fontFamily !== face.family) continue;
                        const match = rule.style.getPropertyValue('src').match(/url\(["']?([^)"']+)/);
                        if (match) throw Error('font failed to decode: ' + asset(match[1]));
                    }
                    throw Error('font failed to decode: ' + face.family);
                }
            }));
            await document.fonts.ready;
            return (%s);
        })()"""
        info = evaluate(ready % (json.dumps(names), probe or "null"))

        def capture():
            shot = b.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False,
                          "clip": {"x": 0, "y": 0, "width": width, "height": height, "scale": 1}}, session, serve)
            return base64.b64decode(shot["data"])

        png = capture()
        if background:
            evaluate("""document.querySelectorAll('[data-check=text]').forEach(el => {
                el.style.setProperty('-webkit-text-fill-color','transparent','important');
                el.style.setProperty('text-shadow','none','important');
            })""")
            info["background"] = capture()
        return png, info
