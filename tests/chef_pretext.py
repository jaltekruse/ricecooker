#!/usr/bin/env python
import base64
import concurrent.futures
import hashlib
import os
import posixpath
import re
import tempfile
from urllib.parse import quote
from urllib.parse import urldefrag
from urllib.parse import urljoin
from urllib.parse import urlparse

import shutil

import le_utils
import requests
from bs4 import BeautifulSoup

from ricecooker.chefs import SushiChef
from ricecooker.classes import licenses
from ricecooker.classes.files import HTMLZipFile, VideoFile, WebVideoFile, YouTubeVideoFile
from ricecooker.classes.nodes import ChannelNode, VideoNode
from ricecooker.classes.nodes import HTML5AppNode
from ricecooker.classes.nodes import TopicNode
from ricecooker.config import LOGGER
from ricecooker.utils.caching import CacheControlAdapter
from ricecooker.utils.caching import CacheForeverHeuristic
from ricecooker.utils.caching import FileCache
from ricecooker.utils.downloader import archive_page
from ricecooker.utils.html import download_file
from ricecooker.utils import downloader, web

from ricecooker.utils.zip import create_predictable_zip
from le_utils.constants import file_formats, format_presets

from le_utils.constants.labels import accessibility_categories
from le_utils.constants.labels import learning_activities
from le_utils.constants.labels import levels
from le_utils.constants.labels import needs
from le_utils.constants.labels import resource_type
from le_utils.constants.labels import subjects


# CHANNEL SETTINGS
SOURCE_DOMAIN = "https://runestone.academy/ns/books/published/FOPP-PIE/ThinkLikeComputer.html"
# SOURCE_ID = "thinkcspi_runestone_academy"  # an alphanumeric ID refering to this channel
# CHANNEL_TITLE = "How to Think Like a Computer Scientist, Interactive Edition"  # a humand-readbale title
SOURCE_ID = "thinkcspy_runestone_academy"  # an alphanumeric ID refering to this channel
CHANNEL_TITLE = "How to Think Like a Computer Scientist, Interactive Edition"  # a humand-readbale title

copyright = "Brad Miller, David Ranum, Jeffrey Elkner, Peter Wentworth, Allen B. Downey, Chris Meyers, and Dario Mitchell."
license = licenses.SpecialPermissionsLicense(
                    description="GNU Free Documentation License - Version 1.3",
                    copyright_holder=copyright)
license_description="GNU Free Documentation License - Version 1.3"

# youtube ids {'SGVgAV0v-Ww', 'Yxyx6KpKRzY', 'aqhREpceEMI', '3WgmLIsXFkI', '57dPVbnRouU', 'YK8QlIT3__M', 'xGSfiZt5cdw',
# 'GCLHuPBtLdQ', 'Fd4a8ktQURc', 'blTBEqybQmQ', 'vNfCfowr-pQ', 'HriDtn-0Dcw', 'LD-F4RODy-I', '1uQM-TVlaMo', 'LZ7H1X8ar9E',
# 'Ezve3QJv6Aw', 'Px1c-3GP-5o', '2KYixkCBXSQ', '4wKtB57J5J4', 'G86akhNFHZA'}

#SOURCE_ID = "jason_pretext_test_new_id"  # an alphanumeric ID refering to this channel
#CHANNEL_TITLE = "Jason PreteXt testing"
BOOK_PORT = 8080
CHANNEL_LANGUAGE = "en"  # language of channel
DOMAIN = f"http://localhost:{BOOK_PORT}/"
# directory the book's html pages are served from, this can point at a book hosted online like
# "https://runestone.academy/ns/books/published/thinkcspy/", it must end with a /
BOOK_BASE_URL = DOMAIN
# page in the book with the full table of contents
TOC_PAGE = "thinkcspy-3.html"
# only import sub-chapters whose number contains this string, set to None to import the whole book
SUBCHAPTER_FILTER = None
CHAPTER_FILTER = "Front Matter"
VIDEO_DIR = "/home/jason/scraping_sites/aYoutubeVidsForKolibri"


sess = requests.Session()
cache = FileCache(".webcache")
basic_adapter = CacheControlAdapter(cache=cache)
forever_adapter = CacheControlAdapter(heuristic=CacheForeverHeuristic(), cache=cache)

sess.mount("http://", forever_adapter)
sess.mount("https://", forever_adapter)

dep_zip = None

cache_invalidator_string = "                                                                         "

orig_urls_to_node_ids = {}

youtube_codes = []

def make_fully_qualified_url(url):
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://en.wikipedia.org" + url
    if not url.startswith("http"):
        LOGGER.warning("Skipping bad URL (relative to unknown location): " + url)
        return None
    return url


def make_request(url, *args, **kwargs):
    response = sess.get(url, *args, **kwargs)
    #print("JASON DEBUG")
    #print(response.status_code)
    if response.status_code != 200:
        #print(response.text)
        LOGGER.warning("URL NOT FOUND: " + url)
    elif not response.from_cache:
        LOGGER.warning("NOT CACHED: " + url)
    return response

def try_request(url, *args, **kwargs):
    """make_request, but returning None when the host can't be reached rather than raising"""
    try:
        return make_request(url, *args, **kwargs)
    except requests.RequestException as e:
        LOGGER.warning("Could not download {}: {}".format(url, e))
        return None


