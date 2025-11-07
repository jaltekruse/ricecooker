#!/usr/bin/env python
import tempfile

import shutil
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
from ricecooker.utils import downloader

from ricecooker.utils.zip import create_predictable_zip


# CHANNEL SETTINGS
SOURCE_DOMAIN = "<yourdomain.org>"  #
SOURCE_ID = "jason_pretext_test"  # an alphanumeric ID refering to this channel
CHANNEL_TITLE = "<channeltitle>"  # a humand-readbale title
CHANNEL_LANGUAGE = "en"  # language of channel
DOMAIN = "http://localhost:8080/"


sess = requests.Session()
cache = FileCache(".webcache")
basic_adapter = CacheControlAdapter(cache=cache)
forever_adapter = CacheControlAdapter(heuristic=CacheForeverHeuristic(), cache=cache)

sess.mount("http://", forever_adapter)
sess.mount("https://", forever_adapter)


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
    print(response.status_code)
    if response.status_code != 200:
        print(response.text)
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

    '''
<nav id="ptx-toc" class="ptx-toc depth2 focused" data-preexpanded-levels="0" data-max-levels="2"><ul class="structural toc-item-list contains-active">
<li class="toc-item toc-frontmatter">
<div class="toc-title-box"><a href="frontmatter.html" class="internal"><span class="title">Front Matter</span></a><button class="toc-expander toc-chevron-surround" title="Expand frontmatter"><span class="icon material-symbols-outlined" aria-hidden="true">chevron_left</span></button></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-colophon"><div class="toc-title-box"><a href="front-colophon.html" class="internal"><span class="title">Colophon</span></a></div></li>
<li class="toc-item toc-preface"><div class="toc-title-box"><a href="attribution.html" class="internal"><span class="title">Attribution and Acknowledgements</span></a></div></li>
<li class="toc-item toc-preface"><div class="toc-title-box"><a href="tbil-rl.html" class="internal"><span class="title">TBIL Resource Library</span></a></div></li>
<li class="toc-item toc-preface"><div class="toc-title-box"><a href="instructor-notes.html" class="internal"><span class="title">For Instructors</span></a></div></li>
<li class="toc-item toc-preface"><div class="toc-title-box"><a href="video-resources.html" class="internal"><span class="title">Video Resources</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-chapter contains-active expanded">
<div class="toc-title-box"><a href="LE.html" class="internal"><span class="codenumber">1</span> <span class="title">Systems of Linear Equations (LE)</span></a><button class="toc-expander toc-chevron-surround" title="Close chapter"><span class="icon material-symbols-outlined" aria-hidden="true">chevron_left</span></button></div>
<ul class="structural toc-item-list contains-active">
<li class="toc-item toc-section contains-active active visible">
<div class="toc-title-box"><a href="LE1.html" class="internal"><span class="codenumber">1.1</span> <span class="title">Linear Systems, Vector Equations, and Augmented Matrices (LE1)</span></a></div>
<ul class="structural toc-item-list active">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE1.html#LE1-3" class="internal"><span class="codenumber">1.1.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE1.html#LE1-4" class="internal"><span class="codenumber">1.1.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE1.html#LE1-5" class="internal"><span class="codenumber">1.1.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE1.html#LE1-6" class="internal"><span class="codenumber">1.1.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE1.html#LE1-7" class="internal"><span class="codenumber">1.1.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE1.html#LE1-8" class="internal"><span class="codenumber">1.1.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE1.html#LE1-9" class="internal"><span class="codenumber">1.1.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>


...
...
...



<li class="toc-item toc-chapter">
<div class="toc-title-box"><a href="EV.html" class="internal"><span class="codenumber">2</span> <span class="title">Euclidean Vectors (EV)</span></a><button class="toc-expander toc-chevron-surround" title="Expand chapter"><span class="icon material-symbols-outlined" aria-hidden="true">chevron_left</span></button></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="EV1.html" class="internal"><span class="codenumber">2.1</span> <span class="title">Linear Combinations (EV1)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV1.html#EV1-3" class="internal"><span class="codenumber">2.1.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV1.html#EV1-4" class="internal"><span class="codenumber">2.1.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV1.html#EV1-5" class="internal"><span class="codenumber">2.1.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV1.html#EV1-6" class="internal"><span class="codenumber">2.1.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV1.html#EV1-7" class="internal"><span class="codenumber">2.1.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV1.html#EV1-8" class="internal"><span class="codenumber">2.1.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV1.html#EV1-9" class="internal"><span class="codenumber">2.1.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="EV2.html" class="internal"><span class="codenumber">2.2</span> <span class="title">Spanning Sets (EV2)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV2.html#EV2-3" class="internal"><span class="codenumber">2.2.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV2.html#EV2-4" class="internal"><span class="codenumber">2.2.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV2.html#EV2-5" class="internal"><span class="codenumber">2.2.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV2.html#EV2-6" class="internal"><span class="codenumber">2.2.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV2.html#EV2-7" class="internal"><span class="codenumber">2.2.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV2.html#EV2-8" class="internal"><span class="codenumber">2.2.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV2.html#EV2-9" class="internal"><span class="codenumber">2.2.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
    '''

    #print(list(table.children)[0].find_all("li", recursive=False))
    print(table.find_all("li"))
    # loop through all the rows in the table
    for chapter in list(table.children)[0].find_all("li", recursive=False):

        chapter_number = chapter.findNext("span").text
        title = chapter_number + " - " + chapter.findNext("span").findNext("span").text
        chapter_topic = TopicNode(source_id=chapter.findNext("a").attrs["href"], title=title)

        for sub_chapter in list(chapter.find_all("ul", recursive=False))[0].find_all("li", recursive=False):
            sub_chap_number = sub_chapter.findNext("span").text
            sub_chap_title = sub_chap_number + " - " + sub_chapter.findNext("span").findNext("span").text
            sub_chapter_topic = TopicNode(source_id=sub_chapter.findNext("a").attrs["href"], title=sub_chap_title)
            chapter_topic.add_child(sub_chapter_topic)

            if "2.1" in sub_chap_title:
                sub_chap_url = DOMAIN + list(sub_chapter.find_all("a", recursive="False"))[0].attrs["href"]
                html5app = download_wikipedia_page(sub_chap_url, thumbnail=None, title=title)
                sub_chapter_topic.add_child(html5app)

                # add the downloaded HTML5 app node into the topic

        channel.add_child(chapter_topic)

        # extract the columns (cells, really) within the current row
        columns = chapter.find_all("td")

        # some rows are empty, so just skip
        if not columns:
            continue

        # get the link to the subpage
        link = columns[0].find("a")

        # some rows don't have links, so skip
        if not link:
            continue

        # extract the URL and title for the subpage
        url = make_fully_qualified_url(link["href"])
        if url is None:
            continue  # skip internal links and or bad URLs
        title = link.text

        # attempt to extract a thumbnail for the subpage, from the second column in the table
        image = columns[1].find("img")
        thumbnail_url = make_fully_qualified_url(image["src"]) if image else None
        if thumbnail_url and not (
            thumbnail_url.endswith("jpg") or thumbnail_url.endswith("png")
        ):
            thumbnail_url = None

        # download the wikipedia page into an HTML5 app node
        html5app = download_wikipedia_page(url, thumbnail=thumbnail_url, title=title)

        # add the downloaded HTML5 app node into the topic
        #topic.add_child(html5app)


