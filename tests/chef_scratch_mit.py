#!/usr/bin/env python
import os
import re
import tempfile

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
SOURCE_DOMAIN = "https://scratch.mit.edu/"
# SOURCE_ID = "thinkcspi_runestone_academy"  # an alphanumeric ID refering to this channel
# CHANNEL_TITLE = "How to Think Like a Computer Scientist, Interactive Edition"  # a humand-readbale title
SOURCE_ID = "Scratch_Block_Based_Programming"  # an alphanumeric ID refering to this channel
CHANNEL_TITLE = "Scratch - Block-Based Programming from MIT"  # a humand-readbale title

# youtube ids {'SGVgAV0v-Ww', 'Yxyx6KpKRzY', 'aqhREpceEMI', '3WgmLIsXFkI', '57dPVbnRouU', 'YK8QlIT3__M', 'xGSfiZt5cdw',
# 'GCLHuPBtLdQ', 'Fd4a8ktQURc', 'blTBEqybQmQ', 'vNfCfowr-pQ', 'HriDtn-0Dcw', 'LD-F4RODy-I', '1uQM-TVlaMo', 'LZ7H1X8ar9E',
# 'Ezve3QJv6Aw', 'Px1c-3GP-5o', '2KYixkCBXSQ', '4wKtB57J5J4', 'G86akhNFHZA'}

#SOURCE_ID = "jason_pretext_test_new_id"  # an alphanumeric ID refering to this channel
#CHANNEL_TITLE = "Jason PreteXt testing"
CHANNEL_LANGUAGE = "en"  # language of channel
DOMAIN = "http://localhost:8080/"


def add_subpages_from_pretext_toc(channel, list_url):
    title = "Scratch Block-Based Programming Editor"
    chapter_topic = TopicNode(source_id=title, title=title)

    destpath = tempfile.mkdtemp()
    source_dir = "/home/jason/src/scratch-built-editor/minimal-files"

    shutil.copytree(source_dir, destpath, dirs_exist_ok=True)
                    #,ignore=shutil.ignore_patterns(''))

    zippath = create_predictable_zip(destpath)

    # create an HTML5 app node
    html5app = HTML5AppNode(
        files=[HTMLZipFile(zippath)],
        title=title,
        thumbnail="https://lh3.googleusercontent.com/zwwddqxgFlP14DlucvBV52RUMA-cV3vRvmjf-iWqxuVhYVmB-l8XN9NDirb0687DSw=w300",
        source_id=SOURCE_DOMAIN,
        # license=None
        # getting a weird failure when I try to set a license
        # ricecooker.exceptions.InvalidNodeException: 2 - Euclidean Vectors (EV) (HTML5AppNode): 1 file: License is not a license object
        # in the debugger I'm confused, __bases__ shows this license object inherits from
        # (<class 'ricecooker.classes.licenses.License'>,), which appears to be the class it is checking for? but isinstance returns false
        # TODO JASON - seems like this assertion needs updating, it complains even if I have this, need to put it in the license itself below
        license_description="GNU Free Documentation License - Version 1.3",
        license=licenses.SpecialPermissionsLicense(copyright_holder="Scratch Foundation",
                                                   description="MIT License")
    )
    chapter_topic.add_child(html5app)
    channel.add_child(chapter_topic)

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
            channel, DOMAIN + "thinkcspy-3.html"
        )

        # potato_topic = TopicNode(
        #     source_id="List_of_potato_cultivars", title="Potatoes!"
        # )
        # channel.add_child(potato_topic)
        # add_subpages_from_wikipedia_list(
        #     potato_topic, "https://en.wikipedia.org/wiki/List_of_potato_cultivars"
        # )

        return channel

if __name__ == "__main__":
    """
    Call this script using:
        ./sushichef.py --token=YOURSTUDIOTOKENHERE9139139f3a23232
    """

    wikichef = WikipediaChef()
    wikichef.main()
