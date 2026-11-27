#!/usr/bin/env python3
"""Turn raw captures into the store images the plan describes.

Reads .listing-kit/listing.json through plan.manifest() and, for every output:
  raw mode      normalizes one PNG capture to 8-bit RGB (it must already be the target size);
  framed/band   renders the selected template around the capture;
  panel         renders a brand panel with no capture;
  graphics      renders the feature graphic and headers; derives the Play icon.

Only what changed is written. .listing-kit/compose.lock.json records what each
output was made from, and .listing-kit/outputs.json records which files the kit
owns. A change that would restyle images whose own content did not change needs
--restyle. Files the plan no longer produces are moved to .listing-kit/held/.

Usage: compose.py <app-root> [--target ID]... [--screen ID]... [--restyle] [--adopt] [--dry-run | --preview]
Exit:  0 done; 1 a problem with an input or an image (details printed);
       2 usage or an invalid plan; 3 all outputs are blocked by a missing browser, or ImageMagick is required;
       4 would restyle existing images (rerun with --restyle).
"""
from contextlib import ExitStack
import argparse
import base64
import html
import io
from pathlib import Path
import re
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.normpath(os.path.join(HERE, "..", "lib"))
sys.path.insert(0, LIB)
sys.path.insert(0, HERE)
import imginfo  # noqa: E402
import plan  # noqa: E402
import specs  # noqa: E402
import render  # noqa: E402
import ownership
import template_values
import user_templates
from regular_files import directory, open_regular, read_regular
import fontcheck  # noqa: E402

def listing_name(root, man, rec):
    """The app's display name for brand text, read from the listing itself (Apple name.txt,
    Play title.txt) for this output's locale, then any locale. Never the bundle id: with
    no name on file the brand line is left out."""
    root = Path(root).resolve()
    trees = man.get("trees", {})
    order = [rec.get("store")] + [s for s in ("apple", "play") if s != rec.get("store")]
    for store in order:
        meta = (trees.get(store) or {}).get("metadata")
        if not meta:
            continue
        stem = "name.txt" if store == "apple" else "title.txt"
        codes = [rec.get("storeCode")] if store == rec.get("store") else []
        try:
            metadata = (root / meta).resolve(strict=True).relative_to(root)
            with directory(root, metadata) as parent:
                codes.extend(sorted(os.listdir(parent)))
        except (OSError, RuntimeError, ValueError):
            continue
        for code in dict.fromkeys(codes):
            if not specs.component(code):
                continue
            try:
                relative = (root / metadata / code / stem).resolve(strict=True).relative_to(root)
                name = read_regular(root, relative, 4096).decode("utf-8").strip()
            except (OSError, RuntimeError, ValueError):
                continue
            if name:
                return name
    return None


def sha_stream(stream, copy_to=None):
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1 << 20), b""):
        h.update(chunk)
        if copy_to is not None:
            copy_to.write(chunk)
    return h.hexdigest()


def sha_file(path):
    with open(path, "rb") as stream:
        return sha_stream(stream)