def parse_html(html):
    return BeautifulSoup(html, features="html.parser", preserve_whitespace_tags=web.PRESERVE_WHITESPACE_TAGS)

def get_parsed_html_from_url(url, *args, **kwargs):
    html = make_request(url, *args, **kwargs).content
    return parse_html(html)


class WikipediaChef(SushiChef):
    def get_channel(self, *args, **kwargs):

        channel = ChannelNode(
            source_domain=SOURCE_DOMAIN,
            source_id=SOURCE_ID,
            title=CHANNEL_TITLE,
            description=
                ("A concise introduction to software design using the Python programming language. "
                "Intended for people with no programming experience, this book starts with the most "
                "basic concepts and gradually adds new material."),
            thumbnail="https://python.camden.rutgers.edu/python_resources/python3_book/_images/gasp_lessons.png",
            license=license,
            author=copyright,
            copyright_holder=copyright,
            license_description=license_description,
            language=CHANNEL_LANGUAGE,
            provider="Runestone Academy",
            categories=[subjects.COMPUTER_SCIENCE],
            grade_levels=[
                levels.LOWER_SECONDARY,
                levels.UPPER_SECONDARY,
                levels.PROFESSIONAL,
                levels.TERTIARY
            ]
        )

        return channel

    def construct_channel(self, *args, **kwargs):

        channel = self.get_channel(**kwargs)
        add_subpages_from_pretext_toc(
            channel, BOOK_BASE_URL + TOC_PAGE
        )

        # potato_topic = TopicNode(
        #     source_id="List_of_potato_cultivars", title="Potatoes!"
        # )
        # channel.add_child(potato_topic)
        # add_subpages_from_wikipedia_list(
        #     potato_topic, "https://en.wikipedia.org/wiki/List_of_potato_cultivars"
        # )

        # avoid channel upload
        # raise "exit early please"

        return channel


def add_subpages_from_pretext_toc(channel, list_url):

    # to understand how the following parsing works, look at:
    #   1. the source of the page (e.g. https://en.wikipedia.org/wiki/List_of_citrus_fruits), or inspect in chrome dev tools
    #   2. the documentation for BeautifulSoup version 4: https://www.crummy.com/software/BeautifulSoup/bs4/doc/

    # parse the the page into BeautifulSoup format, so we can loop through and manipulate it
    page = get_parsed_html_from_url(list_url)

    # extract the main table from the page
    table = page.find(id="ptx-toc")

    #print(list(table.children)[0].find_all("li", recursive=False))
    # print(table.find_all("li"))
    # first walk the table of contents to find all of the pages to include, so that the shared dependency zip can be
    # built from all of them before any of the pages are created, as the pages need the dependency zip's checksum
    chapters = []
    for chapter in list(table.children)[0].find_all("li", recursive=False):

        chapter_href, chapter_number, chapter_title = toc_entry(chapter)
        chapter_summary_url = urljoin(list_url, chapter_href)

        sub_chapters = []
        if CHAPTER_FILTER is None or CHAPTER_FILTER in chapter_title:
            for sub_chapter in list(chapter.find_all("ul", recursive=False))[0].find_all("li", recursive=False):
                sub_chap_href, sub_chap_number, sub_chap_title = toc_entry(sub_chapter)

                if SUBCHAPTER_FILTER is None or SUBCHAPTER_FILTER in sub_chap_title:
                    sub_chap_url = urljoin(list_url, sub_chap_href)
                    sub_chapters.append((sub_chap_url, sub_chap_title, sub_chap_number))

        if sub_chapters:
            chapters.append((chapter_href, chapter_summary_url, chapter_title, sub_chapters))

    if dep_zip is None:
        all_page_urls = []
        for _, chapter_summary_url, _, sub_chapters in chapters:
            all_page_urls.append(chapter_summary_url)
            all_page_urls.extend(sub_chap[0] for sub_chap in sub_chapters)
        download_depedency_zip_files(all_page_urls)

    for chapter_source_id, chapter_summary_url, chapter_title, sub_chapters in chapters:
        chapter_topic = TopicNode(source_id=chapter_source_id, title=chapter_title)

        # add a page for the chapter overview, to give us a place to link to for that entry in the table of contents
        chapter_html5app = download_book_page(chapter_summary_url, thumbnail=None, title=chapter_title, sub_chap_number=sub_chapters[0][2])
        chapter_topic.add_child(chapter_html5app[0])

        for sub_chap_url, sub_chap_title, sub_chap_number in sub_chapters:
            html5app = download_book_page(sub_chap_url, thumbnail=None, title=sub_chap_title, sub_chap_number=sub_chap_number)
            chapter_topic.add_child(html5app[0])

            for extra in html5app[1]:
                chapter_topic.add_child(extra)

        channel.add_child(chapter_topic)

    return None


def toc_entry(item):
    """
    (href, number, title) for an entry in the table of contents, e.g. ("general-intro_algorithms.html", "1.2",
    "1.2 - Algorithms"). Front matter, and some of the back matter like the index, have no number, e.g.
    <a href="..."><span class="title">Preface</span></a>, so their title is just "Preface".

    find() only searches inside the entry, unlike findNext(), which keeps going into the entries after it
    """
    # the entry's own link comes before the links of the entries nested in it
    link = item.find("a")
    number = link.find("span", class_="codenumber")
    number = number.get_text(strip=True) if number else ""
    title = link.find("span", class_="title").get_text(strip=True)
    return link["href"], number, "{} - {}".format(number, title) if number else title


