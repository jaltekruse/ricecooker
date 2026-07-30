#!/usr/bin/env python
import os
import re
import tempfile

import glob 
import shutil

import le_utils
import requests
from bs4 import BeautifulSoup

from ricecooker.chefs import SushiChef
from ricecooker.classes import licenses
from ricecooker.classes.files import HTMLZipFile
from ricecooker.classes.nodes import ChannelNode
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


# CHANNEL SETTINGS
SOURCE_DOMAIN = "https://activecalculus.org/single2e/frontmatter.html"
# SOURCE_ID = "thinkcspi_runestone_academy"  # an alphanumeric ID refering to this channel
# CHANNEL_TITLE = "How to Think Like a Computer Scientist, Interactive Edition"  # a humand-readbale title
SOURCE_ID = "active_calc_with_doenet_feb_25_2026"  # an alphanumeric ID refering to this channel
#CHANNEL_TITLE = "Nov 20th C WIP - How to Think Like a Computer Scientist, Interactive Edition"  # a humand-readbale title
CHANNEL_TITLE = "Feb 25 2026 B WIP - Active Calculus: with Doenet "  # a humand-readbale title

# youtube ids {'SGVgAV0v-Ww', 'Yxyx6KpKRzY', 'aqhREpceEMI', '3WgmLIsXFkI', '57dPVbnRouU', 'YK8QlIT3__M', 'xGSfiZt5cdw',
# 'GCLHuPBtLdQ', 'Fd4a8ktQURc', 'blTBEqybQmQ', 'vNfCfowr-pQ', 'HriDtn-0Dcw', 'LD-F4RODy-I', '1uQM-TVlaMo', 'LZ7H1X8ar9E',
# 'Ezve3QJv6Aw', 'Px1c-3GP-5o', '2KYixkCBXSQ', '4wKtB57J5J4', 'G86akhNFHZA'}

#SOURCE_ID = "jason_pretext_test_new_id"  # an alphanumeric ID refering to this channel
#CHANNEL_TITLE = "Jason PreteXt testing"
CHANNEL_LANGUAGE = "en"  # language of channel
DOMAIN = "http://localhost:8080/"


sess = requests.Session()
cache = FileCache(".webcache")
basic_adapter = CacheControlAdapter(cache=cache)
forever_adapter = CacheControlAdapter(heuristic=CacheForeverHeuristic(), cache=cache)

sess.mount("http://", forever_adapter)
sess.mount("https://", forever_adapter)

dep_zip = None

cache_invalidator_string = "        "

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


def get_parsed_html_from_url(url, *args, **kwargs):
    html = make_request(url, *args, **kwargs).content
    return BeautifulSoup(html, "html.parser")


class WikipediaChef(SushiChef):
    def get_channel(self, *args, **kwargs):

        channel = ChannelNode(
            source_domain=SOURCE_DOMAIN,
            source_id=SOURCE_ID,
            title=CHANNEL_TITLE,
            thumbnail="https://lh3.googleusercontent.com/zwwddqxgFlP14DlucvBV52RUMA-cV3vRvmjf-iWqxuVhYVmB-l8XN9NDirb0687DSw=w300",
            language=CHANNEL_LANGUAGE,
        )

        return channel

    def construct_channel(self, *args, **kwargs):

        channel = self.get_channel(**kwargs)
        add_subpages_from_pretext_toc(
            channel, DOMAIN + "frontmatter.html"
        )

        # potato_topic = TopicNode(
        #     source_id="List_of_potato_cultivars", title="Potatoes!"
        # )
        # channel.add_child(potato_topic)
        # add_subpages_from_wikipedia_list(
        #     potato_topic, "https://en.wikipedia.org/wiki/List_of_potato_cultivars"
        # )

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
    # loop through all the rows in the table
    for chapter in list(table.children)[0].find_all("li", recursive=False):

        chapter_number = chapter.findNext("span").text
        title = chapter_number + " - " + chapter.findNext("span").findNext("span").text
        chapter_topic = TopicNode(source_id=chapter.findNext("a").attrs["href"], title=title)

        chapter_summary_node_added = False
        chapter_summary_url = DOMAIN + chapter.findNext("a").attrs["href"]

        for sub_chapter in list(chapter.find_all("ul", recursive=False))[0].find_all("li", recursive=False):
            sub_chap_number = sub_chapter.findNext("span").text
            sub_chap_title = sub_chap_number + " - " + sub_chapter.findNext("span").findNext("span").text
            #sub_chapter_topic = TopicNode(source_id=sub_chapter.findNext("a").attrs["href"], title=sub_chap_title)
            # chapter_topic.add_child(sub_chapter_topic)

            if "2.2" in sub_chap_title or "2.3" in sub_chap_title or "2.4" in sub_chap_title:
            # if "1." in sub_chap_title or "2." in sub_chap_title or "3." in sub_chap_title:
                sub_chap_url = DOMAIN + list(sub_chapter.find_all("a", recursive="False"))[0].attrs["href"]
                if dep_zip is None:
                    download_depedency_zip_files(sub_chap_url, thumbnail=None, title=sub_chap_title)
                html5app = download_book_page(sub_chap_url, thumbnail=None, title=sub_chap_title)
                if not chapter_summary_node_added:
                    # add a page for the chapter overview, to give us a place to link to for that entry in the table of contents
                    chapter_html5app = download_book_page(chapter_summary_url, thumbnail=None, title=title)
                    chapter_topic.add_child(chapter_html5app)
                    chapter_summary_node_added = True
                chapter_topic.add_child(html5app)

        channel.add_child(chapter_topic)

