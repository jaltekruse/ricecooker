#!/usr/bin/env python
"""
Sushichef for CS50x, Harvard's introduction to computer science, https://cs50.harvard.edu/x/

Only CS50x itself is imported, none of the other CS50 courses the site links to. The tree is kept flat, one topic per
week holding the week's page, lecture video, notes, slides, source code, section, shorts and problem set pages.

Videos are imported as their own video nodes, only the English 720p SDR MP4s. Pages are HTML5 apps sharing one
dependency zip, like chef_pretext.py, and like it this runs twice, so that the second run can turn links between pages
and to videos into navigation to the Kolibri nodes, using the node ids from the first run.
"""
import json
import os
import re
import shutil
import sys
import tempfile
from urllib.parse import urldefrag
from urllib.parse import urljoin
from urllib.parse import urlparse

from le_utils.constants import format_presets
from le_utils.constants.labels import levels
from le_utils.constants.labels import subjects

from ricecooker.chefs import SushiChef
from ricecooker.classes import licenses
from ricecooker.classes.files import DocumentFile
from ricecooker.classes.files import HTMLZipFile
from ricecooker.classes.files import SubtitleFile
from ricecooker.classes.files import VideoFile
from ricecooker.classes.nodes import ChannelNode
from ricecooker.classes.nodes import DocumentNode
from ricecooker.classes.nodes import HTML5AppNode
from ricecooker.classes.nodes import TopicNode
from ricecooker.classes.nodes import VideoNode
from ricecooker.config import LOGGER
from ricecooker.utils import downloader
from ricecooker.utils import web
from ricecooker.utils.downloader import archive_page
from ricecooker.utils.zip import create_predictable_zip

# reuse the scraping helpers written for PreTeXt books, e.g. building the shared dependency zip and handling MathJax
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chef_pretext  # noqa: E402
from chef_pretext import archive_path_for_url  # noqa: E402
from chef_pretext import download_mathjax  # noqa: E402
from chef_pretext import download_mathjax_loader_extensions  # noqa: E402
from chef_pretext import download_page_resources  # noqa: E402
from chef_pretext import download_to_archive  # noqa: E402
from chef_pretext import get_parsed_html_from_url  # noqa: E402
from chef_pretext import point_mathjax_at_dependency_zip  # noqa: E402


# CHANNEL SETTINGS
COURSE_URL = "https://cs50.harvard.edu/x/"
SOURCE_ID = "cs50x_harvard"
CHANNEL_TITLE = "CS50x: Introduction to Computer Science"
CHANNEL_LANGUAGE = "en"
COPYRIGHT_HOLDER = "David J. Malan, Harvard University"
LICENSE = licenses.CC_BY_NC_SALicense(copyright_holder=COPYRIGHT_HOLDER)

# the weeks to import, trim this to test with a few
WEEKS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "ai"]
# the course's other pages, as (path, title), in the order they appear in the channel
COURSE_INFO_PAGES = [
    ("syllabus/", "Syllabus"),
    ("faqs/", "FAQs"),
    ("honesty/", "Academic Honesty"),
    ("certificate/", "Certificate"),
    ("staff/", "Staff"),
    ("license/", "License"),
]
FINAL_PROJECT_PAGE = "project/"
PRACTICE_PROBLEMS_PAGE = "practice/"

# the only video files imported, the English 720p SDR MP4s
VIDEO_RESOLUTION = "720p"
# the labels of the lists of videos in other languages, which are skipped
OTHER_LANGUAGE_LABELS = {"Portuguese", "Spanish"}
# the asciinema player, which plays the problems' terminal recordings offline instead of embedding asciinema.org
ASCIINEMA_PLAYER_URL = "https://cdn.jsdelivr.net/npm/asciinema-player@3/dist/bundle/"
ASCIINEMA_PLAYER_FILES = ["asciinema-player.css", "asciinema-player.min.js", "asciinema-player-worker.min.js"]
ASCIINEMA_SCRIPT_RE = re.compile(r"asciinema\.org/a/(\w+)\.js")
# the emoji images the course's theme shows instead of emoji characters, set in its jekyll-theme-cs50.js
TWEMOJI_BASE = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/"
# emoji, optionally followed by a variation selector or skin tone, joined into sequences by zero width joiners, flags
# and keycaps, close enough to what twemoji turns into images
EMOJI_RE = re.compile(
    "(?:[\U0001F1E6-\U0001F1FF]{2}"
    "|[#*0-9]\uFE0F?\u20E3"
    "|[\u2600-\u27BF\u2B00-\u2BFF\U0001F000-\U0001FAFF][\uFE0F\U0001F3FB-\U0001F3FF]?"
    "(?:\u200D[\u2600-\u27BF\U0001F000-\U0001FAFF][\uFE0F\U0001F3FB-\U0001F3FF]?)*)")