def find_file_matching_pattern(root_directory, regex_pattern):
    compiled_regex = re.compile(regex_pattern)

    # os.walk travels through all subdirectories automatically
    for root, dirs, files in os.walk(root_directory):
        for filename in files:
            if compiled_regex.search(filename):
                # Construct the relative path to the file
                full_path = os.path.join(root, filename)
                return full_path 

def download_book_page(url, thumbnail, title, sub_chap_number):
    destpath = tempfile.mkdtemp()
    extra_content = []

    index_path = destpath + "/index.html"
    global dep_zip
    dep_zip_file = None
    #dep_zip_file.preset = le_utils.constants.format_presets.HTML5_DEPENDENCY_ZIP
    #print("JASON DEBUG - #$%@#!$^#$%^^@#$%&^#$%%@$#%@#%$#@%@#$%@#$%@#$%@#$%@#$%@#$%@#$%#&&^(*(")
    #print(dep_zip_file.preset)

    dep_file_reference = ''
    assets_ref = './'
    pie_ref = '../../PIE/'

    def replace_links(soup):
        nonlocal dep_zip_file, dep_file_reference

        parser = web.HTMLParser(index_path)

        local_links = parser.get_links_in_parsed(soup, index_path)
        links_to_replace = {}

        global dep_zip
        dep_zip_file = HTMLZipFile(dep_zip, preset=format_presets.HTML5_DEPENDENCY_ZIP)
        #dep_zip_file.preset = le_utils.constants.format_presets.HTML5_DEPENDENCY_ZIP
        #print("JASON DEBUG - #$%@#!$^#$%^^@#$%&^#$%%@$#%@#%$#@%@#$%@#$%@#$%@#$%@#$%@#$%@#$%#&&^(*(")
        #print(dep_zip_file.preset)

        dep_file_reference = '/zipcontent/{}.zip/'.format(dep_zip_file.checksum)

        for link in local_links:
            # if pie_ref in link:
                # content_info['needs_dep_zip'] = True
                # dep_zip_pie_ref = '{}/PIE/'.format(os.path.basename(dep_zip))
                # links_to_replace[pie_ref] = dep_zip_pie_ref
            if link.startswith(assets_ref):
                # content_info['needs_dep_zip'] = True
                dep_zip_assets_ref = dep_file_reference + link[2:]
                links_to_replace[link] = dep_zip_assets_ref

            # find and patch any Three.js references in the sources that are not part of the PIE package.
            # elif 'three.js' in link.lower() or 'three.min.js' in link.lower():
            #     # print("Three.js link found: {}".format(link))
            #     full_path = os.path.join(os.path.dirname(html_file_path), link)
            #     if os.path.exists(full_path):
            #         self.patch_three_js(full_path)


        page = soup
        all_videos = page.find_all("iframe", class_="video")
        if (all_videos):

            all_video_boxes = page.find_all("div", class_="video-box")
            for video_box_div in all_video_boxes:
                video_box_div['style'] = ""

            for video in all_videos:
                # preset must be set if preset and default_preset isn't specified when creating WebVideoFile object for file 44543976d529bb1a7bdbe99fdcbddab3.html (simple-python-data_variables.html)

                # https://www.youtube-nocookie.com/embed/LZ7H1X8ar9E?&amp;modestbranding=1&amp;rel=0
                video_id = re.search(r".*embed/(.*)\?.*", video.attrs['src']).group(1)
                regular_youtube_url = "https://www.youtube.com/watch?v=" + video_id
                #the tool I used to download the videos I guess decided to replace double underscores in video IDs with single underscores?
                video_id_modified = video_id.replace("__", "_")
                video_file = find_file_matching_pattern(VIDEO_DIR, f".*{video_id_modified}.*")
                video_title = f"Video - {sub_chap_number} - " + re.search(r".*YouTube_(.*)_Media_.*", video_file).group(1)
                wvf = VideoFile(path=video_file, preset=format_presets.VIDEO_LOW_RES, source_url=regular_youtube_url)
                node = VideoNode(source_id=video_id, title=video_title, 
                                license=license,
                                copyright_holder=copyright,
                                license_description=license_description,
                                files=[wvf])
                extra_content.append(node)
                # if we are on the second pass and have nodeIDs from uploading the first time
                # replace the youtube embedd with a link to the video in the Kolibri tree
                if (orig_urls_to_node_ids):
                    on_click = f"window.kolibri.navigateTo('{orig_urls_to_node_ids[video_id]}')"
                    new_video_link = page.new_tag("button", attrs={"onClick": 
                                on_click})
                    new_video_link.string = video_title
                    video_placeholder_img = page.new_tag("img", attrs={
                        "src": dep_file_reference + "video_placeholder.png", "onClick": on_click,
                        "style": "max-width:100%"})
                    video.insert_before(video_placeholder_img)
                    video.insert_before(page.new_tag("br"))
                    video.replace_with(new_video_link)
            
            print(extra_content)

        # knowls are html snippets that are lazily loaded when clicked on, find them now while we have the parsed page
        knowls.update(fetch_knowls(soup, url))

        point_mathjax_at_dependency_zip(soup, dep_file_reference)

        return parser.replace_links_in_parsed(links_to_replace, soup, index_path)

    knowls = {}
    archive_page(url, destpath, skip_static_asset_download=True, final_link_replacement=replace_links)
    #archive_page(url, destpath)

    # mathjax_dest = destpath + "/cdn.jsdelivr.net/npm/mathjax@3/"
    # shutil.rmtree(mathjax_dest + "es5")
    # shutil.copytree("/home/jason/src/MathJax/es5", mathjax_dest + "/es5")

    
    with open(index_path, 'r', encoding='utf-8') as file:
        new_html = file.read()

    # TODO Jason - very hack just trying to get pretext working
    # this is for custom data attributes on some tags that are interpreted as URLs by PreteXt javascript
    new_html = new_html.replace("\"_static", "\"" + dep_file_reference + archive_path_for_url(urljoin(url, "_static")))

    new_html = replace_links_to_other_pages(new_html)
        
 
    # other URLs above
    # TODO - use beautifulSoup to parse the page and replace the youtube embed with something, a link, maybe a generic
    # image that looks like a video with a play button, that will link to the resource for each video.

    # will also need to upload the video as a resource, and put the link in the doc on the second pass, as is done with
    # other URLs above

    page_youtube_codes = re.findall(r"youtube.*/embed/(.*)\?", new_html)
    youtube_codes.extend(page_youtube_codes)
    #print(new_html)

    # new_html = page

    # isolate the index.html it it's own folder, all resources should now be coming out of the dep zip
    new_dest = destpath + "/PRETEXT_INDEX_ALONE_" + os.path.basename(destpath)
    os.makedirs(new_dest, exist_ok=True)

    global cache_invalidator_string
    # the knowls get inserted into this page when they are opened, so they are stored next to the index.html at the
    # same relative paths as the data-knowl attributes, with the resources they reference pointed at the dependency zip
    for knowl_path, knowl_html in knowls.items():
        knowl_dest = os.path.join(new_dest, knowl_path)
        os.makedirs(os.path.dirname(knowl_dest), exist_ok=True)
        with open(knowl_dest, "wb") as knowl_file:
            knowl_file.write(rewrite_knowl_for_page(knowl_html, url, dep_file_reference).encode("utf-8"))

    f = open(new_dest + "/index.html", "wb")
    f.write((new_html + cache_invalidator_string).encode("utf-8"))
    f.close()

    # turn the temp folder into a zip file
    zippath = create_predictable_zip(new_dest)

    # create an HTML5 app node
    html5app = HTML5AppNode(
        files=[HTMLZipFile(zippath), dep_zip_file],
        title=title,
        thumbnail=thumbnail,
        source_id=url.split("/")[-1],
        # getting a weird failure when I try to set a license
        # ricecooker.exceptions.InvalidNodeException: 2 - Euclidean Vectors (EV) (HTML5AppNode): 1 file: License is not a license object
        # in the debugger I'm confused, __bases__ shows this license object inherits from
        # (<class 'ricecooker.classes.licenses.License'>,), which appears to be the class it is checking for? but isinstance returns false
        # TODO JASON - seems like this assertion needs updating, it complains even if I have this, need to put it in the license itself below
        license=license,
        copyright_holder=copyright,
        license_description=license_description
    )

    # return a tuple, first element is the main section ot add, the second element of the tuple is another tuple with
    # a series of supplemntary resources that should be added to the same parent, but at the end of all of the regular sections
    # TODO - determine if having them in-order after the section is right, I think creating a no-leaf node for pages is likely
    # the wrong design
    return (html5app, extra_content)
    #return html5app

