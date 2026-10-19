#!/usr/bin/env python
"""
Sushichef for MIT OpenCourseWare courses, e.g.
    ./chef_ocw.py --token=... course=https://ocw.mit.edu/courses/6-002-circuits-and-electronics-spring-2007/

Each course is its own channel. OCW publishes an offline copy of every course's site as a zip, with a data.json for
each page and resource describing it, so this works from that zip rather than scraping the live site:

- the course's pages are HTML5 apps, flattened into one topic per section of the course's navigation, sharing one
  dependency zip holding the rest of the offline site (css, js, MathJax, images)
- the PDFs are document nodes and the videos are video nodes, from the archive.org MP4s OCW links to (or YouTube when
  there isn't one) with their captions, placed after the pages that link to them

Like chef_pretext.py and chef_cs50.py this runs twice, so the second run can make links between pages, and to the PDFs
and videos, into navigation to the Kolibri nodes, using the node ids from the first run.
"""
import collections
import json
import os
import posixpath
import re
import shutil
import tempfile
import zipfile
from urllib.parse import urldefrag
from urllib.parse import urljoin
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from le_utils.constants import format_presets

from ricecooker.chefs import SushiChef
from ricecooker.classes import licenses
from ricecooker.classes.files import DocumentFile
from ricecooker.classes.files import HTMLZipFile
from ricecooker.classes.files import SubtitleFile
from ricecooker.classes.files import VideoFile
from ricecooker.classes.files import YouTubeVideoFile
from ricecooker.classes.nodes import ChannelNode
from ricecooker.classes.nodes import DocumentNode
from ricecooker.classes.nodes import HTML5AppNode
from ricecooker.classes.nodes import TopicNode
from ricecooker.classes.nodes import VideoNode
from ricecooker.config import LOGGER
from ricecooker.utils.zip import create_predictable_zip


# CHANNEL SETTINGS
# the course to import, can be set on the command line with course=<url>
COURSE_URL = "https://ocw.mit.edu/courses/6-002-circuits-and-electronics-spring-2007/"
CHANNEL_LANGUAGE = "en"
COPYRIGHT_HOLDER = "MIT OpenCourseWare"
LICENSE = licenses.CC_BY_NC_SALicense(copyright_holder=COPYRIGHT_HOLDER)

# where the course's downloaded and extracted offline zip goes
DOWNLOAD_DIR = os.path.join(os.getcwd(), "ocw_courses")
# where images the pages load from the internet, like the video gallery's YouTube thumbnails, are saved in the offline
# site, so that they are in the dependency zip
EXTERNAL_IMAGES_DIR = "external_images"

course = None
dep_zip = None
# where links on the pages should go, from the path of a page or resource in the offline site to the source id of
# its node, e.g. a PDF's resource page and the PDF itself both go to the PDF's document node
link_targets = {}
# the node ids from the first run, by source id, used to make links into navigation between nodes on the second run
orig_urls_to_node_ids = {}

cache_invalidator_string = "                                                                         "


class OCWChef(SushiChef):
    def get_channel(self, *args, **kwargs):
        load_course(kwargs.get("course", COURSE_URL))
        info = course.info
        return ChannelNode(
            source_domain="ocw.mit.edu",
            source_id="mit_ocw_" + info["site_short_id"],
            title="MIT {} {}, {} {}".format(info["primary_course_number"], info["course_title"], info["term"],
                                            info["year"]).strip(),
            description=BeautifulSoup(info.get("course_description_html") or info.get("course_description", ""),
                                      "html.parser").get_text(" ", strip=True)[:400],
            thumbnail=course.local_path(info.get("image_src")),
            license=LICENSE,
            copyright_holder=COPYRIGHT_HOLDER,
            language=CHANNEL_LANGUAGE,
            provider="MIT OpenCourseWare",
        )

    def construct_channel(self, *args, **kwargs):
        channel = self.get_channel(**kwargs)
        topics = course_tree()

        global dep_zip
        if dep_zip is None:
            download_external_images([item["path"] for topic in topics for item in topic["children"]
                                      if item["kind"] == "page"])
            dep_zip = create_predictable_zip(course.root)

        for topic in topics:
            channel.add_child(build_topic(topic))
        return channel


