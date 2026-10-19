#!/usr/bin/env python
"""
Checks what a sushichef builds without uploading anything to Studio or downloading its videos, so that a scraper can be
verified with one command instead of by hand, e.g.

    python tests/verify_chef.py tests/chef_cs50.py --set 'WEEKS=["1", "10"]' --browser
    python tests/verify_chef.py tests/chef_ocw.py --option course=https://ocw.mit.edu/courses/... --browser
    python tests/verify_chef.py tests/chef_pretext.py --set 'SUBCHAPTER_FILTER="10."' --browser

It runs the chef's construct_channel twice, the way the chefs' __main__ does, giving every node a stand-in node id
between the runs (in the chef's module level orig_urls_to_node_ids), so the links made into navigation between nodes on
the second run can be checked too. Then it checks:

- the tree: node counts, empty topics, duplicate titles and source ids, nodes failing ricecooker's validation, which
  video files and subtitles the videos have, and that the documents' files exist
- the pages, statically: every file a page references in its dependency zip (/zipcontent/<checksum>.zip/...) is in it,
  relative references resolve inside the page's own zip, navigation goes to nodes that exist, and which links still go
  to the source site and which resources still come from the internet
- with --browser, each page loaded in headless Chromium from a server laid out like Kolibri's zipcontent, with every
  other request blocked: failed requests, JavaScript errors, broken images, failed fonts and MathJax errors

It prints a short summary, and writes everything it found to a JSON report (--report) for a closer look.

--set NAME=VALUE overrides one of the chef module's settings before it runs, VALUE is a Python literal. --option
key=value is passed to construct_channel, like the key=value options on a chef's command line.
"""
import argparse
import ast
import collections
import hashlib
import http.server
import importlib.util
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import zipfile
from urllib.parse import unquote
from urllib.parse import urlparse

from bs4 import BeautifulSoup

# how many examples of each problem to show in the summary, the report has all of them
EXAMPLES_SHOWN = 5
BROWSER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify_pages.js")
ZIPCONTENT_RE = re.compile(r"/zipcontent/([0-9a-f]{32})\.zip/([^\"'\s)<>]*)")
NAVIGATE_RE = re.compile(r"navigateTo\(\s*['\"]([^'\"]+)['\"]")
# tags whose attribute references a resource the page loads, rather than a page it links to
RESOURCE_ATTRIBUTES = {"img": "src", "script": "src", "iframe": "src", "source": "src", "video": "src", "audio": "src",
                       "link": "href", "embed": "src"}


class Report(object):
    def __init__(self, ignore=()):
        self.checks = collections.OrderedDict()
        # problems already looked at, e.g. ones in the source site itself, which don't make a check fail or warn
        self.ignore = [re.compile(pattern) for pattern in ignore]

    def add(self, name, status, summary, examples=None):
        """status is PASS, WARN, FAIL or INFO, examples are the details, all kept in the report"""
        examples = list(examples or [])
        ignored = [e for e in examples if any(pattern.search(str(e)) for pattern in self.ignore)]
        if status in ("WARN", "FAIL") and ignored:
            examples = [e for e in examples if e not in ignored]
            summary += " ({} ignored)".format(len(ignored))
            if not examples:
                status = "PASS"
        self.checks[name] = {"status": status, "summary": summary, "examples": examples, "ignored": ignored}

    def print_summary(self):
        for name, check in self.checks.items():
            print("{:5} {:28} {}".format(check["status"], name, check["summary"]))
            if check["status"] in ("WARN", "FAIL"):
                for example in check["examples"][:EXAMPLES_SHOWN]:
                    print("        - {}".format(example))
                if len(check["examples"]) > EXAMPLES_SHOWN:
                    print("        ... {} more in the report".format(len(check["examples"]) - EXAMPLES_SHOWN))
        counts = collections.Counter(check["status"] for check in self.checks.values())
        print("\n{} passed, {} warnings, {} failed".format(counts["PASS"], counts["WARN"], counts["FAIL"]))

    def save(self, path):
        with open(path, "w") as f:
            json.dump(self.checks, f, indent=1)


def status_for(problems, failing=True):
    return ("FAIL" if failing else "WARN") if problems else "PASS"


# RUNNING THE CHEF


def load_chef(path, settings):
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    for setting in settings:
        key, value = setting.split("=", 1)
        if not hasattr(module, key):
            raise SystemExit("{} has no setting {}".format(path, key))
        setattr(module, key, ast.literal_eval(value))
    return module


def chef_class(module):
    from ricecooker.chefs import SushiChef

    classes = [value for value in vars(module).values()
               if isinstance(value, type) and issubclass(value, SushiChef) and value is not SushiChef
               and value.__module__ == module.__name__]
    if len(classes) != 1:
        raise SystemExit("Expected one SushiChef subclass in {}, found {}".format(module.__name__, classes))
    return classes[0]