def download_depedency_zip_files(page_urls):
    """
    Build the dependency zip shared by all of the pages, containing the static resources referenced directly in the
    pages, as well as the ones PreTeXt and Runestone load lazily at runtime. Everything is found by parsing the pages
    and resources themselves, as servers hosting books generally don't allow directory listings.
    """

    # create a temp directory to house our downloaded files
    destpath = tempfile.mkdtemp()

    scanned_scripts = set()
    downloaded_resource_urls = set()
    for url in page_urls:
        page = get_parsed_html_from_url(url)

        # knowls are the html snippets loaded when expanding things like cross references. They are stored with
        # each page, but the resources they reference go in this zip
        for knowl_html in fetch_knowls(page, url).values():
            download_knowl_resources(knowl_html, url, destpath)

        for script in page.find_all("script", src=True):
            script_url = urljoin(url, script["src"])
            if script_url in scanned_scripts:
                continue
            scanned_scripts.add(script_url)
            if not download_mathjax(script_url, page, url, destpath):
                download_webpack_lazy_chunks(script_url, destpath)

        download_mathjax_loader_extensions(page, url, destpath)

        # this removes resources from the parsed page, so it needs to be done last
        download_page_resources(page, url, destpath, downloaded_resource_urls)

    shutil.copy(os.path.join(VIDEO_DIR, "video_placeholder.png"), destpath)

    f = open(destpath + "/index.html", "wb")
    global cache_invalidator_string
    f.write(("<html><body>This is the depedency zip</body></html>" + cache_invalidator_string).encode("utf-8"))
    f.close()
    # turn the temp folder into a zip file
    zippath = create_predictable_zip(destpath)

    global dep_zip
    dep_zip = zippath
    return None