# e.g. r.p="/static_shared/" in OCW's webpack runtime
WEBPACK_ROOT_PUBLIC_PATH_RE = re.compile(r'(\b\w\.p=)"/static_shared/"')


class Course(object):
    """A course's offline site, downloaded from OCW and extracted"""

    def __init__(self, course_url):
        self.url = course_url if course_url.endswith("/") else course_url + "/"
        slug = self.url.rstrip("/").split("/")[-1]
        self.root = os.path.join(DOWNLOAD_DIR, slug)
        if not os.path.isfile(os.path.join(self.root, "data.json")):
            self.download(slug)
        self.fix_webpack_public_path()
        self.info = self.read_json("data.json")
        # the resources' data.json files, by their path in the site, e.g. resources/hw1
        self.resources = {}
        for path in self.read_json("content_map.json").values():
            resource_dir = path.strip("/").rsplit("/", 1)[0]
            if resource_dir.startswith("resources/"):
                self.resources[resource_dir] = self.read_json(path.strip("/"))
        # the videos' transcripts, which are PDFs that stay with the video's page rather than being documents
        self.transcripts = {
            self.site_path(transcript["file"])
            for resource in self.resources.values()
            for transcript in (resource.get("video_files") or {}).get("video_transcript_resources") or []
            if transcript.get("file")
        }

    def download(self, slug):
        download_page = BeautifulSoup(requests.get(self.url + "download/").text, "html.parser")
        zip_url = urljoin(self.url, download_page.find("a", class_="download-course-button")["href"])
        LOGGER.info("Downloading the offline copy of {} from {}".format(self.url, zip_url))
        zip_path = os.path.join(DOWNLOAD_DIR, slug + ".zip")
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        with requests.get(zip_url, stream=True) as response:
            response.raise_for_status()
            with open(zip_path, "wb") as f:
                shutil.copyfileobj(response.raw, f)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(self.root)

    def fix_webpack_public_path(self):
        """
        OCW's scripts load the rest of their webpack chunks from /static_shared/, the root of ocw.mit.edu, which in
        Kolibri is the root of the server rather than the dependency zip the scripts are in. Make them load them from
        the directory the scripts are in instead, the way webpack's automatic public path does
        """
        js_dir = os.path.join(self.root, "static_shared", "js")
        for name in os.listdir(js_dir) if os.path.isdir(js_dir) else []:
            path = os.path.join(js_dir, name)
            with open(path, encoding="utf-8") as f:
                js = f.read()
            fixed = WEBPACK_ROOT_PUBLIC_PATH_RE.sub(
                r'\1(document.currentScript&&document.currentScript.src.replace(/js\/[^\/]*$/,""))||"/static_shared/"', js)
            if fixed != js:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(fixed)

    def read_json(self, path):
        with open(os.path.join(self.root, path), encoding="utf-8") as f:
            return json.load(f)

    def read_page(self, path):
        with open(os.path.join(self.root, path), encoding="utf-8") as f:
            return BeautifulSoup(f.read(), "html.parser")

    def site_path(self, url, relative_to=""):
        """
        The path in the offline site of a url, e.g. pages/syllabus/index.html, for links relative to the page at
        relative_to, absolute links to the course on ocw.mit.edu, and the /courses/<course>/<file> paths in data.json.
        Returns None for links elsewhere
        """
        url = urldefrag(url)[0]
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https") or url.startswith("//"):
            if not url.startswith(self.url) and not url.startswith("//" + self.url.split("//", 1)[1]):
                return None
            path = urlparse(url).path[len(urlparse(self.url).path):]
        elif parsed.scheme:
            return None
        elif url.startswith(urlparse(self.url).path):
            # files in data.json, which are in static_resources in the offline site
            path = "static_resources/" + url[len(urlparse(self.url).path):]
        else:
            path = posixpath.normpath(posixpath.join(posixpath.dirname(relative_to), url))
            if path.startswith(".."):
                # e.g. the OCW logo, linking to the rest of the OCW site
                return None
        if path in ("", "."):
            path = "index.html"
        elif not os.path.splitext(path)[1]:
            path = path.rstrip("/") + "/index.html"
        return path

    def external_image_path(self, url):
        """Where an image from the internet a page uses is saved in the offline site, e.g. YouTube thumbnails"""
        parsed = urlparse(url)
        return posixpath.join(EXTERNAL_IMAGES_DIR, parsed.netloc + parsed.path)

    def local_path(self, path):
        if not path:
            return None
        local = os.path.join(self.root, posixpath.normpath(path.lstrip("./")))
        return local if os.path.exists(local) else None