def walk(node, depth=0, parent=None):
    yield node, depth, parent
    for child in node.children:
        yield from walk(child, depth + 1, node)


def stand_in_node_id(source_id):
    return hashlib.md5(source_id.encode("utf-8")).hexdigest()


def run_chef_twice(module, options, report):
    chef = chef_class(module)()
    channel = chef.construct_channel(**options)
    node_ids = getattr(module, "orig_urls_to_node_ids", None)
    if node_ids is None:
        report.add("chef.two_runs", "WARN", "the chef has no orig_urls_to_node_ids, only ran once, navigation not checked")
        return channel, {}
    node_ids.update((node.source_id, stand_in_node_id(node.source_id)) for node, _, _ in walk(channel)
                    if node is not channel)
    channel = chef.construct_channel(**options)
    report.add("chef.two_runs", "PASS", "ran construct_channel twice, the second with {} stand-in node ids".format(
        len(node_ids)))
    return channel, dict(node_ids)


# THE TREE


def kind(node):
    return type(node).__name__.replace("Node", "")


def file_source(file):
    return getattr(file, "path", None) or getattr(file, "youtube_id", None) or getattr(file, "web_url", None) or ""


def check_tree(channel, report):
    nodes = [(node, depth, parent) for node, depth, parent in walk(channel) if node is not channel]
    counts = collections.Counter(kind(node) for node, _, _ in nodes)
    report.add("tree.counts", "INFO", ", ".join("{} {}".format(n, k) for k, n in counts.most_common()) +
               ", {} levels deep".format(max([depth for _, depth, _ in nodes] or [0])))

    empty = [node.title for node, _, _ in nodes if kind(node) == "Topic" and not node.children]
    report.add("tree.empty_topics", status_for(empty), "{} empty topics".format(len(empty)), empty)

    duplicates = []
    for node, _, _ in [(channel, 0, None)] + nodes:
        titles = collections.Counter(child.title for child in node.children)
        duplicates += ["{!r} {} times in {!r}".format(t, n, node.title) for t, n in titles.items() if n > 1]
    report.add("tree.duplicate_titles", status_for(duplicates, failing=False),
               "{} titles repeated among siblings".format(len(duplicates)), duplicates)

    source_ids = collections.Counter(node.source_id for node, _, _ in nodes)
    repeated = ["{} ({} times)".format(s, n) for s, n in source_ids.items() if n > 1]
    report.add("tree.duplicate_source_ids", status_for(repeated), "{} source ids used more than once".format(
        len(repeated)), repeated)

    invalid = []
    for node, _, _ in nodes:
        try:
            if not node.validate():
                invalid.append("{} {!r}".format(kind(node), node.title))
        except Exception as e:
            invalid.append("{} {!r}: {}".format(kind(node), node.title, str(e)[:200]))
    report.add("tree.validation", status_for(invalid), "{} nodes fail ricecooker's validation".format(len(invalid)),
               invalid)

    check_videos([node for node, _, _ in nodes if kind(node) == "Video"], report)

    missing = []
    for node, _, _ in nodes:
        if kind(node) == "Document":
            for file in node.files:
                path = file_source(file)
                if path and not re.match(r"^https?://", path) and not os.path.exists(path):
                    missing.append("{!r}: {}".format(node.title, path))
    report.add("tree.document_files", status_for(missing), "{} documents with missing local files".format(len(missing)),
               missing)


# words in video urls that say which version of a video it is, e.g. lecture1-720p.mp4 or lec1-220k.mp4
VIDEO_VARIANT_RE = re.compile(r"(\d{3,4}p|\d+k(?=\W)|4k|hdr|sdr)", re.I)


def check_videos(videos, report):
    variants = collections.Counter()
    without_subtitles = []
    examples = []
    for video in videos:
        sources = [file_source(f) for f in video.files if type(f).__name__ != "SubtitleFile"]
        subtitles = [getattr(f, "language", "?") for f in video.files if type(f).__name__ == "SubtitleFile"]
        for source in sources:
            found = VIDEO_VARIANT_RE.findall(os.path.basename(urlparse(source).path)) if "/" in source else ["youtube"]
            variants[" ".join(sorted(v.lower() for v in found)) or "unlabeled"] += 1
            examples.append("{!r}: {} subtitles {}".format(video.title, source, subtitles or "none"))
        if not subtitles:
            without_subtitles.append(video.title)
    report.add("videos.versions", "INFO", "video files by the version in their name: {}".format(
        dict(variants) or "no videos"), examples)
    report.add("videos.subtitles", status_for(without_subtitles, failing=False),
               "{} of {} videos without subtitles".format(len(without_subtitles), len(videos)), without_subtitles)