def download_wikipedia_page(url, thumbnail, title):

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

    # turn the temp folder into a zip file
    zippath = create_predictable_zip(destpath)

    # create an HTML5 app node
    html5app = HTML5AppNode(
        files=[HTMLZipFile(zippath, filename=zippath)],
        title=title,
        thumbnail=thumbnail,
        source_id=url.split("/")[-1],
        # license=None
        # getting a weird failure when I try to set a license
        # ricecooker.exceptions.InvalidNodeException: 2 - Euclidean Vectors (EV) (HTML5AppNode): 1 file: License is not a license object
        # in the debugger I'm confused, __bases__ shows this license object inherits from
        # (<class 'ricecooker.classes.licenses.License'>,), which appears to be the class it is checking for? but isinstance returns false
        license=licenses.CC_BY_NC_SALicense(copyright_holder="Steven Clontz and Drew Lewis")
    )

    return html5app


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
    wikichef = WikipediaChef()
    wikichef.main()

    '''
<nav id="ptx-toc" class="ptx-toc depth2 focused" data-preexpanded-levels="0" data-max-levels="2"><ul class="structural toc-item-list contains-active">
<li class="toc-item toc-frontmatter">
<div class="toc-title-box"><a href="frontmatter.html" class="internal"><span class="title">Front Matter</span></a><button class="toc-expander toc-chevron-surround" title="Expand frontmatter"><span class="icon material-symbols-outlined" aria-hidden="true">chevron_left</span></button></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-colophon"><div class="toc-title-box"><a href="front-colophon.html" class="internal"><span class="title">Colophon</span></a></div></li>
<li class="toc-item toc-preface"><div class="toc-title-box"><a href="attribution.html" class="internal"><span class="title">Attribution and Acknowledgements</span></a></div></li>
<li class="toc-item toc-preface"><div class="toc-title-box"><a href="tbil-rl.html" class="internal"><span class="title">TBIL Resource Library</span></a></div></li>
<li class="toc-item toc-preface"><div class="toc-title-box"><a href="instructor-notes.html" class="internal"><span class="title">For Instructors</span></a></div></li>
<li class="toc-item toc-preface"><div class="toc-title-box"><a href="video-resources.html" class="internal"><span class="title">Video Resources</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-chapter contains-active expanded">
<div class="toc-title-box"><a href="LE.html" class="internal"><span class="codenumber">1</span> <span class="title">Systems of Linear Equations (LE)</span></a><button class="toc-expander toc-chevron-surround" title="Close chapter"><span class="icon material-symbols-outlined" aria-hidden="true">chevron_left</span></button></div>
<ul class="structural toc-item-list contains-active">
<li class="toc-item toc-section contains-active active visible">
<div class="toc-title-box"><a href="LE1.html" class="internal"><span class="codenumber">1.1</span> <span class="title">Linear Systems, Vector Equations, and Augmented Matrices (LE1)</span></a></div>
<ul class="structural toc-item-list active">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE1.html#LE1-3" class="internal"><span class="codenumber">1.1.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE1.html#LE1-4" class="internal"><span class="codenumber">1.1.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE1.html#LE1-5" class="internal"><span class="codenumber">1.1.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE1.html#LE1-6" class="internal"><span class="codenumber">1.1.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE1.html#LE1-7" class="internal"><span class="codenumber">1.1.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE1.html#LE1-8" class="internal"><span class="codenumber">1.1.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE1.html#LE1-9" class="internal"><span class="codenumber">1.1.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section visible">
<div class="toc-title-box"><a href="LE2.html" class="internal"><span class="codenumber">1.2</span> <span class="title">Row Reduction of Matrices (LE2)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE2.html#LE2-3" class="internal"><span class="codenumber">1.2.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE2.html#LE2-4" class="internal"><span class="codenumber">1.2.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE2.html#LE2-5" class="internal"><span class="codenumber">1.2.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE2.html#LE2-6" class="internal"><span class="codenumber">1.2.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE2.html#LE2-7" class="internal"><span class="codenumber">1.2.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE2.html#LE2-8" class="internal"><span class="codenumber">1.2.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE2.html#LE2-9" class="internal"><span class="codenumber">1.2.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section visible">
<div class="toc-title-box"><a href="LE3.html" class="internal"><span class="codenumber">1.3</span> <span class="title">Counting Solutions for Linear Systems (LE3)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE3.html#LE3-3" class="internal"><span class="codenumber">1.3.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE3.html#LE3-4" class="internal"><span class="codenumber">1.3.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE3.html#LE3-5" class="internal"><span class="codenumber">1.3.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE3.html#LE3-6" class="internal"><span class="codenumber">1.3.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE3.html#LE3-7" class="internal"><span class="codenumber">1.3.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE3.html#LE3-8" class="internal"><span class="codenumber">1.3.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE3.html#LE3-9" class="internal"><span class="codenumber">1.3.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section visible">
<div class="toc-title-box"><a href="LE4.html" class="internal"><span class="codenumber">1.4</span> <span class="title">Linear Systems with Infinitely-Many Solutions (LE4)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE4.html#LE4-3" class="internal"><span class="codenumber">1.4.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE4.html#LE4-4" class="internal"><span class="codenumber">1.4.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE4.html#LE4-5" class="internal"><span class="codenumber">1.4.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE4.html#LE4-6" class="internal"><span class="codenumber">1.4.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE4.html#LE4-7" class="internal"><span class="codenumber">1.4.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE4.html#LE4-8" class="internal"><span class="codenumber">1.4.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="LE4.html#LE4-9" class="internal"><span class="codenumber">1.4.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
</ul>
</li>
<li class="toc-item toc-chapter">
<div class="toc-title-box"><a href="EV.html" class="internal"><span class="codenumber">2</span> <span class="title">Euclidean Vectors (EV)</span></a><button class="toc-expander toc-chevron-surround" title="Expand chapter"><span class="icon material-symbols-outlined" aria-hidden="true">chevron_left</span></button></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="EV1.html" class="internal"><span class="codenumber">2.1</span> <span class="title">Linear Combinations (EV1)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV1.html#EV1-3" class="internal"><span class="codenumber">2.1.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV1.html#EV1-4" class="internal"><span class="codenumber">2.1.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV1.html#EV1-5" class="internal"><span class="codenumber">2.1.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV1.html#EV1-6" class="internal"><span class="codenumber">2.1.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV1.html#EV1-7" class="internal"><span class="codenumber">2.1.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV1.html#EV1-8" class="internal"><span class="codenumber">2.1.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV1.html#EV1-9" class="internal"><span class="codenumber">2.1.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="EV2.html" class="internal"><span class="codenumber">2.2</span> <span class="title">Spanning Sets (EV2)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV2.html#EV2-3" class="internal"><span class="codenumber">2.2.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV2.html#EV2-4" class="internal"><span class="codenumber">2.2.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV2.html#EV2-5" class="internal"><span class="codenumber">2.2.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV2.html#EV2-6" class="internal"><span class="codenumber">2.2.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV2.html#EV2-7" class="internal"><span class="codenumber">2.2.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV2.html#EV2-8" class="internal"><span class="codenumber">2.2.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV2.html#EV2-9" class="internal"><span class="codenumber">2.2.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="EV3.html" class="internal"><span class="codenumber">2.3</span> <span class="title">Subspaces (EV3)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV3.html#EV3-3" class="internal"><span class="codenumber">2.3.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV3.html#EV3-4" class="internal"><span class="codenumber">2.3.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV3.html#EV3-5" class="internal"><span class="codenumber">2.3.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV3.html#EV3-6" class="internal"><span class="codenumber">2.3.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV3.html#EV3-7" class="internal"><span class="codenumber">2.3.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV3.html#EV3-8" class="internal"><span class="codenumber">2.3.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV3.html#EV3-9" class="internal"><span class="codenumber">2.3.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="EV4.html" class="internal"><span class="codenumber">2.4</span> <span class="title">Linear Independence (EV4)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV4.html#EV4-3" class="internal"><span class="codenumber">2.4.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV4.html#EV4-4" class="internal"><span class="codenumber">2.4.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV4.html#EV4-5" class="internal"><span class="codenumber">2.4.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV4.html#EV4-6" class="internal"><span class="codenumber">2.4.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV4.html#EV4-7" class="internal"><span class="codenumber">2.4.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV4.html#EV4-8" class="internal"><span class="codenumber">2.4.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV4.html#EV4-9" class="internal"><span class="codenumber">2.4.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="EV5.html" class="internal"><span class="codenumber">2.5</span> <span class="title">Identifying a Basis (EV5)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV5.html#EV5-3" class="internal"><span class="codenumber">2.5.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV5.html#EV5-4" class="internal"><span class="codenumber">2.5.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV5.html#EV5-5" class="internal"><span class="codenumber">2.5.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV5.html#EV5-6" class="internal"><span class="codenumber">2.5.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV5.html#EV5-7" class="internal"><span class="codenumber">2.5.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV5.html#EV5-8" class="internal"><span class="codenumber">2.5.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV5.html#EV5-9" class="internal"><span class="codenumber">2.5.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="EV6.html" class="internal"><span class="codenumber">2.6</span> <span class="title">Subspace Basis and Dimension (EV6)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV6.html#EV6-3" class="internal"><span class="codenumber">2.6.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV6.html#EV6-4" class="internal"><span class="codenumber">2.6.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV6.html#EV6-5" class="internal"><span class="codenumber">2.6.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV6.html#EV6-6" class="internal"><span class="codenumber">2.6.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV6.html#EV6-7" class="internal"><span class="codenumber">2.6.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV6.html#EV6-8" class="internal"><span class="codenumber">2.6.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV6.html#EV6-9" class="internal"><span class="codenumber">2.6.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="EV7.html" class="internal"><span class="codenumber">2.7</span> <span class="title">Homogeneous Linear Systems (EV7)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV7.html#EV7-3" class="internal"><span class="codenumber">2.7.1</span> <span class="title">Warmup</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV7.html#EV7-4" class="internal"><span class="codenumber">2.7.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV7.html#EV7-5" class="internal"><span class="codenumber">2.7.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV7.html#EV7-6" class="internal"><span class="codenumber">2.7.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV7.html#EV7-7" class="internal"><span class="codenumber">2.7.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV7.html#EV7-8" class="internal"><span class="codenumber">2.7.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="EV7.html#EV7-9" class="internal"><span class="codenumber">2.7.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
</ul>
</li>
<li class="toc-item toc-chapter">
<div class="toc-title-box"><a href="AT.html" class="internal"><span class="codenumber">3</span> <span class="title">Algebraic Properties of Linear Maps (AT)</span></a><button class="toc-expander toc-chevron-surround" title="Expand chapter"><span class="icon material-symbols-outlined" aria-hidden="true">chevron_left</span></button></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="AT1.html" class="internal"><span class="codenumber">3.1</span> <span class="title">Linear Transformations (AT1)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT1.html#AT1-3" class="internal"><span class="codenumber">3.1.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT1.html#AT1-4" class="internal"><span class="codenumber">3.1.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT1.html#AT1-5" class="internal"><span class="codenumber">3.1.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT1.html#AT1-6" class="internal"><span class="codenumber">3.1.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT1.html#AT1-7" class="internal"><span class="codenumber">3.1.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT1.html#AT1-8" class="internal"><span class="codenumber">3.1.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT1.html#AT1-9" class="internal"><span class="codenumber">3.1.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="AT2.html" class="internal"><span class="codenumber">3.2</span> <span class="title">Standard Matrices (AT2)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT2.html#AT2-3" class="internal"><span class="codenumber">3.2.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT2.html#AT2-4" class="internal"><span class="codenumber">3.2.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT2.html#AT2-5" class="internal"><span class="codenumber">3.2.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT2.html#AT2-6" class="internal"><span class="codenumber">3.2.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT2.html#AT2-7" class="internal"><span class="codenumber">3.2.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT2.html#AT2-8" class="internal"><span class="codenumber">3.2.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT2.html#AT2-9" class="internal"><span class="codenumber">3.2.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="AT3.html" class="internal"><span class="codenumber">3.3</span> <span class="title">Image and Kernel (AT3)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT3.html#AT3-3" class="internal"><span class="codenumber">3.3.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT3.html#AT3-4" class="internal"><span class="codenumber">3.3.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT3.html#AT3-5" class="internal"><span class="codenumber">3.3.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT3.html#AT3-6" class="internal"><span class="codenumber">3.3.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT3.html#AT3-7" class="internal"><span class="codenumber">3.3.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT3.html#AT3-8" class="internal"><span class="codenumber">3.3.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT3.html#AT3-9" class="internal"><span class="codenumber">3.3.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="AT4.html" class="internal"><span class="codenumber">3.4</span> <span class="title">Injective and Surjective Linear Maps (AT4)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT4.html#AT4-3" class="internal"><span class="codenumber">3.4.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT4.html#AT4-4" class="internal"><span class="codenumber">3.4.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT4.html#AT4-5" class="internal"><span class="codenumber">3.4.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT4.html#AT4-6" class="internal"><span class="codenumber">3.4.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT4.html#AT4-7" class="internal"><span class="codenumber">3.4.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT4.html#AT4-8" class="internal"><span class="codenumber">3.4.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT4.html#AT4-9" class="internal"><span class="codenumber">3.4.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="AT5.html" class="internal"><span class="codenumber">3.5</span> <span class="title">Vector Spaces (AT5)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT5.html#AT5-3" class="internal"><span class="codenumber">3.5.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT5.html#AT5-4" class="internal"><span class="codenumber">3.5.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT5.html#AT5-5" class="internal"><span class="codenumber">3.5.3</span> <span class="title">Cooldown</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT5.html#AT5-6" class="internal"><span class="codenumber">3.5.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT5.html#AT5-7" class="internal"><span class="codenumber">3.5.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT5.html#AT5-8" class="internal"><span class="codenumber">3.5.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT5.html#AT5-9" class="internal"><span class="codenumber">3.5.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="AT6.html" class="internal"><span class="codenumber">3.6</span> <span class="title">Polynomial and Matrix Spaces (AT6)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT6.html#AT6-3" class="internal"><span class="codenumber">3.6.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT6.html#AT6-4" class="internal"><span class="codenumber">3.6.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT6.html#AT6-5" class="internal"><span class="codenumber">3.6.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT6.html#AT6-6" class="internal"><span class="codenumber">3.6.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT6.html#AT6-7" class="internal"><span class="codenumber">3.6.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT6.html#AT6-8" class="internal"><span class="codenumber">3.6.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="AT6.html#AT6-9" class="internal"><span class="codenumber">3.6.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
</ul>
</li>
<li class="toc-item toc-chapter">
<div class="toc-title-box"><a href="MX.html" class="internal"><span class="codenumber">4</span> <span class="title">Matrices (MX)</span></a><button class="toc-expander toc-chevron-surround" title="Expand chapter"><span class="icon material-symbols-outlined" aria-hidden="true">chevron_left</span></button></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="MX1.html" class="internal"><span class="codenumber">4.1</span> <span class="title">Matrices and Multiplication (MX1)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX1.html#MX1-3" class="internal"><span class="codenumber">4.1.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX1.html#MX1-4" class="internal"><span class="codenumber">4.1.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX1.html#MX1-5" class="internal"><span class="codenumber">4.1.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX1.html#MX1-6" class="internal"><span class="codenumber">4.1.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-exercises"><div class="toc-title-box"><a href="MX1.html#MX1-7" class="internal"><span class="codenumber">4.1.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX1.html#MX1-8" class="internal"><span class="codenumber">4.1.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX1.html#MX1-9" class="internal"><span class="codenumber">4.1.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="MX2.html" class="internal"><span class="codenumber">4.2</span> <span class="title">The Inverse of a Matrix (MX2)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX2.html#MX2-3" class="internal"><span class="codenumber">4.2.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX2.html#MX2-4" class="internal"><span class="codenumber">4.2.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX2.html#MX2-5" class="internal"><span class="codenumber">4.2.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX2.html#MX2-6" class="internal"><span class="codenumber">4.2.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-exercises"><div class="toc-title-box"><a href="MX2.html#MX2-7" class="internal"><span class="codenumber">4.2.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX2.html#MX2-8" class="internal"><span class="codenumber">4.2.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX2.html#MX2-9" class="internal"><span class="codenumber">4.2.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="MX3.html" class="internal"><span class="codenumber">4.3</span> <span class="title">Solving Systems with Matrix Inverses (MX3)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX3.html#MX3-3" class="internal"><span class="codenumber">4.3.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX3.html#MX3-4" class="internal"><span class="codenumber">4.3.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX3.html#MX3-5" class="internal"><span class="codenumber">4.3.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX3.html#MX3-6" class="internal"><span class="codenumber">4.3.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-exercises"><div class="toc-title-box"><a href="MX3.html#MX3-7" class="internal"><span class="codenumber">4.3.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX3.html#MX3-8" class="internal"><span class="codenumber">4.3.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX3.html#MX3-9" class="internal"><span class="codenumber">4.3.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="MX4.html" class="internal"><span class="codenumber">4.4</span> <span class="title">Row Operations as Matrix Multiplication (MX4)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX4.html#MX4-3" class="internal"><span class="codenumber">4.4.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX4.html#MX4-4" class="internal"><span class="codenumber">4.4.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX4.html#MX4-5" class="internal"><span class="codenumber">4.4.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX4.html#MX4-6" class="internal"><span class="codenumber">4.4.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-exercises"><div class="toc-title-box"><a href="MX4.html#MX4-7" class="internal"><span class="codenumber">4.4.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="MX4.html#MX4-8" class="internal"><span class="codenumber">4.4.6</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
</ul>
</li>
<li class="toc-item toc-chapter">
<div class="toc-title-box"><a href="GT.html" class="internal"><span class="codenumber">5</span> <span class="title">Geometric Properties of Linear Maps (GT)</span></a><button class="toc-expander toc-chevron-surround" title="Expand chapter"><span class="icon material-symbols-outlined" aria-hidden="true">chevron_left</span></button></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="GT1.html" class="internal"><span class="codenumber">5.1</span> <span class="title">Row Operations and Determinants (GT1)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT1.html#GT1-3" class="internal"><span class="codenumber">5.1.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT1.html#GT1-4" class="internal"><span class="codenumber">5.1.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT1.html#GT1-5" class="internal"><span class="codenumber">5.1.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT1.html#GT1-6" class="internal"><span class="codenumber">5.1.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-exercises"><div class="toc-title-box"><a href="GT1.html#GT1-7" class="internal"><span class="codenumber">5.1.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT1.html#GT1-8" class="internal"><span class="codenumber">5.1.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT1.html#GT1-9" class="internal"><span class="codenumber">5.1.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="GT2.html" class="internal"><span class="codenumber">5.2</span> <span class="title">Computing Determinants (GT2)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT2.html#GT2-3" class="internal"><span class="codenumber">5.2.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT2.html#GT2-4" class="internal"><span class="codenumber">5.2.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT2.html#GT2-5" class="internal"><span class="codenumber">5.2.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT2.html#GT2-6" class="internal"><span class="codenumber">5.2.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-exercises"><div class="toc-title-box"><a href="GT2.html#GT2-7" class="internal"><span class="codenumber">5.2.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT2.html#GT2-8" class="internal"><span class="codenumber">5.2.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT2.html#GT2-9" class="internal"><span class="codenumber">5.2.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="GT3.html" class="internal"><span class="codenumber">5.3</span> <span class="title">Eigenvalues and Characteristic Polynomials (GT3)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT3.html#GT3-3" class="internal"><span class="codenumber">5.3.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT3.html#GT3-4" class="internal"><span class="codenumber">5.3.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT3.html#GT3-5" class="internal"><span class="codenumber">5.3.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT3.html#GT3-6" class="internal"><span class="codenumber">5.3.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-exercises"><div class="toc-title-box"><a href="GT3.html#GT3-7" class="internal"><span class="codenumber">5.3.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT3.html#GT3-8" class="internal"><span class="codenumber">5.3.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT3.html#GT3-9" class="internal"><span class="codenumber">5.3.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="GT4.html" class="internal"><span class="codenumber">5.4</span> <span class="title">Eigenvectors and Eigenspaces (GT4)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT4.html#GT4-3" class="internal"><span class="codenumber">5.4.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT4.html#GT4-4" class="internal"><span class="codenumber">5.4.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT4.html#GT4-5" class="internal"><span class="codenumber">5.4.3</span> <span class="title">Individual Practice</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT4.html#GT4-6" class="internal"><span class="codenumber">5.4.4</span> <span class="title">Videos</span></a></div></li>
<li class="toc-item toc-exercises"><div class="toc-title-box"><a href="GT4.html#GT4-7" class="internal"><span class="codenumber">5.4.5</span> <span class="title">Exercises</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT4.html#GT4-8" class="internal"><span class="codenumber">5.4.6</span> <span class="title">Mathematical Writing Explorations</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT4.html#GT4-9" class="internal"><span class="codenumber">5.4.7</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="GT5.html" class="internal"><span class="codenumber">5.5</span> <span class="title">Change of Basis (GT5)</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT5.html#GT5-3" class="internal"><span class="codenumber">5.5.1</span> <span class="title">Warm Up</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT5.html#GT5-4" class="internal"><span class="codenumber">5.5.2</span> <span class="title">Class Activities</span></a></div></li>
<li class="toc-item toc-subsection"><div class="toc-title-box"><a href="GT5.html#GT5-5" class="internal"><span class="codenumber">5.5.3</span> <span class="title">Sample Problem and Solution</span></a></div></li>
</ul>
</li>
</ul>
</li>
<li class="toc-item toc-backmatter">
<div class="toc-title-box"><a href="backmatter.html" class="internal"><span class="title">Back Matter</span></a><button class="toc-expander toc-chevron-surround" title="Expand backmatter"><span class="icon material-symbols-outlined" aria-hidden="true">chevron_left</span></button></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-appendix">
<div class="toc-title-box"><a href="applications.html" class="internal"><span class="codenumber">A</span> <span class="title">Applications</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="truss.html" class="internal"><span class="codenumber">A.1</span> <span class="title">Civil Engineering: Trusses and Struts</span></a></div>
<ul class="structural toc-item-list"><li class="toc-item toc-subsection"><div class="toc-title-box"><a href="truss.html#truss-2" class="internal"><span class="codenumber">A.1.1</span> <span class="title">Activities</span></a></div></li></ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="pagerank.html" class="internal"><span class="codenumber">A.2</span> <span class="title">Computer Science: PageRank</span></a></div>
<ul class="structural toc-item-list"><li class="toc-item toc-subsection"><div class="toc-title-box"><a href="pagerank.html#pagerank-2" class="internal"><span class="codenumber">A.2.1</span> <span class="title">Activities</span></a></div></li></ul>
</li>
<li class="toc-item toc-section">
<div class="toc-title-box"><a href="geology.html" class="internal"><span class="codenumber">A.3</span> <span class="title">Geology: Phases and Components</span></a></div>
<ul class="structural toc-item-list"><li class="toc-item toc-subsection"><div class="toc-title-box"><a href="geology.html#geology-2" class="internal"><span class="codenumber">A.3.1</span> <span class="title">Activities</span></a></div></li></ul>
</li>
</ul>
</li>
<li class="toc-item toc-appendix">
<div class="toc-title-box"><a href="appendix-extras.html" class="internal"><span class="codenumber">B</span> <span class="title">Appendix</span></a></div>
<ul class="structural toc-item-list">
<li class="toc-item toc-section"><div class="toc-title-box"><a href="sample-exercises.html" class="internal"><span class="codenumber">B.1</span> <span class="title">Sample Exercises with Solutions</span></a></div></li>
<li class="toc-item toc-section"><div class="toc-title-box"><a href="list-of-definitions.html" class="internal"><span class="codenumber">B.2</span> <span class="title">Definitions</span></a></div></li>
</ul>
</li>
<li class="toc-item toc-index"><div class="toc-title-box"><a href="backmatter-4.html" class="internal"><span class="title">Index</span></a></div></li>
</ul>
</li>
</ul></nav>
    '''