def load_course(course_url):
    global course
    if course is None or course.url.rstrip("/") != course_url.rstrip("/"):
        course = Course(course_url)


# THE TREE
# described with plain dicts like chef_cs50.py, then turned into nodes by build_topic


def course_tree():
    """
    One topic per top level section of the course's navigation, holding its page and the pages under it, followed by
    the PDFs and videos those pages link to, in the order they are linked
    """
    added = set()
    used_pages = {"index.html"}
    home = {"title": "Course Home", "children": [page_item("index.html", "Course Home")] + resource_items(
        ["index.html"], added)}
    topics = [home]
    sections = navigation_sections()
    used_pages.update(path for _, section_pages in sections for path, _ in section_pages)
    for title, section_pages in sections:
        section_pages = section_pages + linked_pages([path for path, _ in section_pages], used_pages)
        pages = [page_item(path, page_title) for path, page_title in section_pages]
        topics.append({"title": title, "children": pages + resource_items([p["path"] for p in pages], added)})

    # resources none of the pages link to go at the end of the section their data.json says they are part of
    topics_by_title = {topic["title"]: topic for topic in topics}
    others = {"title": "Other Resources", "children": []}
    for resource_dir in sorted(course.resources):
        if resource_dir not in added:
            item = resource_item(resource_dir)
            if item:
                parent = course.resources[resource_dir].get("parent_title")
                topics_by_title.get(parent, others)["children"].append(item)
    if others["children"]:
        topics.append(others)
    return topics


def navigation_sections():
    """[(section title, [(page path, page title), ...]), ...] from the course navigation on the course's home page"""
    nav = course.read_page("index.html").find("nav", class_="course-nav")
    sections = []
    for item in nav.find_all("li", class_="course-nav-list-item", recursive=True):
        if item.find_parent("li", class_="course-nav-list-item"):
            continue
        pages = []
        for link in item.find_all("a", class_="nav-link", href=True):
            path = course.site_path(link["href"], "index.html")
            if path and course.local_path(path) and path not in [p for p, _ in pages]:
                pages.append((path, link.get_text(" ", strip=True)))
        if pages:
            sections.append((pages[0][1], pages))
    return sections


def is_page(path):
    return path.startswith(("pages/", "video_galleries/")) and path.endswith("index.html")


def linked_pages(page_paths, used_pages):
    """
    Pages linked from the pages that aren't in the course navigation, like 1.061's animation pages linked from its
    lecture notes, and the pages they link to in turn
    """
    found = []
    to_scan = list(page_paths)
    while to_scan:
        page_path = to_scan.pop(0)
        for link in course.read_page(page_path).find_all("a", href=True):
            path = course.site_path(link["href"], page_path)
            if path and is_page(path) and path not in used_pages and course.local_path(path):
                used_pages.add(path)
                title = course.read_page(path).find("title")
                found.append((path, title.get_text(strip=True).split("|")[0].strip() if title else link.get_text(strip=True)))
                to_scan.append(path)
    return found