# the text of the buttons replacing embedded videos, the theme shows the play symbol as an emoji image too
WATCH_BUTTON_TEXT = "\u25b6 Watch the video"
# how the versions of the problems with the same name are told apart
PROBLEM_VARIANTS = {"less": "Less Comfortable", "more": "More Comfortable"}
# files linked from the pages small enough to include in the dependency zip, everything else stays a link to the web
DEPENDENCY_FILE_EXTENSIONS = {".zip", ".pdf", ".txt", ".srt", ".c", ".h", ".py", ".sql", ".csv", ".html", ".js", ".css"}

# fa.cs50.io, where the site's icons come from, refuses requests that don't come from one of CS50's pages
for session in (downloader.DOWNLOAD_SESSION, chef_pretext.sess):
    session.headers["Referer"] = COURSE_URL

dep_zip = None
# the urls of all of the pages, for building the dependency zip
page_urls = []
# where links on the pages should go, from a url to the source id of the node for it, e.g. the url of a short's page
# and of its video both go to the short's video node
link_targets = {}
# the node ids from the first run, by source id, used to make links into navigation between nodes on the second run
orig_urls_to_node_ids = {}

cache_invalidator_string = "                                                                         "


class CS50xChef(SushiChef):
    def get_channel(self, *args, **kwargs):
        return ChannelNode(
            source_domain=COURSE_URL,
            source_id=SOURCE_ID,
            title=CHANNEL_TITLE,
            description=(
                "Harvard University's introduction to the intellectual enterprises of computer science and the art "
                "of programming, for students with or without prior programming experience."
            ),
            license=LICENSE,
            copyright_holder=COPYRIGHT_HOLDER,
            language=CHANNEL_LANGUAGE,
            provider="CS50, Harvard University",
            categories=[subjects.COMPUTER_SCIENCE],
            grade_levels=[levels.UPPER_SECONDARY, levels.TERTIARY, levels.PROFESSIONAL],
        )

    def construct_channel(self, *args, **kwargs):
        channel = self.get_channel(**kwargs)

        # first work out the whole tree, so that the dependency zip can be built from all of the pages before any of
        # them are created, as the pages need the dependency zip's checksum
        home = page_item(COURSE_URL, "Course Home")
        topics = [week_tree(week) for week in WEEKS]
        topics.append(pages_tree("Final Project", [(FINAL_PROJECT_PAGE, "Final Project")]))
        topics.append(problems_tree("Practice Problems", PRACTICE_PROBLEMS_PAGE))
        topics.append(pages_tree("About the Course", COURSE_INFO_PAGES))

        if dep_zip is None:
            build_dependency_zip()

        channel.add_child(build_page(home["url"], home["title"]))
        for topic in topics:
            channel.add_child(build_topic(topic))
        return channel


# THE TREE
# The tree is first described with plain dicts, {"kind": "page" | "video" | "document", "url": ..., "title": ...},
# grouped into {"title": ..., "children": [...]} topics, then turned into nodes by build_topic


def page_item(url, title):
    url = normalize_url(url)
    page_urls.append(url)
    link_targets[url] = url
    return {"kind": "page", "url": url, "title": title}


def document_item(url, title, *aliases):
    for link in (url, *aliases):
        link_targets[normalize_url(link)] = url
    return {"kind": "document", "url": url, "title": title}