# tags and attributes for the resources referenced directly in a page that download_static_assets downloads
PAGE_RESOURCE_ATTRS = {"img": "src", "link": "href", "script": "src", "source": "src"}


def download_page_resources(page, page_url, archive_dir, downloaded_resource_urls):
    """
    Download everything directly referenced by a parsed page (css, js, images, etc.) into archive_dir, laid out by
    domain and path the same way archive_page does, e.g. localhost:8081/_static/pretext/js/pretext.js

    Resources already downloaded for an earlier page are removed from the page first, so the many resources shared
    between pages are only processed once. This also matters for correctness, download_static_assets re-processes
    css files it finds already downloaded, which breaks the links it rewrote in them the first time.
    """
    for tag, attr in PAGE_RESOURCE_ATTRS.items():
        for node in page.find_all(tag, attrs={attr: True}):
            resource_url = urljoin(page_url, node[attr])
            if resource_url in downloaded_resource_urls:
                node.decompose()
            else:
                downloaded_resource_urls.add(resource_url)

    resource_urls = {}

    def get_resource_filename(url, destination):
        return downloader.get_archive_filename(url, destination, page_url, archive_dir, resource_urls)

    downloader.download_static_assets(page, archive_dir, urljoin(page_url, "."),
                                      derive_filename=get_resource_filename, resource_urls=resource_urls)


def archive_path_for_url(url):
    """
    The path a resource is stored at inside an archive_page download folder, which is the domain followed by the path
    of the URL (see get_archive_filename in ricecooker.utils.downloader)
    """
    parsed = urlparse(url)
    return parsed.netloc + parsed.path


def download_to_archive(url, archive_dir, source_urls=None):
    """
    Download a single resource into archive_dir at the same location archive_page would put it, returns the content
    of the resource, or None if it couldn't be downloaded

    source_urls are the places to try downloading the content from, in order, when it should come from somewhere
    other than url itself, the location the page will request it from
    """
    url = urldefrag(url)[0]
    if urlparse(url).scheme not in ("http", "https"):
        return None
    dest = os.path.join(archive_dir, archive_path_for_url(url))
    if os.path.isfile(dest):
        with open(dest, "rb") as existing:
            return existing.read()
    for source_url in source_urls or [url]:
        try:
            response = make_request(source_url)
        except requests.RequestException as e:
            LOGGER.warning("Could not download {}: {}".format(source_url, e))
            continue
        if response.status_code == 200:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(response.content)
            return response.content
    return None


def download_all_to_archive(urls_and_sources, archive_dir):
    """download_to_archive for a list of (url, source_urls), in parallel, as packages like MathJax have many files"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda args: download_to_archive(args[0], archive_dir, source_urls=args[1]), urls_and_sources))


# Matches the chunk filename functions in a webpack runtime, which contain a map from chunk id to content hash, e.g.
#   o.u=e=>e+"."+{28:"bb005543f41af5fb",115:"7e0a23b1119b8951"}[e]+".js"
#   o.miniCssF=e=>"prefix-"+e+"."+{115:"b962e3b6e349f40f"}[e]+".css"
WEBPACK_CHUNK_MAP_RE = re.compile(r'(?:"([^"]*)"\+)?\w+\+"([^"]*)"\+\{([^{}]*)\}\[\w+\]\+"([^"]*\.(?:js|css))"')
WEBPACK_CHUNK_ENTRY_RE = re.compile(r'"?([\w-]+)"?:"(\w+)"')
WASM_FILE_RE = re.compile(r'"([\w.-]+\.wasm)"')
CSS_URL_RE = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)")


def download_webpack_lazy_chunks(script_url, archive_dir):
    """
    Runestone components are bundled with webpack, which only loads most of its JS and CSS chunks when a page uses a
    component that needs them. If this script is a webpack runtime, download all of the chunks it could load.
    """
    response = try_request(script_url)
    if response is None or response.status_code != 200:
        return
    runtime = response.text
    if "webpackChunk" not in runtime:
        return

    # chunks are loaded relative to the location of the runtime script (webpack's "automatic publicPath")
    public_path = script_url.split("?")[0].rsplit("/", 1)[0] + "/"
    for prefix, separator, entries, suffix in WEBPACK_CHUNK_MAP_RE.findall(runtime):
        for chunk_id, chunk_hash in WEBPACK_CHUNK_ENTRY_RE.findall(entries):
            chunk_url = public_path + prefix + chunk_id + separator + chunk_hash + suffix
            chunk = download_to_archive(chunk_url, archive_dir)
            if chunk is None:
                continue
            chunk = chunk.decode("utf-8", errors="replace")
            if chunk_url.endswith(".css"):
                download_css_resources(chunk_url, chunk, archive_dir)
            else:
                # e.g. sql.js loads sql-wasm.wasm from the publicPath
                for wasm_file in WASM_FILE_RE.findall(chunk):
                    download_to_archive(public_path + wasm_file, archive_dir)


def download_css_resources(css_url, css, archive_dir):
    """Download fonts, images and imports referenced from a css file that isn't linked directly from a page"""
    for ref in CSS_URL_RE.findall(css):
        if ref.startswith("data:"):
            continue
        ref_url = urljoin(css_url, ref).split("?")[0]
        content = download_to_archive(ref_url, archive_dir)
        if content is not None and urldefrag(ref_url)[0].endswith(".css"):
            download_css_resources(ref_url, content.decode("utf-8", errors="replace"), archive_dir)