def page_item(path, title):
    link_targets[path] = course.url + path.replace("index.html", "")
    return {"kind": "page", "path": path, "url": link_targets[path], "title": title}


def resource_items(page_paths, added):
    """The documents and videos linked from the pages, in the order they are linked, skipping ones already added"""
    items = []
    for page_path in page_paths:
        for link in course.read_page(page_path).find_all("a", href=True):
            path = course.site_path(link["href"], page_path)
            resource_dir = posixpath.dirname(path) if path else None
            if resource_dir in course.resources and resource_dir not in added:
                added.add(resource_dir)
                item = resource_item(resource_dir)
                if item:
                    items.append(item)
                    if item["kind"] == "video":
                        # the PDFs linked from the video's own page, like the lecture's notes, go after the video
                        items.extend(resource_items([resource_dir + "/index.html"], added))
    return items


def resource_item(resource_dir):
    resource = course.resources[resource_dir]
    title = resource.get("title") or resource_dir.split("/")[-1]
    source_id = course.url + resource_dir + "/"
    if resource.get("resourcetype") == "Video":
        video_files = resource.get("video_files") or {}
        youtube_id = (resource.get("video_metadata") or {}).get("youtube_id")
        if not video_files.get("archive_url") and not youtube_id:
            return None
        captions = [(c.get("language") or "en", course.local_path(course.site_path(c["file"])))
                    for c in video_files.get("video_captions_resources") or [] if c.get("file")]
        link_targets[resource_dir + "/index.html"] = source_id
        # the bigger version of the YouTube thumbnail OCW links to
        thumbnail = (video_files.get("video_thumbnail_file") or "").replace("/default.jpg", "/hqdefault.jpg") or None
        return {"kind": "video", "url": source_id, "title": title, "archive_url": video_files.get("archive_url"),
                "youtube_id": youtube_id, "captions": [c for c in captions if c[1]], "thumbnail": thumbnail}

    file_path = course.site_path(resource["file"]) if resource.get("file") else None
    if file_path in course.transcripts:
        return None
    if resource.get("file_type") == "application/pdf" and course.local_path(file_path):
        link_targets[resource_dir + "/index.html"] = source_id
        link_targets[file_path] = source_id
        return {"kind": "document", "url": source_id, "title": re.sub(r"\.pdf$", "", title, flags=re.I),
                "file": course.local_path(file_path)}
    # images and other files stay in the dependency zip, linked from the pages
    return None


def build_topic(topic):
    topic_node = TopicNode(source_id=topic["children"][0]["url"] + "#topic", title=topic["title"])
    # number repeated titles, e.g. the two demonstrations of impedance matching in 6.002's video lectures
    seen_titles = collections.Counter()
    for item in topic["children"]:
        seen_titles[item["title"]] += 1
        if seen_titles[item["title"]] > 1:
            item = dict(item, title="{} ({})".format(item["title"], seen_titles[item["title"]]))
        if item["kind"] == "page":
            topic_node.add_child(build_page(item))
        elif item["kind"] == "video":
            if item["archive_url"]:
                files = [VideoFile(path=item["archive_url"])]
            else:
                files = [YouTubeVideoFile(youtube_id=item["youtube_id"], language=CHANNEL_LANGUAGE)]
            for language, caption_path in item["captions"]:
                files.append(SubtitleFile(path=caption_path, language=language))
            topic_node.add_child(VideoNode(source_id=item["url"], title=item["title"], license=LICENSE,
                                           copyright_holder=COPYRIGHT_HOLDER, files=files, thumbnail=item["thumbnail"]))
        else:
            topic_node.add_child(DocumentNode(source_id=item["url"], title=item["title"], license=LICENSE,
                                              copyright_holder=COPYRIGHT_HOLDER, files=[DocumentFile(path=item["file"])]))
    return topic_node


# THE PAGES