def video_item(video_page_url, title, *aliases):
    """
    The video on a lecture, section or short's page, or None if it doesn't have a 720p SDR MP4. aliases are other
    urls that should link to the video node, like the short's own page
    """
    main = get_parsed_html_from_url(video_page_url).find("main")
    mp4_url = find_video_url(main)
    if not mp4_url:
        LOGGER.warning("No {} SDR video found on {}".format(VIDEO_RESOLUTION, video_page_url))
        return None
    for link in (mp4_url, *aliases, *player_urls(main)):
        link_targets[normalize_url(link)] = mp4_url
    return {"kind": "video", "url": mp4_url, "title": title, "subtitles": find_english_subtitles(main)}


def week_tree(week):
    week_url = urljoin(COURSE_URL, "weeks/{}/".format(week))
    main = get_parsed_html_from_url(week_url).find("main")
    week_title = heading_text(main)

    children = [page_item(week_url, week_title)]
    # e.g. "Lecture 1", and "Lecture: Artificial Intelligence" for the weeks without a number
    children.append(video_item(week_url, "Lecture " + week if week.isdigit() else "Lecture: " + week_title))
    notes = link_with_text(main, "Notes")
    if notes:
        children.append(page_item(urljoin(week_url, notes["href"]), "Notes"))

    slides = list_item_link(main, "Slides", "PDF")
    if slides:
        children.append(document_item(slides, "Slides"))
    source_code = list_item_link(main, "Source Code", "PDF")
    if source_code:
        # the source code's directory listing goes to the PDF of the source code as well
        children.append(document_item(source_code, "Source Code", list_item_link(main, "Source Code", "Index")))

    section = link_with_text(main, "Section")
    if section:
        section_url = urljoin(week_url, section["href"])
        children.append(video_item(section_url, "Section", section_url))

    shorts = list_item(main, "Shorts")
    for short in shorts.find_all("a", href=True) if shorts else []:
        short_url = urljoin(week_url, short["href"])
        children.append(video_item(short_url, "Short: " + short.get_text(strip=True), short_url))

    problem_set = main.find("a", href=True, string=re.compile(r"^Problem Set"))
    if problem_set:
        children.extend(problems_tree(problem_set.get_text(strip=True), urljoin(week_url, problem_set["href"]))["children"])

    return {"title": week_title, "children": [child for child in children if child]}


def problems_tree(title, index_url):
    """A page listing problems, like a problem set, followed by each of the problems' pages"""
    index_url = normalize_url(urljoin(COURSE_URL, index_url))
    main = get_parsed_html_from_url(index_url).find("main")
    problems = {}
    for link in main.find_all("a", href=True):
        problem_url = normalize_url(urljoin(index_url, link["href"]))
        # the problems' pages are the ones under the index page
        if problem_url.startswith(index_url) and problem_url != index_url and problem_url not in problems:
            problems[problem_url] = heading_text(get_parsed_html_from_url(problem_url).find("main")) or link.get_text(strip=True)

    children = [page_item(index_url, title)]
    titles = list(problems.values())
    for problem_url, problem_title in problems.items():
        if titles.count(problem_title) > 1:
            # problems with versions for the less and more comfortable, e.g. mario/less/ and mario/more/
            variant = problem_url.rstrip("/").split("/")[-1]
            problem_title += " ({})".format(PROBLEM_VARIANTS.get(variant, variant))
        children.append(page_item(problem_url, problem_title))
    return {"title": title, "children": children}


def pages_tree(title, pages):
    return {"title": title, "children": [page_item(urljoin(COURSE_URL, path), page_title) for path, page_title in pages]}


def build_topic(topic):
    topic_node = TopicNode(source_id=topic["children"][0]["url"] + "#topic", title=topic["title"])
    for item in topic["children"]:
        if item["kind"] == "page":
            topic_node.add_child(build_page(item["url"], item["title"]))
        elif item["kind"] == "video":
            files = [VideoFile(path=item["url"])]
            if item["subtitles"]:
                files.append(SubtitleFile(path=item["subtitles"], language="en", subtitlesformat="srt"))
            topic_node.add_child(VideoNode(source_id=item["url"], title=item["title"], license=LICENSE,
                                           copyright_holder=COPYRIGHT_HOLDER, files=files))
        else:
            topic_node.add_child(DocumentNode(source_id=item["url"], title=item["title"], license=LICENSE,
                                              copyright_holder=COPYRIGHT_HOLDER, files=[DocumentFile(path=item["url"])]))
    return topic_node


