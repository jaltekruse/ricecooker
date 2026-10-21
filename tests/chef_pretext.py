#!/usr/bin/env python
import os
import re
import tempfile
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
# Fallback used if the MathJax files can't be listed from jsDelivr
MATHJAX_LOCAL_ES5_DIR = "/home/jason/src/MathJax/es5"
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

        chapter_number = chapter.findNext("span").text
        chapter_title = chapter_number + " - " + chapter.findNext("span").findNext("span").text
        chapter_summary_url = urljoin(list_url, chapter.findNext("a").attrs["href"])

        sub_chapters = []
        if CHAPTER_FILTER is None or CHAPTER_FILTER in chapter_title:
            for sub_chapter in list(chapter.find_all("ul", recursive=False))[0].find_all("li", recursive=False):
                sub_chap_number = sub_chapter.findNext("span").text
                sub_chap_title = sub_chap_number + " - " + sub_chapter.findNext("span").findNext("span").text

                if SUBCHAPTER_FILTER is None or SUBCHAPTER_FILTER in sub_chap_title:
                    sub_chap_url = urljoin(list_url, list(sub_chapter.find_all("a", recursive="False"))[0].attrs["href"])
                    sub_chapters.append((sub_chap_url, sub_chap_title, sub_chap_number))

        if sub_chapters:
            chapters.append((chapter.findNext("a").attrs["href"], chapter_summary_url, chapter_title, sub_chapters))

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
            if "mathjax" in script_url.lower():
                download_mathjax(script_url, destpath)
            else:
                download_webpack_lazy_chunks(script_url, destpath)

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


def download_to_archive(url, archive_dir):
    """
    Download a single resource into archive_dir at the same location archive_page would put it, returns the content
    of the resource, or None if it couldn't be downloaded
    """
    url = urldefrag(url)[0]
    if urlparse(url).scheme not in ("http", "https"):
        return None
    dest = os.path.join(archive_dir, archive_path_for_url(url))
    if os.path.isfile(dest):
        with open(dest, "rb") as existing:
            return existing.read()
    response = make_request(url)
    if response.status_code != 200:
        return None
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(response.content)
    return response.content


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
    response = make_request(script_url)
    if response.status_code != 200:
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


def download_mathjax(script_url, archive_dir):
    """
    MathJax loads its fonts and TeX extensions as they are needed, and there isn't a reliable way to know which ones
    a page will need, so download the whole es5 directory it is loaded from. When MathJax comes from jsDelivr the
    files can be listed with their API, otherwise fall back to a local copy of MathJax.
    """
    es5_url = script_url.split("?")[0].rsplit("/", 1)[0] + "/"
    es5_dest = os.path.join(archive_dir, archive_path_for_url(es5_url))

    match = re.match(r"https?://cdn\.jsdelivr\.net/npm/((?:@[^/]+/)?[^/@]+)@([^/]+)(/.*/)$", es5_url)
    if match:
        package, version, package_dir = match.groups()
        listing = make_request(
            "https://data.jsdelivr.com/v1/packages/npm/{}@{}?structure=flat".format(package, version))
        if listing.status_code == 200:
            for file_info in listing.json()["files"]:
                if file_info["name"].startswith(package_dir):
                    download_to_archive(es5_url + file_info["name"][len(package_dir):], archive_dir)
            return

    if os.path.isdir(MATHJAX_LOCAL_ES5_DIR):
        LOGGER.warning("Could not list MathJax files from {}, using local copy {}".format(es5_url, MATHJAX_LOCAL_ES5_DIR))
        shutil.copytree(MATHJAX_LOCAL_ES5_DIR, es5_dest, dirs_exist_ok=True)
    else:
        LOGGER.warning("Could not download all of MathJax from {}, some math may not render".format(es5_url))


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