def download_book_page(url, thumbnail, title):
    destpath = tempfile.mkdtemp()

    archive_page(url, destpath, skip_static_asset_download=True)
    #archive_page(url, destpath)

    # mathjax_dest = destpath + "/cdn.jsdelivr.net/npm/mathjax@3/"
    # shutil.rmtree(mathjax_dest + "es5")
    # shutil.copytree("/home/jason/src/MathJax/es5", mathjax_dest + "/es5")
    index_path = destpath + "/index.html"
    parser = web.HTMLParser(index_path)

    local_links = parser.get_links()
    links_to_replace = {}

    global dep_zip
    dep_zip_file = HTMLZipFile(dep_zip, preset=le_utils.constants.format_presets.HTML5_DEPENDENCY_ZIP)
    #dep_zip_file.preset = le_utils.constants.format_presets.HTML5_DEPENDENCY_ZIP
    #print("JASON DEBUG - #$%@#!$^#$%^^@#$%&^#$%%@$#%@#%$#@%@#$%@#$%@#$%@#$%@#$%@#$%@#$%#&&^(*(")
    #print(dep_zip_file.preset)

    # TODO Jason - I bleive I was told to always recreate the HTMLZipFile node, but this makes
    # me think I'm re-computing the checksum repreatedly
    dep_file_reference = '/zipcontent/{}.zip/'.format(dep_zip_file.checksum)
    assets_ref = './'
    pie_ref = '../../PIE/'
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

    new_html = parser.replace_links(links_to_replace)

    # TODO Jason - very hack just trying to get pretext working
    # this is for custom data attributes on some tags that are interpreted as URLs by PreteXt javascript
    new_html = new_html.replace("\"_static", "\"" + dep_file_reference + "./localhost:8080/_static")
    new_html = new_html.replace("\"./knowl", "\"" + dep_file_reference  + "./localhost:8080/knowl")
    new_html = re.sub(r"(iframe.*src=\")", r"\1" + dep_file_reference, new_html)

    # replace other URLs with navigation events to visit other node in the Kolibri tree
    for orig_url in orig_urls_to_node_ids:
        new_html = new_html.replace("href=\"" + orig_url,
                                    "onClick=\"window.kolibri.navigateTo('{}')"
                                    .format(orig_urls_to_node_ids[orig_url]))

    youtube_codes.extend(re.findall(r"youtube.*/embed/(.*)\?", new_html))
    #print(new_html)

    # isolate the index.html it it's own folder, all resources should now be coming out of the dep zip
    new_dest = destpath + "/PRETEXT_INDEX_ALONE_" + os.path.basename(destpath)
    os.makedirs(new_dest, exist_ok=True)

    global cache_invalidator_string
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
        # license=None
        # getting a weird failure when I try to set a license
        # ricecooker.exceptions.InvalidNodeException: 2 - Euclidean Vectors (EV) (HTML5AppNode): 1 file: License is not a license object
        # in the debugger I'm confused, __bases__ shows this license object inherits from
        # (<class 'ricecooker.classes.licenses.License'>,), which appears to be the class it is checking for? but isinstance returns false
        # TODO JASON - seems like this assertion needs updating, it complains even if I have this, need to put it in the license itself below
        license_description="GNU Free Documentation License - Version 1.3",
        license=licenses.CC_BY_SALicense(copyright_holder="Matthew Boelkins, David Austin, Christina Safranski, Steven Schlicker, Mitchel T. Keller",
                                                   )
    )
    return html5app

def replace_strings_in_file(file_path, old_string, new_string):
    try:
        with open(file_path, 'r') as file:
            file_content = file.read()

        updated_content = file_content.replace(old_string, new_string)

        with open(file_path, 'w') as file:
            file.write(updated_content)

        print(f"Text replacement completed successfully in '{file_path}'.")
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