def sha_obj(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# Bump only when renderer code changes the pixels. Version 1 uses the original
# four source digests so existing format-1 locks compare equal without migration.
RENDERER_VERSION = (
    "278fee109b8287b5868a099686db95009737e4cbdfe8d4260df4316896548e90",
    "f02108aac92f30d3b10ed91914e9c983d84fdce2e043f97e6fd646714c4e2eb3",
    "20ef3aeb7102e87cfec469987fa268ce6c5e558f2f0070b40ea630f576b368d4",
    "e288399c3e6b29b16cc612d5222fe8b22a642a908fddc209d0233a3d6df4b5ee",
)


def template_hash(name, user=None):
    if user:
        return sha_obj([user.digests, sha_file(Path(render.TEMPLATES) / "base.css"), RENDERER_VERSION])
    template_values.template_name(name)
    files = [Path(render.TEMPLATES) / fn for fn in ("base.css", name + ".html")]
    return sha_obj([sha_file(path) for path in files] + list(RENDERER_VERSION))


def text_of(rec):
    t = rec.get("text") or {}
    val = lambda k: (t.get(k) or {}).get("value") or ""  # noqa: E731
    if "panel" in t:
        p = t["panel"]
        return "panel", {"headline": (p.get("headline") or {}).get("value") or "",
                         "rows": [((r.get("label") or {}).get("value") or "", (r.get("text") or {}).get("value") or "")
                                  for r in p.get("rows", [])]}
    if rec["kind"] == "graphic":
        return "graphic", {"headline": val("headline"), "detail": val("detail")}
    return "shot", {"caption": val("caption"), "detail": val("detail")}


def magick():
    for cmd in (["magick"], ["convert"]):
        if shutil.which(cmd[0]):
            return cmd
    return None


def flatten_rgb(png, deadline):
    """Return the PNG as 8-bit RGB without alpha (stores reject alpha), using ImageMagick."""
    cmd = magick()
    if not cmd:
        return None
    result = subprocess.run(cmd + ["png:-", "-background", "white", "-alpha", "remove", "-alpha", "off",
                            "-strip", "-depth", "8", "PNG24:-"], input=png, stdout=subprocess.PIPE,
                            check=True, timeout=render.cdp.time_left(deadline))
    return result.stdout


MAX_PLAN_ASSET_BYTES = 64 << 20


class Job:
    def __init__(self, root, rec, templates=None, input_roots=None, digests=None):
        self.root, self.rec = root, rec
        self.out = os.path.join(root, rec["outputPath"])
        self.raw = os.path.join(root, rec["rawPath"]) if rec.get("rawPath") else None
        self.kind, self.text = text_of(rec)
        style = rec.get("style") or {}
        self.style = style
        self.mode = rec.get("styleMode") or style.get("mode") or "raw"
        if rec["kind"] == "graphic":
            default = "header" if rec["slotId"].startswith("header-") else "feature"
            self.template = None if rec["slotId"] == "icon" else rec.get("template") or default
            self.mode = "icon" if rec["slotId"] == "icon" else "graphic"
        elif self.kind == "panel":
            selected = rec.get("template") or style.get("template")
            self.template = selected if selected and selected not in template_values.TEMPLATES else "panel"
            self.mode = "panel"
        elif self.mode == "raw":
            self.template = None
        else:
            self.template = rec.get("template") or style.get("template") or "caption-top"
        self.user = None
        if self.template and self.template not in template_values.TEMPLATES:
            self.user = (templates[self.template] if templates is not None
                         else user_templates.resolve(root, self.template))
        self.input_roots = input_roots or {}
        self.digests = {} if digests is None else digests
        self.branded = self.user is not None or self.template in ("feature", "header", "panel")
        self.fonts = {role: [os.path.normpath(os.path.join(root, p)) for p in paths]
                      for role, paths in (style.get("fonts") or {}).items()}
        self.logo = os.path.normpath(os.path.join(root, style["logo"])) if style.get("logo") else None
        if not self.branded:
            self.logo = None
        self.source = os.path.normpath(os.path.join(root, rec["from"])) if rec.get("from") else None
        self.icon_digest = None
        self.adopted = None
        self.problems = []

    def location(self, path):
        file = Path(path)
        base = Path(self.root) if path == self.raw else self.input_roots.get(file, Path(self.root))
        return base, file.relative_to(base)

    def read_input(self, path):
        base, relative = self.location(path)
        data = read_regular(base, relative, MAX_PLAN_ASSET_BYTES)
        expected = self.digests.get(path)
        if expected is not None and hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"{relative}: input changed during compose")
        return data

    def digest(self, path):
        if path not in self.digests:
            self.digests[path] = hashlib.sha256(self.read_input(path)).hexdigest()
        return self.digests[path]

    def keys(self):
        """(content key, style key): content is what the image shows, style is how it is drawn."""
        size = self.rec["size"]
        if self.mode == "raw":
            return sha_obj([size, self.digest(self.raw)]), sha_obj(["png24", 1])
        if self.mode == "icon":
            with open_regular(*self.location(self.source)) as stream:
                self.icon_digest = sha_stream(stream)
            return sha_obj([size, self.icon_digest]), sha_obj(["png32", 1])
        content = {"size": size, "text": self.text}
        if self.raw:
            content["capture"] = self.digest(self.raw)
        if self.branded and not self.logo:
            content["brand"] = self.rec.get("appName")
        fonts = {role: [self.digest(p) for p in paths] for role, paths in self.fonts.items()}
        style = {"template": template_hash(self.template, self.user), "palette": self.style.get("palette"), "fonts": fonts,
                 "logo": self.digest(self.logo) if self.logo else None, "locale": self.rec.get("storeCode")}
        style.update({key: self.style[key] for key in ("align", "gap") if key in self.style})
        if self.user or self.kind == "shot":
            style["fit"] = self.fit()
            if self.user or self.template in ("caption-top", "caption-bottom"):
                style["bezel"] = self.style.get("bezel")
        return sha_obj(content), sha_obj(style)

    def fit(self):
        if self.template == "full-bleed":
            return "cover"
        return self.style.get("fit") or ("bleed" if (self.style.get("bezel") or {}).get("bleed") else "contain")

    def asset_args(self):
        data = None
        shot_size = None
        if self.raw and self.kind == "shot":
            data = self.read_input(self.raw)
            inspect = imginfo._jpeg if data.startswith(b"\xff\xd8") else imginfo._png
            w, h, _, _ = inspect(io.BytesIO(data))
            if not w:
                raise render.RenderError("raw capture is not a readable image: %s" % self.rec["rawPath"])
            shot_size = (w, h)
        font_paths = dict.fromkeys(p for paths in self.fonts.values() for p in paths)
        assets = {p: render.Asset(p, self.read_input(p)) for p in font_paths}
        fonts = {role: [assets[p] for p in paths] for role, paths in self.fonts.items()}
        logo = render.Asset(self.logo, self.read_input(self.logo)) if self.logo else None
        return dict(template=self.template, user=self.user, locale=self.rec.get("storeCode") or "en-US", style=self.style,
                    fonts=fonts, text=self.text, raw=data,
                    shot_size=shot_size, logo=logo, app_name=self.rec.get("appName"), fit=self.fit())

    def missing_inputs(self):
        out = []
        if self.template:
            for role in ("headline", "detail"):
                for p in self.fonts.get(role, []):
                    if not os.path.isfile(p):
                        out.append("font file not found: %s" % os.path.relpath(p, self.root))
            if self.logo and not os.path.isfile(self.logo):
                out.append("logo not found: %s" % os.path.relpath(self.logo, self.root))
        if self.mode == "icon" and self.source and not os.path.isfile(self.source):
            out.append("icon source not found: %s" % self.rec["from"])
        return out