# PARSING THE PAGES


def normalize_url(url):
    """drop the fragment, and add the / the site's pages are linked with, so the same page is always the same url"""
    url = urldefrag(url)[0]
    if url == COURSE_URL.rstrip("/"):
        return COURSE_URL
    path = urlparse(url).path
    if url.startswith(COURSE_URL) and not path.endswith("/") and not os.path.splitext(path)[1]:
        url += "/"
    return url


def heading_text(main):
    """The page's heading, e.g. "Week 1: C" for <h1>Week 1 <em>C</em></h1>"""
    heading = main.find("h1") if main else None
    if not heading:
        return ""
    emphasis = heading.find("em")
    if emphasis:
        prefix = heading.get_text(" ", strip=True).replace(emphasis.get_text(strip=True), "").strip()
        return "{}: {}".format(prefix, emphasis.get_text(strip=True)) if prefix else emphasis.get_text(strip=True)
    return heading.get_text(" ", strip=True)


def list_item(root, label):
    """The <li> in one of the site's nested lists of links that starts with label, e.g. <li>Slides <ul>...</ul></li>"""
    for item in root.find_all("li"):
        text = item.find(string=True, recursive=False)
        if text and text.strip() == label:
            return item
    return None


def list_item_link(root, label, link_text):
    """The url of the link with link_text in the list item labeled label, e.g. the PDF under Slides"""
    item = list_item(root, label)
    link = item.find("a", href=True, string=link_text) if item else None
    return link["href"] if link else None


def link_with_text(root, text):
    return root.find("a", href=True, string=text)


def labels_of_ancestors(node):
    labels = set()
    for item in node.find_parents("li"):
        text = item.find(string=True, recursive=False)
        if text:
            labels.add(text.strip())
    return labels


def find_video_url(main):
    """
    The English 720p SDR MP4 on a page. Lectures list each language's video in HDR and SDR, shorts and sections only
    have SDR. The shorts' links end in .mp4.download, which redirects to a signed S3 url, the CDN serves the .mp4 itself
    """
    for link in main.find_all("a", href=True, string=VIDEO_RESOLUTION):
        labels = labels_of_ancestors(link)
        if "HDR" in labels or labels & OTHER_LANGUAGE_LABELS:
            continue
        url = re.sub(r"\.download$", "", link["href"])
        if url.endswith(".mp4"):
            return url
    return None


def find_english_subtitles(main):
    for link in main.find_all("a", href=re.compile(r"\.srt$")):
        if "/lang/en/" in link["href"]:
            return link["href"]
    return None


def player_urls(main):
    """The urls of the other places a page's video is linked to, CS50's video player and YouTube"""
    urls = [frame["src"] for frame in main.find_all("iframe", src=re.compile(r"video\.cs50\.io"))]
    for link in main.find_all("a", href=re.compile(r"(video\.cs50\.io|youtu\.be|youtube\.com)")):
        if not labels_of_ancestors(link) & OTHER_LANGUAGE_LABELS:
            urls.append(link["href"])
    return urls


# THE DEPENDENCY ZIP AND PAGES