def download_depedency_zip_files(url, thumbnail, title):

    # create a temp directory to house our downloaded files
    destpath = tempfile.mkdtemp()

    # downlod the main wikipedia page, apply a middleware processor, and call it index.html

    #archive = downloader.ArchiveDownloader(destpath)
    #archive.get_page(url)

    #download_file(url, destpath)

    archive_page(url, destpath)

    # localref, _ = get_page(
    #     url,
    #     destpath,
    #     filename="index.html",
    #     #middleware_callbacks=process_wikipedia_page,
    #     request_fn=make_request,
    # )

    mathjax_dest = destpath + "/cdn.jsdelivr.net/npm/mathjax@3/"
    shutil.rmtree(mathjax_dest + "es5")
    shutil.copytree("/home/jason/src/MathJax/es5", mathjax_dest + "/es5")

    # https://studio.learningequality.org/zipcontent/a7a5a810f1b2f926f6070496ec19d1b6.zip/cdn.jsdelivr.net/npm/mathjax@3

    mathjax_4_font_dest = destpath + "/cdn.jsdelivr.net/npm/"
    #shutil.rmtree(mathjax_4_font_dest + "@mathjax")
    #shutil.rmtree(mathjax_4_font_dest + "mathjax@4.1.0")
    shutil.copytree("/home/jason/src/mathjax-4/node_modules/@mathjax", mathjax_4_font_dest + "@mathkax")
    shutil.copytree("/home/jason/src/mathjax-4/node_modules/mathjax", mathjax_4_font_dest + "mathjax@4.1.0")

    # https://studio.learningequality.org/zipcontent/504532c3f084544ff5450c2a57ca8816.zip/cdn.jsdelivr.net/npm/mathjax@4.1.0/tex-mml-chtml.js

    #source_dir = "/home/jason/src/thinkcspy/output/web/"
    source_dir = "/home/jason/src/matt-gh-pages-active-calculus-single-mbx/doenet/"
    pretext_dest = destpath + "/localhost:8080/"
    pretext_asset_dirs = ["external", "generated", "knowl", "_static"]
    for asset_dir in pretext_asset_dirs:
        #dest_asset_dir = pretext_dest + asset_dir

        # if Path(dest_asset_dir).exists():
        #     shutil.rmtree(dest_asset_dir)

        # copy over resources, merging with anything already preset, like rewritten files that had query params like
        # pretext_add_on.js?x=1 rewritten to pretext_add_on_x_1.js
        # Don't overwrite CSS files as those are traversed to rewrite transitive imports of resources like images/fonts
        # TODO JASON - review this, I modified it to only ignore theme.css instead of all css, I ran into generated css fragments I needed
        # to copy over, I think most of the transitive css imports I found were pulling in external things that come from other domains
        # so they don't interact with this copy and potential overwrite, but I could be mor thorough checking everything pretext is doing itself
        # with CSS
        shutil.copytree(source_dir + asset_dir, pretext_dest + asset_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns('theme.css'))

    source_pattern = source_dir + "doe-*"
    source_pattern_2_2 = source_dir + "doe-int-ex-2-2-*"

    doenet_pages_for_iframes = glob.glob(source_pattern)

    doenet_pages_for_iframes_2_2 = glob.glob(source_pattern_2_2)

    for file_path in doenet_pages_for_iframes_2_2:
        archive_page(DOMAIN + file_path.split("/")[-1], destpath)
        shutil.copy(destpath + "/index.html", destpath + "/" + file_path.split("/")[-1])

    # From doenet-standalone
    # DEFAULT_V4_SRC = "https://cdn.jsdelivr.net/npm/mathjax@4.1.0/tex-mml-chtml.js"
    replace_strings_in_file(destpath + "/cdn.jsdelivr.net/npm/@doenet/standalone@latest/doenet-standalone.js",
                            "https://cdn.jsdelivr.net/npm/", "cdn.jsdelivr.net/npm/")

    # for file_path in doenet_pages_for_iframes:
    #     try:
    #         shutil.copy(file_path, destpath)
    #     except IOError as e:
    #         print(f"Error copying {file_path}: {e}")

    # TODO Jason likely bring this back?
    #os.remove(destpath + "/index.html")

    f = open(destpath + "/index.html", "wb")
    global cache_invalidator_string
    f.write(("<html><body>This is the depedency zip</body></html>" + cache_invalidator_string).encode("utf-8"))
    f.close()
    # turn the temp folder into a zip file
    zippath = create_predictable_zip(destpath)

    global dep_zip
    dep_zip = zippath
    return None

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
    # wikichef.main()
    # print deduplicated list of youtube video ids
    print(set(youtube_codes))
    print("done")