def build(job, renderer):
    """Return the output bytes for a job, or None after recording problems."""
    deadline = render.cdp.new_deadline()
    w, h = job.rec["size"]
    if job.mode == "raw":
        data = job.read_input(job.raw)
        iw, ih, _, _ = imginfo._png(io.BytesIO(data))
        if (iw, ih) != (w, h):
            job.problems.append("raw mode needs a %dx%d capture in PNG format; %s is %sx%s" %
                                (w, h, job.rec["rawPath"], iw, ih))
            return None
        return verify_rgb(flatten_rgb(data, deadline), w, h, deadline)
    if job.mode == "icon":
        if not job.source:
            return b""  # nothing to derive; an existing icon is left alone
        cmd = magick()
        if not cmd:
            job.problems.append("deriving the Play icon needs ImageMagick")
            return None
        with tempfile.TemporaryDirectory() as d:
            dst = os.path.join(d, "icon.png")
            source = Path(d) / ("source" + Path(job.source).suffix)
            with open_regular(*job.location(job.source)) as stream, source.open("wb") as snapshot:
                digest = sha_stream(stream, snapshot)
            if job.icon_digest is not None and digest != job.icon_digest:
                raise ValueError("%s: input changed during compose" % job.rec["from"])
            subprocess.run(cmd + [str(source), "-resize", "%dx%d!" % (w, h), "-strip", "-depth", "8", "PNG32:" + dst], check=True, timeout=render.cdp.time_left(deadline))
            with open(dst, "rb") as f:
                return f.read()
    try:
        png, report = render.render(renderer, size=(w, h), deadline=deadline, **job.asset_args())
    except (render.RenderError, fontcheck.FontError, KeyError) as e:
        job.problems.append(str(e))
        return None
    job.report = report
    if report["problems"]:
        job.problems.extend(report["problems"])
        return None
    if imginfo._png(io.BytesIO(png)) != (w, h, 8, 2):
        png = flatten_rgb(png, deadline)
    return verify_rgb(png, w, h, deadline)