def fetch_knowls(page, page_url):
    """
    Download the knowls (html snippets loaded and inserted into the page when clicked) referenced in a parsed page,
    including knowls referenced from within other knowls.

    Returns a dict from the path of the knowl relative to the page (as given in the data-knowl attribute) to its html.
    """
    knowls = {}
    to_visit = [page]
    while to_visit:
        for node in to_visit.pop().find_all(attrs={"data-knowl": True}):
            knowl_ref = node["data-knowl"]
            knowl_path = os.path.normpath(urldefrag(knowl_ref)[0])
            if urlparse(knowl_ref).scheme or knowl_path.startswith("..") or os.path.isabs(knowl_path) \
                    or knowl_path in knowls:
                continue
            response = make_request(urljoin(page_url, knowl_ref))
            if response.status_code != 200:
                continue
            knowls[knowl_path] = response.content.decode("utf-8", errors="replace")
            to_visit.append(parse_html(knowls[knowl_path]))
    return knowls


# attributes in a knowl that reference resources that need to be included in the dependency zip
KNOWL_RESOURCE_ATTRS = {"img": "src", "script": "src", "source": "src", "video": "poster", "audio": "src"}


def knowl_resources(knowl, page_url):
    """yields (node, attribute, absolute url) for each resource referenced in a parsed knowl"""
    for tag, attr in KNOWL_RESOURCE_ATTRS.items():
        for node in knowl.find_all(tag, attrs={attr: True}):
            if node[attr].startswith("data:"):
                continue
            # knowls are inserted into the page that opens them, so their relative links are relative to the page
            yield node, attr, urljoin(page_url, node[attr])


def download_knowl_resources(knowl_html, page_url, archive_dir):
    for _, _, resource_url in knowl_resources(parse_html(knowl_html), page_url):
        download_to_archive(resource_url, archive_dir)


def rewrite_knowl_for_page(knowl_html, page_url, dep_file_reference):
    """Point the resources in a knowl at the dependency zip, and links to other pages at their Kolibri nodes"""
    knowl = parse_html(knowl_html)
    for node, attr, resource_url in knowl_resources(knowl, page_url):
        if urlparse(resource_url).scheme in ("http", "https"):
            node[attr] = dep_file_reference + archive_path_for_url(resource_url)
    return replace_links_to_other_pages(str(knowl))


def replace_links_to_other_pages(html):
    # replace other URLs with navigation events to visit other node in the Kolibri tree
    for orig_url in orig_urls_to_node_ids:
        html = html.replace("href=\"" + orig_url,
                            "onClick=\"window.kolibri.navigateTo('{}')"
                            .format(orig_urls_to_node_ids[orig_url]))
    return html


# MathJax scripts found while building the dependency zip, keyed by the path archive_page rewrites the script's src
# to, so that the pages can be pointed at the downloaded copy of the MathJax package (see download_mathjax)
mathjax_scripts = {}

JSDELIVR_NPM_API = "https://data.jsdelivr.com/v1/packages/npm/"
JSDELIVR_NPM_CDN = "https://cdn.jsdelivr.net/npm/"

# Where books commonly load MathJax from, capturing the version (or version range) and the path within the package
MATHJAX_CDN_URL_RES = [
    re.compile(r"^https?://cdn\.jsdelivr\.net/npm/mathjax@([^/]+)(/.+)$"),
    re.compile(r"^https?://unpkg\.com/mathjax@([^/]+)(/.+)$"),
    re.compile(r"^https?://cdnjs\.cloudflare\.com/ajax/libs/mathjax/([^/]+)(/.+)$"),
    re.compile(r"^https?://cdn\.jsdelivr\.net/gh/mathjax/MathJax@([^/]+)(/.+)$"),
]
# version numbers mentioned in a MathJax script, used to identify copies of MathJax a book hosts itself
MATHJAX_VERSION_CANDIDATE_RE = re.compile(r'"([234]\.\d+\.\d+)"')
# the combined components at the top level of the MathJax 4 package, e.g. tex-mml-chtml.js, a page only uses one
MATHJAX_4_COMBINED_COMPONENT_RE = re.compile(r"^/(?:tex|mml)[\w-]*\.js$")
# MathJax 4 loads its fonts from separate packages, by default from here (its default loader.paths.fonts)
MATHJAX_4_FONTS_URL = "https://cdn.jsdelivr.net/npm/@mathjax"