def build_dependency_zip():
    """
    Build the dependency zip shared by all of the pages, with the css, js, images and MathJax they use, and the small
    files they link to, like the lectures' source code zips
    """
    destpath = tempfile.mkdtemp()
    scanned_scripts = set()
    downloaded_resource_urls = set()
    for url in dict.fromkeys(page_urls):
        page = get_parsed_html_from_url(url)
        for script in page.find_all("script", src=True):
            script_url = urljoin(url, script["src"])
            if script_url not in scanned_scripts:
                scanned_scripts.add(script_url)
                download_mathjax(script_url, page, url, destpath)
        download_mathjax_loader_extensions(page, url, destpath)

        for link in page.find_all("a", href=True):
            file_url = urldefrag(urljoin(url, link["href"]))[0]
            if is_dependency_file(file_url) and file_url not in link_targets:
                download_to_archive(file_url, destpath)

        for emoji in set(EMOJI_RE.findall(page.get_text() + WATCH_BUTTON_TEXT)):
            download_to_archive(TWEMOJI_BASE + "72x72/" + twemoji_name(emoji) + ".png", destpath)

        for script in page.find_all("script", src=ASCIINEMA_SCRIPT_RE):
            recording = ASCIINEMA_SCRIPT_RE.search(script["src"]).group(1)
            download_to_archive("https://asciinema.org/a/{}.cast".format(recording), destpath)

        # this removes resources from the parsed page, so it needs to be done last
        download_page_resources(page, url, destpath, downloaded_resource_urls)

    for name in ASCIINEMA_PLAYER_FILES:
        download_to_archive(ASCIINEMA_PLAYER_URL + name, destpath)
    point_theme_at_local_emoji(destpath)

    with open(os.path.join(destpath, "index.html"), "wb") as f:
        f.write(("<html><body>This is the dependency zip</body></html>" + cache_invalidator_string).encode("utf-8"))

    global dep_zip
    dep_zip = create_predictable_zip(destpath)


def twemoji_name(emoji):
    """The name twemoji gives an emoji's image, its code points in hex, without variation selectors unless it's a
    sequence joined by zero width joiners"""
    if "\u200d" not in emoji:
        emoji = emoji.replace("\ufe0f", "")
    return "-".join("{:x}".format(ord(c)) for c in emoji)


def point_theme_at_local_emoji(destpath):
    """
    The course's theme script has twemoji load the emoji images from jsDelivr, have it load the ones downloaded into
    the dependency zip instead, relative to where the theme script is
    """
    for root, _, files in os.walk(destpath):
        for name in files:
            if name.startswith("jekyll-theme-cs50") and name.endswith(".js"):
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as f:
                    js = f.read()
                local_base = os.path.relpath(os.path.join(destpath, archive_path_for_url(TWEMOJI_BASE)), root) + "/"
                patched = js.replace("base: '{}'".format(TWEMOJI_BASE), "base: CS50_THEME_DIR + '{}'".format(local_base))
                if patched != js:
                    # the directory the script was loaded from, which is only known while it first runs
                    patched = ("var CS50_THEME_DIR = document.currentScript.src.replace(/[^\\/]*$/, '');\n"
                               + patched)
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(patched)


def is_dependency_file(url):
    parsed = urlparse(url)
    return parsed.netloc == "cdn.cs50.net" and os.path.splitext(parsed.path)[1].lower() in DEPENDENCY_FILE_EXTENSIONS


def navigation_script(node_id):
    return "window.kolibri.navigateTo('{}'); return false;".format(node_id)


def rewrite_links(soup, page_url, dep_file_reference):
    """
    Turn links to other pages and to videos into navigation to their Kolibri nodes, once the node ids are known on the
    second run, and point links to files included in the dependency zip at it
    """
    for link in soup.find_all("a", href=True):
        url = normalize_url(urljoin(page_url, link["href"]))
        node_id = orig_urls_to_node_ids.get(link_targets.get(url))
        if node_id:
            link["href"] = "#"
            link["onclick"] = navigation_script(node_id)
        elif is_dependency_file(url):
            link["href"] = dep_file_reference + archive_path_for_url(url)


def replace_embedded_videos(soup, page_url):
    """
    Replace embedded video players with a button that goes to the video's node, or for the videos only on YouTube,
    like the problems' walkthroughs, a link to it
    """
    for frame in soup.find_all("iframe", src=True):
        src = frame["src"].replace("&amp;", "&")
        node_id = orig_urls_to_node_ids.get(link_targets.get(normalize_url(src)))
        youtube = re.search(r"(?:youtube\.com/embed/|youtu\.be/|video\.cs50\.io/)([\w-]{11})", src)
        if node_id:
            button = soup.new_tag("button", attrs={"onclick": navigation_script(node_id), "class": "btn btn-primary"})
            button.string = WATCH_BUTTON_TEXT
            frame.replace_with(button)
        elif youtube and "video.cs50.io" not in src:
            paragraph = soup.new_tag("p")
            link = soup.new_tag("a", href="https://www.youtube.com/watch?v=" + youtube.group(1), target="_blank")
            link.string = "Watch this video on YouTube (requires an internet connection)"
            paragraph.append(link)
            frame.replace_with(paragraph)