def verify_rgb(data, width, height, deadline):
    if not data or imginfo._png(io.BytesIO(data)) != (width, height, 8, 2):
        raise ValueError("normalized output is not a %dx%d 8-bit RGB PNG" % (width, height))
    render.cdp.time_left(deadline)
    return data


def inline_asset(url, assets):
    asset = assets[url]
    data = asset if isinstance(asset, bytes) else Path(asset).read_bytes()
    mime = render.cdp.MIME[os.path.splitext(url)[1]].split(";")[0]
    return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii"))


def preview_page(jobs, renderer=None):
    frames = []
    for job in jobs:
        if job.problems:
            label = html.escape(job.rec["outputPath"])
            detail = html.escape(", ".join(job.problems))
            frames.append(f"<figure><figcaption>{label}</figcaption><p>{detail}</p></figure>")
            continue
        w, h = job.rec["size"]
        if job.user:
            png = build(job, renderer)
            if png is None:
                raise ValueError("%s: %s" % (job.rec["outputPath"], ", ".join(job.problems)))
            page = '<style>*{margin:0}</style><img alt="" src="%s">' % inline_asset("/image.png", {"/image.png": png})
        elif job.template:
            assets = render.page_assets(**job.asset_args())
            page = assets["/index.html"].decode()
            def stylesheet(match):
                css = assets[match[1]]
                css = css.decode() if isinstance(css, bytes) else Path(css).read_text(encoding="utf-8")
                css = re.sub(r"url\((/[^)]+)\)", lambda m: "url(" + inline_asset(m[1], assets) + ")", css)
                return "<style>" + css + "</style>"
            page = re.sub(r'<link rel="stylesheet" href="(/[^"]+)">', stylesheet, page)
            page = re.sub(r'(<img [^>]*?src=")(/[^"]+)"',
                          lambda m: m[1] + inline_asset(m[2], assets) + '"', page)
        else:
            source = job.raw or job.source
            if not source:
                source = job.out
            key = "/image" + Path(source).suffix.lower()
            page = ('<!doctype html><style>*{margin:0}img{width:100vw;height:100vh;object-fit:contain}</style>'
                    '<img alt="" src="%s">' % inline_asset(key, {key: job.read_input(job.raw) if job.raw else source}))
        scale = min(300 / w, 420 / h, 1)
        label = html.escape(job.rec["outputPath"])
        frames.append('<figure><figcaption>%s</figcaption><div style="width:%gpx;height:%gpx">'
                      '<iframe sandbox title="%s" width="%d" height="%d" style="transform:scale(%.9f)" '
                      'srcdoc="%s"></iframe></div></figure>' %
                      (label, w*scale, h*scale, label, w, h, scale, html.escape(page, quote=True)))
    return ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            """<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; """
            """form-action 'none'; base-uri 'none'; font-src data:; img-src data:; frame-src 'self' about:"><title>Listing preview</title>"""
            '<style>body{display:flex;flex-wrap:wrap;align-items:start;gap:2em;font:14px system-ui}'
            'figure{margin:0;max-width:310px}figcaption{overflow-wrap:anywhere;margin:.5em 0}'
            'figure div{overflow:hidden}iframe{display:block;transform-origin:top left;border:0}</style>'
            + "".join(frames)).encode()


def report_failures(failed):
    for job in failed:
        for problem in job.problems:
            print("compose: %s: %s" % (job.rec["outputPath"], problem), file=sys.stderr)