def list_npm_package(package, version_spec):
    """
    List the files in an npm package with the jsDelivr API, returns (exact version, {path in package: sha256 base64})
    """
    try:
        resolved = make_request("{}{}/resolved?specifier={}".format(JSDELIVR_NPM_API, package, quote(version_spec)))
        version = resolved.json().get("version") if resolved.status_code == 200 else None
        if not version:
            return None, {}
        listing = make_request("{}{}@{}?structure=flat".format(JSDELIVR_NPM_API, package, version))
        if listing.status_code != 200:
            return version, {}
        return version, {f["name"]: f["hash"] for f in listing.json()["files"]}
    except (requests.RequestException, ValueError, KeyError) as e:
        LOGGER.warning("Could not list the files in {}@{} from jsDelivr: {}".format(package, version_spec, e))
        return None, {}


def identify_mathjax(script_url, script_content):
    """
    Work out which version of MathJax a script is from, and where the script is within the MathJax package.

    Returns (exact version, files in the package, path of the script in the package), or None if it isn't recognized
    """
    url = script_url.split("?")[0]
    for pattern in MATHJAX_CDN_URL_RES:
        match = pattern.match(url)
        if match:
            version, files = list_npm_package("mathjax", match.group(1))
            if match.group(2) in files:
                return version, files, match.group(2)

    # a copy of MathJax hosted with the book, look for a file in one of the versions it mentions with the same contents
    script_hash = base64.b64encode(hashlib.sha256(script_content).digest()).decode()
    candidates = dict.fromkeys(MATHJAX_VERSION_CANDIDATE_RE.findall(script_content.decode("utf-8", errors="replace")))
    for version_spec in list(candidates)[:5]:
        version, files = list_npm_package("mathjax", version_spec)
        matching = [path for path, file_hash in files.items() if file_hash == script_hash]
        if matching:
            # prefer the same file name, the same contents can be in the package more than once
            return version, files, max(matching, key=lambda path: url.endswith(path))
    return None


def mathjax_files_needed(files, script_path, major_version):
    """The files from the MathJax package that a page loading the script at script_path could need"""
    if major_version == 2:
        # unpacked/ is the uncompressed source of the rest of the package
        return [f for f in files if not f.startswith(("/unpacked/", "/test/", "/docs/"))]
    if major_version == 3:
        # the components are loaded relative to the script, e.g. everything in es5/
        component_root = os.path.dirname(script_path).rstrip("/") + "/"
        return [f for f in files if f.startswith(component_root)]
    return [f for f in files if not MATHJAX_4_COMBINED_COMPONENT_RE.match(f) or f == script_path]


def mathjax_config_text(page):
    """The text of the inline scripts in a page that configure MathJax"""
    return "\n".join(s.get_text() for s in page.find_all("script", src=False) if "MathJax" in s.get_text())


def download_mathjax(script_url, page, page_url, archive_dir):
    """
    MathJax loads its components, fonts and TeX extensions as they are needed, and there isn't a reliable way to know
    which ones a page will need. So identify the version of MathJax the script is from and download the files from that
    version of the package that could be loaded, listing them with the jsDelivr API, as CDNs don't allow listing
    directories. Files are saved where the page would load them from, falling back to downloading them from jsDelivr.

    Returns whether the script is MathJax
    """
    response = try_request(script_url)
    if response is None or response.status_code != 200:
        return False
    named_mathjax = "mathjax" in script_url.lower()
    if not named_mathjax and b"MathJax" not in response.content:
        return False
    identified = identify_mathjax(script_url, response.content)
    if not identified:
        if named_mathjax:
            LOGGER.warning("Could not identify the version of MathJax loaded from {}, math may not render".format(script_url))
        return False
    version, files, script_path = identified
    major_version = int(version.split(".")[0])
    LOGGER.info("Downloading MathJax {} for {}".format(version, script_url))

    # MathJax loads everything relative to the directory its script is in, whatever that directory is called
    script_dir = posixpath.dirname(script_path)
    urls_and_sources = []
    for path in mathjax_files_needed(files, script_path, major_version):
        file_url = urljoin(script_url, posixpath.relpath(path, script_dir))
        urls_and_sources.append((file_url, [file_url, "{}mathjax@{}{}".format(JSDELIVR_NPM_CDN, version, path)]))
    download_all_to_archive(urls_and_sources, archive_dir)

    fonts_url = None
    if major_version >= 4:
        # MathJax's own copy of the package's directory, e.g. https://cdn.jsdelivr.net/npm/mathjax@4/
        package_root = urljoin(script_url, posixpath.relpath("/", script_dir).rstrip("/") + "/" if script_dir != "/" else ".")
        fonts_url = download_mathjax_4_font(version, script_path, page, archive_dir, package_root)

    archived_src = downloader.get_archive_filename(script_url, archive_dir, page_url)
    mathjax_scripts[archived_src] = {"url": script_url, "fonts_url": fonts_url}
    return True