# THE PAGES


class Page(object):
    def __init__(self, node):
        self.node = node
        self.title = node.title
        self.zip_path = None
        self.dependency_zips = {}
        for file in node.files:
            if file.get_preset() == "html5_dependency":
                self.dependency_zips[file.checksum] = file.path
            else:
                self.zip_path = file.path
                self.checksum = file.checksum
        with zipfile.ZipFile(self.zip_path) as z:
            self.html = z.read("index.html").decode("utf-8", errors="replace")
            self.own_files = set(z.namelist())


_zip_contents = {}


def zip_contents(path):
    if path not in _zip_contents:
        with zipfile.ZipFile(path) as z:
            _zip_contents[path] = set(z.namelist())
    return _zip_contents[path]


def in_zip(path, zip_path):
    """whether the zip has the file, or the directory, e.g. a font directory MathJax is pointed at"""
    contents = zip_contents(zip_path)
    directory = path.rstrip("/") + "/"
    return path in contents or directory + "index.html" in contents or any(n.startswith(directory) for n in contents)


def source_hosts(channel):
    hosts = {urlparse(node.source_id).netloc for node, _, _ in walk(channel) if re.match(r"^https?://", node.source_id)}
    hosts.add(urlparse("//" + channel.source_domain.split("://")[-1]).netloc)
    return {host for host in hosts if host}


def check_pages(channel, node_ids, report):
    pages = [Page(node) for node, _, _ in walk(channel) if kind(node) == "HTML5App"]
    hosts = source_hosts(channel)
    known_ids = set(node_ids.values())
    missing, unresolved, bad_navigation, online_links, external = [], [], [], collections.Counter(), collections.Counter()
    navigation_links = 0

    for page in pages:
        for checksum, path in set(ZIPCONTENT_RE.findall(page.html)):
            path = unquote(path.split("?")[0].split("#")[0])
            dependency_zip = page.dependency_zips.get(checksum)
            if not dependency_zip:
                missing.append("{!r}: references zip {} which isn't one of its files".format(page.title, checksum))
            elif path and not in_zip(path, dependency_zip):
                missing.append("{!r}: {}".format(page.title, path))

        soup = BeautifulSoup(page.html, "html.parser")
        for tag, attribute in RESOURCE_ATTRIBUTES.items():
            for element in soup.find_all(tag, attrs={attribute: True}):
                value = element[attribute]
                parsed = urlparse(value)
                if parsed.scheme in ("http", "https") or value.startswith("//"):
                    external[parsed.netloc] += 1
                elif not parsed.scheme and not value.startswith(("/", "#")) and value:
                    path = unquote(parsed.path).lstrip("./")
                    if path and path not in page.own_files:
                        unresolved.append("{!r}: <{} {}={!r}>".format(page.title, tag, attribute, value))

        ids = NAVIGATE_RE.findall(page.html)
        navigation_links += len(ids)
        bad_navigation += ["{!r}: {}".format(page.title, i) for i in ids if node_ids and i not in known_ids]
        for link in soup.find_all("a", href=True):
            parsed = urlparse(link["href"])
            if parsed.scheme in ("http", "https") and parsed.netloc in hosts:
                online_links[link["href"].split("#")[0]] += 1

    report.add("pages.count", "INFO", "{} pages, {} navigation links between nodes".format(len(pages), navigation_links))
    report.add("pages.dependency_files", status_for(missing),
               "{} references to files missing from the dependency zips".format(len(missing)), missing)
    report.add("pages.relative_references", status_for(unresolved),
               "{} relative references not in the page's own zip".format(len(unresolved)), unresolved)
    if node_ids:
        report.add("pages.navigation", status_for(bad_navigation),
                   "{} navigation links to node ids that don't exist".format(len(bad_navigation)), bad_navigation)
    report.add("pages.links_to_source_site", status_for(online_links, failing=False),
               "{} links ({} distinct) still go to {} instead of a node".format(
                   sum(online_links.values()), len(online_links), "/".join(sorted(hosts))),
               ["{} ({} times)".format(u, n) for u, n in online_links.most_common()])
    report.add("pages.internet_resources", status_for(external, failing=False),
               "resources still loaded from the internet, from {} hosts".format(len(external)),
               ["{} ({} times)".format(h, n) for h, n in external.most_common()])
    return pages


# THE BROWSER


