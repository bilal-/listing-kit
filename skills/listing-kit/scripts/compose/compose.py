#!/usr/bin/env python3
"""Turn raw captures into the store images the plan describes.

Reads .listing-kit/listing.json through plan.manifest() and, for every output:
  raw mode      copies the normalized capture (it must already be the target size);
  framed/band   renders a bundled template around the capture;
  panel         renders a brand panel with no capture;
  graphics      renders the feature graphic and headers; derives the Play icon.

Only what changed is written. .listing-kit/compose.lock.json records what each
output was made from, and .listing-kit/outputs.json records which files the kit
owns. A change that would restyle images whose own content did not change needs
--restyle. Files the plan no longer produces are moved to .listing-kit/held/.

Usage: compose.py <app-root> [--target ID]... [--screen ID]... [--restyle] [--dry-run]
Exit:  0 done; 1 a problem with an input or an image (details printed);
       2 usage or an invalid plan; 3 no browser or ImageMagick for what is needed;
       4 would restyle existing images (rerun with --restyle).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.normpath(os.path.join(HERE, "..", "lib"))
sys.path.insert(0, LIB)
sys.path.insert(0, HERE)
import imginfo  # noqa: E402
import plan  # noqa: E402
import specs  # noqa: E402
import render  # noqa: E402
import fontcheck  # noqa: E402

LOCK = os.path.join(".listing-kit", "compose.lock.json")
RECORD = os.path.join(".listing-kit", "outputs.json")
HELD = os.path.join(".listing-kit", "held")
KIT = os.path.normpath(os.path.join(HERE, "..", ".."))


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha_obj(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def kit_version():
    try:
        with open(os.path.join(KIT, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "unknown"


def template_hash(name):
    h = hashlib.sha256()
    for fn in ("base.css", name + ".html"):
        with open(os.path.join(render.TEMPLATES, fn), "rb") as f:
            h.update(f.read())
    return h.hexdigest()


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


def write_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".lk-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_json(path, obj):
    write_atomic(path, (json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def magick():
    for cmd in (["magick"], ["convert"]):
        if shutil.which(cmd[0]):
            return cmd
    return None


def flatten_rgb(png):
    """Return the PNG as 8-bit RGB without alpha (stores reject alpha), using ImageMagick."""
    cmd = magick()
    if not cmd:
        return None
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "in.png"), os.path.join(d, "out.png")
        with open(src, "wb") as f:
            f.write(png)
        subprocess.run(cmd + [src, "-background", "white", "-alpha", "remove", "-alpha", "off", "-strip",
                              "-depth", "8", "-define", "png:color-type=2", "PNG24:" + dst], check=True)
        with open(dst, "rb") as f:
            return f.read()


class Job:
    def __init__(self, root, rec, rules_stamp):
        self.root, self.rec = root, rec
        self.out = os.path.join(root, rec["outputPath"])
        self.raw = os.path.join(root, rec["rawPath"]) if rec.get("rawPath") else None
        self.kind, self.text = text_of(rec)
        style = rec.get("style") or {}
        self.style = style
        self.mode = rec.get("styleMode") or style.get("mode") or "raw"
        if rec["kind"] == "graphic":
            self.template = None if rec["slotId"] == "icon" else "feature"
            self.mode = "icon" if rec["slotId"] == "icon" else "graphic"
        elif self.kind == "panel":
            self.template, self.mode = "panel", "panel"
        elif self.mode == "raw":
            self.template = None
        else:
            self.template = rec.get("template") or style.get("template") or "caption-top"
        self.fonts = {role: [os.path.normpath(os.path.join(root, p)) for p in paths]
                      for role, paths in (style.get("fonts") or {}).items()}
        self.logo = os.path.normpath(os.path.join(root, style["logo"])) if style.get("logo") else None
        self.source = os.path.normpath(os.path.join(root, rec["from"])) if rec.get("from") else None
        self.rules_stamp = rules_stamp
        self.problems = []

    def keys(self):
        """(content key, style key): content is what the image shows, style is how it is drawn."""
        files = {}
        for label, p in [("raw", self.raw), ("logo", self.logo), ("from", self.source)]:
            if p:
                files[label] = sha_file(p) if os.path.isfile(p) else None
        content = sha_obj({"text": self.text, "raw": files.get("raw"), "from": files.get("from"),
                           "size": self.rec["size"]})
        fonts = {role: [sha_file(p) if os.path.isfile(p) else None for p in paths] for role, paths in self.fonts.items()}
        style = sha_obj({"mode": self.mode, "template": self.template,
                         "templateHash": template_hash(self.template) if self.template else None,
                         "palette": self.style.get("palette"), "bezel": self.style.get("bezel"),
                         "fit": self.style.get("fit"), "fonts": fonts, "logo": files.get("logo"),
                         "locale": self.rec.get("storeCode"), "kit": kit_version(), "rules": self.rules_stamp})
        return content, style

    def missing_inputs(self):
        out = []
        if self.mode in ("raw", "framed", "band") or (self.kind == "shot" and self.template):
            if not self.raw or not os.path.isfile(self.raw):
                out.append("no raw capture at %s" % self.rec.get("rawPath"))
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
    w, h = job.rec["size"]
    if job.mode == "raw":
        iw, ih, depth, ct = imginfo.image_info(job.raw)
        if (iw, ih) != (w, h):
            job.problems.append("raw mode needs a %dx%d capture; %s is %sx%s" % (w, h, job.rec["rawPath"], iw, ih))
            return None
        with open(job.raw, "rb") as f:
            data = f.read()
        return data if (depth, ct) == (8, 2) else flatten_rgb(data)
    if job.mode == "icon":
        if not job.source:
            return b""  # nothing to derive; an existing icon is left alone
        cmd = magick()
        if not cmd:
            job.problems.append("deriving the Play icon needs ImageMagick")
            return None
        with tempfile.TemporaryDirectory() as d:
            dst = os.path.join(d, "icon.png")
            subprocess.run(cmd + [job.source, "-resize", "%dx%d!" % (w, h), "-strip", "-depth", "8", "PNG32:" + dst], check=True)
            with open(dst, "rb") as f:
                return f.read()
    shot_size = None
    if job.raw and job.kind == "shot":
        iw, ih, _, _ = imginfo.image_info(job.raw)
        if not iw:
            job.problems.append("raw capture is not a readable image: %s" % job.rec["rawPath"])
            return None
        shot_size = (iw, ih)
    fit = job.style.get("fit") or ("bleed" if (job.style.get("bezel") or {}).get("bleed") else "contain")
    bezel = dict(job.style.get("bezel") or {})
    style = {"palette": job.style.get("palette") or {}, "bezel": bezel}
    try:
        png, report = render.render(renderer, job.template, (w, h), job.rec.get("storeCode") or "en-US", style,
                                    job.fonts, job.text, raw=job.raw if job.kind == "shot" else None,
                                    shot_size=shot_size, logo=job.logo, app_name=job.rec.get("appName"), fit=fit)
    except (render.RenderError, fontcheck.FontError, KeyError) as e:
        job.problems.append(str(e))
        return None
    job.report = report
    if report["problems"]:
        job.problems.extend(report["problems"])
        return None
    path_w, path_h = w, h
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t:
        t.write(png)
    try:
        iw, ih, depth, ct = imginfo.image_info(t.name)
    finally:
        os.unlink(t.name)
    if (iw, ih) != (path_w, path_h):
        job.problems.append("rendered %sx%s, expected %dx%d" % (iw, ih, w, h))
        return None
    return png if (depth, ct) == (8, 2) else flatten_rgb(png)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root")
    ap.add_argument("--target", action="append", default=[])
    ap.add_argument("--screen", action="append", default=[])
    ap.add_argument("--restyle", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    root = os.path.abspath(args.root)
    try:
        data = plan.load(root)
        rules = specs.load(root)
        man = plan.manifest(data, rules, root)
    except FileNotFoundError:
        sys.stderr.write("compose: no .listing-kit/listing.json under %s\n" % root)
        return 2
    except (plan.PlanError, specs.SpecsError) as e:
        sys.stderr.write("compose: the plan is not valid:\n%s\n" % e)
        return 2
    stamp = {"verified": rules.get("verified"), "override": bool(rules.get("_override"))}
    lock = read_json(os.path.join(root, LOCK), {"format": 1, "outputs": {}})
    if lock.get("format") != 1 or not isinstance(lock.get("outputs"), dict):
        lock = {"format": 1, "outputs": {}}
    jobs = [Job(root, rec, stamp) for rec in man["outputs"]
            if (not args.target or rec.get("targetId") in args.target)
            and (not args.screen or rec.get("screenId") in args.screen)]
    todo, restyled, failed, unchanged = [], [], [], 0
    for job in jobs:
        miss = job.missing_inputs()
        if miss:
            job.problems = miss
            failed.append(job)
            continue
        job.content, job.stylekey = job.keys()
        prev = lock["outputs"].get(job.rec["outputPath"])
        on_disk = os.path.isfile(job.out)
        if prev and on_disk and prev.get("content") == job.content and prev.get("style") == job.stylekey \
                and prev.get("sha256") == sha_file(job.out):
            unchanged += 1
            continue
        if prev and on_disk and prev.get("content") == job.content and prev.get("style") != job.stylekey \
                and prev.get("sha256") == sha_file(job.out):
            restyled.append(job)
        todo.append(job)
    if restyled and not args.restyle:
        print("compose: %d image(s) would be redrawn although their content did not change "
              "(style, template, fonts, kit or rules changed). Rerun with --restyle to redraw them:" % len(restyled))
        for job in restyled:
            print("  " + job.rec["outputPath"])
        return 4
    needs_browser = any(j.template for j in todo)
    if needs_browser and not render.cdp.find_browser():
        sys.stderr.write("compose: framed screenshots need Chrome, Chromium, Edge or Brave. Found none. "
                         "Install one, or set style.mode to raw.\n")
        return 3
    if todo and not magick():
        sys.stderr.write("compose: ImageMagick is needed (brew install imagemagick / apt install imagemagick).\n")
        return 3
    written = []
    browser = renderer = None
    fingerprint = None
    try:
        if needs_browser and not args.dry_run:
            browser, renderer = render.open_browser()
            fingerprint = {"os": sys.platform, "browser": browser.version_major()}
        for job in todo:
            if args.dry_run:
                print("would write " + job.rec["outputPath"])
                continue
            try:
                data_out = build(job, renderer)
            except (subprocess.CalledProcessError, OSError, render.cdp.BrowserError) as e:
                job.problems.append(str(e))
                data_out = None
            if data_out is None:
                failed.append(job)
                continue
            if data_out == b"":
                continue
            write_atomic(job.out, data_out)
            lock["outputs"][job.rec["outputPath"]] = {
                "content": job.content, "style": job.stylekey, "sha256": hashlib.sha256(data_out).hexdigest(),
                "size": job.rec["size"], "renderer": fingerprint if job.template else None,
                "checks": {k: getattr(job, "report", {}).get(k) for k in ("worstContrast", "textShare", "bleedCut")}
                if job.template else None}
            written.append(job.rec["outputPath"])
            print("wrote " + job.rec["outputPath"])
    finally:
        if browser:
            browser.close()
    if args.dry_run:
        return 1 if failed else 0
    # Files the kit wrote earlier that the plan no longer produces leave the upload tree.
    held = []
    planned = {rec["outputPath"] for rec in man["outputs"]}
    for rel in man.get("stale", []):
        src = os.path.join(root, rel)
        if rel in planned or not os.path.isfile(src):
            continue
        dst = os.path.join(root, HELD, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.replace(src, dst)
        lock["outputs"].pop(rel, None)
        held.append(rel)
        print("moved out of the upload tree: %s -> %s" % (rel, os.path.join(HELD, rel)))
    owned = sorted(p for p in lock["outputs"] if os.path.isfile(os.path.join(root, p)))
    write_json(os.path.join(root, LOCK), lock)
    write_json(os.path.join(root, RECORD), {"format": 1, "files": owned})
    mixed = {json.dumps(v.get("renderer"), sort_keys=True) for v in lock["outputs"].values() if v.get("renderer")}
    if len(mixed) > 1:
        print("note: the set now mixes renderer versions; run with --restyle when convenient.")
    for job in failed:
        for p in job.problems:
            sys.stderr.write("compose: %s: %s\n" % (job.rec["outputPath"], p))
    print("compose: %d written, %d unchanged, %d held, %d failed" % (len(written), unchanged, len(held), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