def download_mathjax_4_font(version, script_path, page, archive_dir, package_root):
    """
    Starting with MathJax 4, fonts are in separate packages, loaded from jsDelivr by default rather than relative to
    MathJax, https://docs.mathjax.org/en/v4.1/web/hosting.html. Download the font the page uses, to where it will be
    loaded from once the page's loader.paths.fonts is pointed at the dependency zip (see point_mathjax_at_dependency_zip).

    Returns the URL the font packages are saved under, to use for loader.paths.fonts
    """
    config = mathjax_config_text(page)
    if re.search(r"\bfontPath\b", config):
        LOGGER.warning("The MathJax configuration sets a fontPath, which isn't handled, math may not render")
    font_match = re.search(r"""\bfont["']?\s*:\s*["']([\w-]+)["']""", config)
    font = font_match.group(1) if font_match else "mathjax-newcm"
    output = "svg" if "svg" in os.path.basename(script_path) else "chtml"

    package = "@mathjax/{}-font".format(font)
    # MathJax loads the version of the font matching its own version
    font_version, files = list_npm_package(package, version)
    if not files:
        font_version, files = list_npm_package(package, version.split(".")[0])
    if not files:
        LOGGER.warning("Could not list the files for the MathJax font {}, math may not render".format(package))
        return None

    # e.g. chtml.js, chtml/woff2/*.woff2 and chtml/dynamic/*.js. They go where MathJax loads them from by default, and
    # also next to the MathJax package, the way npm installs them (node_modules/mathjax and node_modules/@mathjax),
    # where sites hosting MathJax themselves tend to point it, e.g. CS50's assets/mathjax and assets/@mathjax
    fonts_urls = dict.fromkeys([MATHJAX_4_FONTS_URL, urljoin(package_root, "../@mathjax").rstrip("/")])
    download_all_to_archive([
        ("{}/{}-font{}".format(fonts_url, font, path),
         ["{}{}@{}{}".format(JSDELIVR_NPM_CDN, package, font_version, path)])
        for fonts_url in fonts_urls
        for path in files if path == "/{}.js".format(output) or path.startswith("/{}/".format(output))
    ], archive_dir)
    return MATHJAX_4_FONTS_URL


def download_mathjax_loader_extensions(page, page_url, archive_dir):
    """
    Download the extra files a page's MathJax configuration has the MathJax loader load, from paths the configuration
    adds, e.g. PreTeXt loads [pretext]/mathjaxknowl3.js with "paths": {"pretext": "_static/pretext/js/lib"}
    """
    config = mathjax_config_text(page)
    paths = {}
    for block in re.findall(r"""\bpaths["']?\s*:\s*\{([^{}]*)\}""", config):
        paths.update(re.findall(r"""["']?([\w-]+)["']?\s*:\s*["']([^"']+)["']""", block))
    # a list of strings, which contain [ and ], e.g. "load": ["[tex]/extpfeil", "[pretext]/mathjaxknowl3.js"]
    for block in re.findall(r"""\bload["']?\s*:\s*\[((?:\s*(?:"[^"]*"|'[^']*')\s*,?)*)\s*\]""", config):
        for entry in re.findall(r"""["']([^"']+)["']""", block):
            match = re.match(r"^\[([\w-]+)\]/(.+)$", entry)
            # anything else is a MathJax component, which is in the MathJax package
            if not match or match.group(1) not in paths or "[" in paths[match.group(1)]:
                continue
            extension_url = urljoin(page_url, paths[match.group(1)].rstrip("/") + "/" + match.group(2))
            if not os.path.splitext(extension_url)[1]:
                extension_url += ".js"
            download_to_archive(extension_url, archive_dir)


def point_mathjax_at_dependency_zip(page, dep_file_reference):
    """Point a page's MathJax script tags at the MathJax package downloaded into the dependency zip"""
    for script in page.find_all("script", src=True):
        src = script["src"]
        info = mathjax_scripts.get(src[2:] if src.startswith("./") else src)
        if not info:
            continue
        # keep the query, MathJax 2 reads its configuration from it, e.g. MathJax.js?config=TeX-AMS_CHTML
        query = urlparse(info["url"]).query
        script["src"] = dep_file_reference + archive_path_for_url(info["url"]) + ("?" + query if query else "")
        if info["fonts_url"]:
            # unless the page sets it, MathJax 4 loads fonts from jsDelivr instead of relative to itself
            set_fonts_path = page.new_tag("script")
            set_fonts_path.string = (
                "window.MathJax = window.MathJax || {}; MathJax.loader = MathJax.loader || {}; "
                "MathJax.loader.paths = Object.assign({fonts: '%s'}, MathJax.loader.paths);"
                % (dep_file_reference + archive_path_for_url(info["fonts_url"])))
            script.insert_before(set_fonts_path)


def process_wikipedia_page(content, baseurl, destpath, **kwargs):

    page = BeautifulSoup(content, "html.parser")

    for image in page.find_all("img"):
        relpath, _ = download_file(
            make_fully_qualified_url(image["src"]), destpath, request_fn=make_request
        )
        image["src"] = relpath

    return str(page)


if __name__ == "__main__":
    """
    Call this script using:
        ./sushichef.py --token=YOURSTUDIOTOKENHERE9139139f3a23232
    """

    # current_file_dir = Path(__file__).resolve().parent
    # cache_dirs = [".ricecookerfilecache", ".webcache", "chefdata", "restore", "storage"]
    # for cache_dir in cache_dirs:
    #     full_cache_dir = current_file_dir / cache_dir
    #     if Path(full_cache_dir).exists():
    #         shutil.rmtree(full_cache_dir)

    wikichef = WikipediaChef()
    wikichef.main()
    orig_urls_to_node_ids = dict(map(lambda x: (x.source_id, x.node_id), wikichef.tree.all_nodes))
    wikichef.main()
    # print deduplicated list of youtube video ids
    print(set(youtube_codes))
    print("done")