def serve_zips(zips):
    """Serves {name: zip path} like Kolibri's zipcontent, /zipcontent/<name>.zip/<path in the zip>"""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parts = unquote(urlparse(self.path).path).split("/", 3)
            try:
                with zipfile.ZipFile(zips[parts[2][:-len(".zip")]]) as z:
                    data = z.read(parts[3] or "index.html")
            except Exception:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(parts[3])[0] or "application/octet-stream")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("localhost", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def check_in_browser(pages, report, max_pages, node_command):
    pages = pages[:max_pages] if max_pages else pages
    zips = {}
    for page in pages:
        zips[page.checksum] = page.zip_path
        zips.update(page.dependency_zips)
    server = serve_zips(zips)
    base = "http://localhost:{}/zipcontent/".format(server.server_address[1])
    config = {"pages": [{"title": p.title, "url": base + p.checksum + ".zip/index.html"} for p in pages],
              "chromium": os.environ.get("VERIFY_CHROMIUM") or default_chromium(),
              "playwright": os.environ.get("VERIFY_PLAYWRIGHT", "playwright")}
    process = subprocess.run(node_command + [BROWSER_SCRIPT, json.dumps(config)], capture_output=True, text=True)
    server.shutdown()
    if process.returncode != 0:
        report.add("browser", "FAIL", "the browser check didn't run: " + process.stderr.strip()[-300:])
        return
    results = [json.loads(line) for line in process.stdout.splitlines() if line.startswith("{")]

    def collect(key, describe=lambda r, item: "{!r}: {}".format(r["title"], item)):
        return [describe(r, item) for r in results for item in r[key]]

    failed = collect("failed")
    report.add("browser.failed_requests", status_for(failed), "{} requests for missing files".format(len(failed)), failed)
    blocked = collections.Counter(urlparse(url).netloc for r in results for url in set(r["blocked"]))
    example_urls = {}
    for r in results:
        for url in r["blocked"]:
            example_urls.setdefault(urlparse(url).netloc, []).append(url)
    report.add("browser.internet_requests", status_for(blocked, failing=False),
               "pages tried to reach {} hosts on the internet".format(len(blocked)),
               ["{} ({} requests), e.g. {}".format(h, len(example_urls[h]), ", ".join(sorted(set(example_urls[h]))[:2]))
                for h, _ in blocked.most_common()])
    errors = collect("errors")
    report.add("browser.javascript_errors", status_for(errors, failing=False), "{} JavaScript errors".format(
        len(errors)), errors)
    images = collect("brokenImages")
    report.add("browser.broken_images", status_for(images), "{} images that didn't load".format(len(images)), images)
    fonts = collect("failedFonts")
    report.add("browser.failed_fonts", status_for(fonts, failing=False), "{} web fonts that didn't load".format(
        len(fonts)), fonts)
    math_errors = ["{!r}: {} math errors".format(r["title"], r["mathErrors"]) for r in results if r["mathErrors"]]
    with_math = [r for r in results if r["math"]]
    report.add("browser.math", status_for(math_errors), "{} pages with math rendered by MathJax, {} with errors".format(
        len(with_math), len(math_errors)), math_errors)
    report.add("browser.pages", "INFO", "loaded {} pages".format(len(results)),
               ["{!r}: {} navigation links, {} math".format(r["title"], r["navigationLinks"], r["math"]) for r in results])


def default_chromium():
    for path in ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome"]:
        if os.path.exists(path):
            return path
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("chef", help="path to the chef's .py file")
    parser.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                        help="override a setting in the chef's module, VALUE is a Python literal")
    parser.add_argument("--option", action="append", default=[], metavar="KEY=VALUE",
                        help="an option passed to construct_channel, like the chef's key=value command line options")
    parser.add_argument("--browser", action="store_true", help="also load every page in headless Chromium")
    parser.add_argument("--max-pages", type=int, default=0, help="only load this many pages in the browser")
    parser.add_argument("--node", default="node", help="the node command to run the browser check with")
    parser.add_argument("--report", default="verify_report.json", help="where to write the full report")
    parser.add_argument("--ignore", action="append", default=[], metavar="REGEX",
                        help="problems matching this are known, e.g. broken in the source site, and don't fail a check")
    args = parser.parse_args()

    report = Report(args.ignore)
    # report the files that can't be downloaded as problems, rather than stopping at the first one
    os.environ["STRICT"] = "False"
    module = load_chef(args.chef, args.set)
    import ricecooker.utils.downloader
    import ricecooker.utils.html
    ricecooker.utils.downloader.STRICT = ricecooker.utils.html.STRICT = False
    options = dict(option.split("=", 1) for option in args.option)
    channel, node_ids = run_chef_twice(module, options, report)
    check_tree(channel, report)
    pages = check_pages(channel, node_ids, report)
    if args.browser and pages:
        check_in_browser(pages, report, args.max_pages, args.node.split())

    print("\n{}: {}\n".format(os.path.basename(args.chef), channel.title))
    report.print_summary()
    report.save(args.report)
    print("full report: {}".format(os.path.abspath(args.report)))
    sys.exit(1 if any(check["status"] == "FAIL" for check in report.checks.values()) else 0)


if __name__ == "__main__":
    main()