def compose_outputs(args, man, state, templates, input_roots):
    root = state.root
    digests = {}
    jobs = [Job(root, rec, templates, input_roots, digests) for rec in man["outputs"]
            if (not args.target or rec.get("targetId") in args.target)
            and (not args.screen or rec.get("screenId") in args.screen)]
    missing = set()
    for job in jobs:
        if job.kind == "shot" and (not job.raw or not os.path.isfile(job.raw)):
            missing.add(job.raw)
            rec = job.rec
            job.problems.append(f"no raw capture at {rec.get('rawPath')} (target {rec['targetId']}, "
                                f"screen {rec['screenId']}, locale {rec.get('localeId', 'unknown')})")
        job.problems.extend(job.missing_inputs())
        if job.branded and not job.rec.get("appName"):
            job.rec = dict(job.rec, appName=listing_name(root, man, job.rec))
    if missing:
        print("compose: %d missing capture%s" % (len(missing), "" if len(missing) == 1 else "s"), file=sys.stderr)
    if args.preview:
        rel = ".listing-kit/preview.html"
        current = state.digest(rel)
        conflict = current and current != state.outputs.get(rel, {}).get("sha256")
        failures = [job for job in jobs if job.problems]
        report_failures(failures)
        if conflict and failures and args.adopt:
            raise ValueError(f"{rel}: cannot adopt an existing preview with failed inputs")
        if conflict and not args.adopt:
            raise ValueError("%s: %s" % (rel, ownership.CONFLICT))
        with ExitStack() as resources:
            renderer = None
            if any(job.user and not job.problems for job in jobs):
                browser, renderer = render.open_browser()
                resources.callback(browser.close)
            page = preview_page(jobs, renderer)
        sha = hashlib.sha256(page).hexdigest()
        if current != sha or rel not in state.outputs or state.outputs[rel]["sha256"] != sha:
            state.publish(rel, page, dict(sha256=sha, content=sha, style=sha), current if args.adopt else None)
            if conflict:
                print("adopting " + rel)
        print(os.path.join(root, rel))
        return int(bool(failures))

    todo, restyled, failed = [], [], []
    planned = {rec["outputPath"] for rec in man["outputs"]}
    def versions():
        return {v["renderer"]["browser"] for k, v in state.outputs.items() if k in planned and v.get("renderer")}

    compare_browser = args.restyle and len(versions()) > 1
    cached = []
    unchanged = 0
    for job in jobs:
        rel = job.rec["outputPath"]
        if job.mode == "icon" and not job.source:
            continue
        prev = state.outputs.get(rel, {})
        current = state.digest(rel)
        if current and prev.get("sha256") != current:
            if not args.adopt:
                job.problems.append(ownership.CONFLICT)
            else:
                job.adopted = current
        if job.problems:
            failed.append(job)
            continue
        try:
            job.content, job.stylekey = job.keys()
        except (OSError, ValueError) as exc:
            job.problems.append(str(exc))
            failed.append(job)
            continue
        if current and not job.adopted and prev.get("content") == job.content:
            renderer_os = (prev.get("renderer") or {}).get("os")
            if prev.get("style") == job.stylekey and (not job.template or renderer_os == sys.platform):
                if job.template and compare_browser:
                    cached.append(job)
                unchanged += 1
                continue
            restyled.append(job)
        elif current and not job.adopted and job.branded and not job.logo and not job.rec.get("appName"):
            if prev.get("hasBrandName") is not False:
                # Older lock entries cannot say whether the previous image had a name.
                print("compose: %s: no listing brand name found for the replacement image" % rel)
            if prev.get("hasBrandName"):
                restyled.append(job)
        todo.append(job)

    if restyled and not args.restyle:
        print("%d existing file(s) would be restyled. Rerun with --restyle to replace them:" % len(restyled))
        for job in restyled:
            print("  " + job.rec["outputPath"])
        return 4
    failure_code = 1
    written = held = 0
    browser = renderer = fingerprint = None
    try:
        if not args.dry_run and (cached or any(job.template for job in todo)):
            try:
                path = render.cdp.find_browser()
                if not path:
                    raise render.cdp.BrowserError("no executable found")
                browser, renderer = render.open_browser(path)
                fingerprint = {"os": sys.platform, "browser": browser.version_major()}
            except (OSError, render.cdp.BrowserError, subprocess.TimeoutExpired) as exc:
                if browser:
                    browser.close()
                    browser = None
                reason = "framed screenshots need Chrome, Chromium, Edge or Brave."
                override = os.environ.get("LK_BROWSER")
                if override:
                    reason += " LK_BROWSER=%s:" % override
                reason += " " + str(exc)
                blocked = cached + [job for job in todo if job.template]
                todo = [job for job in todo if not job.template]
                unchanged -= len(cached)
                if not todo and not unchanged and not failed:
                    failure_code = 3
                for job in blocked:
                    job.problems.append(reason)
                failed.extend(blocked)
            else:
                for job in cached:
                    if state.outputs[job.rec["outputPath"]]["renderer"] != fingerprint:
                        todo.append(job)
                        unchanged -= 1
        if todo and not args.dry_run and not magick():
            report_failures(failed)
            print("compose: ImageMagick is needed.", file=sys.stderr)
            return 3
        for job in todo:
            rel = job.rec["outputPath"]
            if args.dry_run:
                if job.adopted:
                    print("would adopt " + rel)
                print("would write " + rel)
                continue
            try:
                if job.template and browser is None:
                    browser, renderer = render.open_browser(path)
                    fingerprint = {"os": sys.platform, "browser": browser.version_major()}
                data = build(job, renderer)
            except (OSError, ValueError, zlib.error, subprocess.SubprocessError, render.cdp.BrowserError) as exc:
                if browser and isinstance(exc, (render.cdp.BrowserError, BrokenPipeError, subprocess.TimeoutExpired)):
                    browser.close()
                    browser = renderer = None
                job.problems.append(str(exc))
                data = None
            if data is None:
                failed.append(job)
                continue
            report = getattr(job, "report", {})
            entry = dict(content=job.content, style=job.stylekey, sha256=hashlib.sha256(data).hexdigest(),
                         size=job.rec["size"], renderer=fingerprint if job.template else None,
                         checks={k: report.get(k) for k in ("worstContrast", "textShare", "bleedCut")} if job.template else None)
            if job.branded and not job.logo:
                entry["hasBrandName"] = bool(job.rec.get("appName"))
            try:
                state.publish(rel, data, entry, job.adopted)
            except ownership.OwnershipConflict as exc:
                job.problems.append(str(exc))
                failed.append(job)
                continue
            except (OSError, ValueError) as exc:
                raise ValueError("%s: %s" % (rel, exc)) from exc
            if job.adopted:
                print("adopting " + rel)
            written += 1
            print("wrote " + rel)
    finally:
        if browser:
            browser.close()

    if not args.dry_run and failure_code != 3:
        for rel in man.get("stale", []):
            if rel in planned:
                continue
            dst = state.hold(rel)
            if dst:
                held += 1
                print("moved out of the upload tree: %s -> %s" % (rel, dst))
            else:
                print("left unowned or edited stale file in place: " + rel)
        if len(versions()) > 1:
            print("note: this set contains images drawn by different browser versions.")
    print("compose: %d written, %d unchanged, %d held, %d failed" % (written, unchanged, held, len(failed)))
    report_failures(failed)
    return failure_code if failed else 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root")
    ap.add_argument("--target", action="append", default=[], help="select a target ID (repeatable)")
    ap.add_argument("--screen", action="append", default=[], help="select a screen ID within the selected targets (repeatable)")
    ap.add_argument("--restyle", action="store_true")
    ap.add_argument("--adopt", action="store_true", help="list and replace conflicting planned files")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--preview", action="store_true", help="write selected outputs to .listing-kit/preview.html, labeling missing raw captures")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return exc.code
    root = os.path.realpath(args.root)
    try:
        with ExitStack() as resources:
            try:
                state = resources.enter_context(ownership.exclusive_state(root))
                man, templates, input_roots = plan.compose_inputs(root)
            except FileNotFoundError:
                if (Path(root) / plan.LISTING).exists():
                    raise
                print("compose: no .listing-kit/listing.json under " + root, file=sys.stderr)
                return 2
            except (plan.PlanError, specs.SpecsError) as exc:
                print("compose: invalid plan: %s" % exc, file=sys.stderr)
                return 2
            return compose_outputs(args, man, state, templates, input_roots)
    except (OSError, ValueError, zlib.error, render.RenderError, render.cdp.BrowserError) as exc:
        print("compose: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