def replace_asciinema_embeds(soup, dep_file_reference):
    """
    The problems' terminal recordings are embedded with asciinema.org's script, which plays them in an iframe from
    asciinema.org. Play the recordings downloaded into the dependency zip with the asciinema player instead
    """
    embeds = [s for s in soup.find_all("script", src=True) if ASCIINEMA_SCRIPT_RE.search(s["src"])]
    if not embeds:
        return
    player = dep_file_reference + archive_path_for_url(ASCIINEMA_PLAYER_URL)
    head = soup.head or soup
    head.append(soup.new_tag("link", rel="stylesheet", href=player + "asciinema-player.css"))
    head.append(soup.new_tag("script", src=player + "asciinema-player.min.js"))
    for embed in embeds:
        recording = ASCIINEMA_SCRIPT_RE.search(embed["src"]).group(1)
        options = {"autoPlay": embed.get("data-autoplay") == "1", "loop": embed.get("data-loop") == "1"}
        for attribute, option in (("data-cols", "cols"), ("data-rows", "rows"), ("data-speed", "speed")):
            if embed.get(attribute):
                options[option] = float(embed[attribute]) if option == "speed" else int(embed[attribute])
        container = soup.new_tag("div", id="asciicast-" + recording)
        script = soup.new_tag("script")
        script.string = "AsciinemaPlayer.create({}, document.getElementById({}), {});".format(
            json.dumps(dep_file_reference + "asciinema.org/a/{}.cast".format(recording)),
            json.dumps("asciicast-" + recording), json.dumps(options))
        embed.replace_with(container)
        container.insert_after(script)


def build_page(url, title):
    destpath = tempfile.mkdtemp()
    index_path = os.path.join(destpath, "index.html")
    dep_zip_file = HTMLZipFile(dep_zip, preset=format_presets.HTML5_DEPENDENCY_ZIP)
    dep_file_reference = "/zipcontent/{}.zip/".format(dep_zip_file.checksum)

    def final_link_replacement(soup):
        parser = web.HTMLParser(index_path)
        # archive_page rewrote the page's resources to where they are in the dependency zip, relative to the page
        links_to_replace = {
            link: dep_file_reference + link[2:]
            for link in parser.get_links_in_parsed(soup, index_path) if link.startswith("./")
        }
        replace_embedded_videos(soup, url)
        replace_asciinema_embeds(soup, dep_file_reference)
        rewrite_links(soup, url, dep_file_reference)
        point_mathjax_at_dependency_zip(soup, dep_file_reference)
        return parser.replace_links_in_parsed(links_to_replace, soup, index_path)

    archive_page(url, destpath, skip_static_asset_download=True, final_link_replacement=final_link_replacement)
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    # only the index.html goes in the page's zip, everything else is in the dependency zip
    page_dir = tempfile.mkdtemp()
    with open(os.path.join(page_dir, "index.html"), "wb") as f:
        f.write((html + cache_invalidator_string).encode("utf-8"))
    shutil.rmtree(destpath)

    return HTML5AppNode(
        source_id=url,
        title=title,
        files=[HTMLZipFile(create_predictable_zip(page_dir)), dep_zip_file],
        license=LICENSE,
        copyright_holder=COPYRIGHT_HOLDER,
    )


if __name__ == "__main__":
    """
    Call this script using:
        ./chef_cs50.py --token=YOURSTUDIOTOKENHERE9139139f3a23232
    """
    chef = CS50xChef()
    chef.main()
    # second run, with the node ids from the first to make links between the nodes
    orig_urls_to_node_ids.update((node.source_id, node.node_id) for node in chef.tree.all_nodes)
    page_urls.clear()
    chef.main()