def download_external_images(page_paths):
    for page_path in set(page_paths):
        for image in course.read_page(page_path).find_all("img", src=re.compile(r"^https?://")):
            local = os.path.join(course.root, course.external_image_path(image["src"]))
            if os.path.exists(local):
                continue
            try:
                response = requests.get(image["src"], timeout=30)
            except requests.RequestException as e:
                LOGGER.warning("Could not download {}: {}".format(image["src"], e))
                continue
            if response.status_code == 200:
                os.makedirs(os.path.dirname(local), exist_ok=True)
                with open(local, "wb") as f:
                    f.write(response.content)

# attributes holding links to other files in the offline site
LINK_ATTRIBUTES = ["href", "src", "data-downloadlink", "data-transcriptlink", "poster"]


def navigation_script(node_id):
    return "window.kolibri.navigateTo('{}'); return false;".format(node_id)


CSS_URL_RE = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""")


def rewrite_page(soup, page_path, dep_file_reference):
    """
    The page is moved to the root of its own zip, so point its links to the rest of the offline site at the dependency
    zip, and once the node ids are known on the second run, make links to other pages, PDFs and videos into navigation
    """
    def rewrite_css(css):
        def replace(match):
            path = course.site_path(match.group(2), page_path)
            if not path or not course.local_path(path):
                return match.group(0)
            return "url({0}{1}{0})".format(match.group(1), dep_file_reference + path)
        return CSS_URL_RE.sub(replace, css)

    # the fonts and icons are in a <style> in each page
    for style in soup.find_all("style"):
        style.string = rewrite_css(style.get_text())
    for tag in soup.find_all(style=True):
        tag["style"] = rewrite_css(tag["style"])

    for image in soup.find_all("img", src=re.compile(r"^https?://")):
        path = course.external_image_path(image["src"])
        if course.local_path(path):
            image["src"] = dep_file_reference + path

    # analytics, which can't work offline
    for tracker in soup.find_all(["iframe", "script"], src=re.compile(r"googletagmanager")):
        (tracker.find_parent("noscript") or tracker).decompose()

    for attribute in LINK_ATTRIBUTES:
        for tag in soup.find_all(attrs={attribute: True}):
            value = tag[attribute]
            if value.startswith(("#", "mailto:", "javascript:", "data:")):
                continue
            path = course.site_path(value, page_path)
            if not path:
                continue
            node_id = orig_urls_to_node_ids.get(link_targets.get(path))
            if tag.name == "a" and attribute == "href" and node_id:
                tag["href"] = "#"
                tag["onclick"] = navigation_script(node_id)
            elif course.local_path(path):
                fragment = urldefrag(value)[1]
                tag[attribute] = dep_file_reference + path + ("#" + fragment if fragment else "")


def build_page(item):
    dep_zip_file = HTMLZipFile(dep_zip, preset=format_presets.HTML5_DEPENDENCY_ZIP)
    dep_file_reference = "/zipcontent/{}.zip/".format(dep_zip_file.checksum)

    soup = course.read_page(item["path"])
    rewrite_page(soup, item["path"], dep_file_reference)

    page_dir = tempfile.mkdtemp()
    with open(os.path.join(page_dir, "index.html"), "wb") as f:
        f.write((str(soup) + cache_invalidator_string).encode("utf-8"))

    return HTML5AppNode(
        source_id=item["url"],
        title=item["title"],
        files=[HTMLZipFile(create_predictable_zip(page_dir)), dep_zip_file],
        license=LICENSE,
        copyright_holder=COPYRIGHT_HOLDER,
    )


if __name__ == "__main__":
    """
    Call this script using:
        ./chef_ocw.py --token=YOURSTUDIOTOKENHERE9139139f3a23232 course=<url of the course on ocw.mit.edu>
    """
    chef = OCWChef()
    chef.main()
    # second run, with the node ids from the first to make links between the nodes
    orig_urls_to_node_ids.update((node.source_id, node.node_id) for node in chef.tree.all_nodes)
    chef.main()
