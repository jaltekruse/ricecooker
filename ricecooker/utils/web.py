"""
This module contains tools for parsing and handling HTML and other web content.
Note that we could not use html for the module name as recent versions of Python
include their own html module.
"""
import os

from bs4 import BeautifulSoup, SoupStrainer

PRESERVE_WHITESPACE_TAGS=["p", "pre", "code", "textarea"]

class HTMLParser:
    """
    HTMLParser contains a set of functions for parsing, scraping, and updating an HTML page.
    """

    def __init__(self, filename=None, html=None, soup=None):
        self.filename = filename
        self.html = html
        self.link_tags = {
            "a": "href",
            "audio": "src",
            "img": "src",
            "link": "href",
            "script": "src",
        }
        self.soup = soup

    def parse_html(self):
        only_tags = SoupStrainer(list(self.link_tags.keys()))
        if not self.soup:
            print("web.py PARSE HTML")
            self.soup = BeautifulSoup(self.html, features="lxml", preserve_whitespace_tags=PRESERVE_WHITESPACE_TAGS, parse_only=only_tags)
        return self.soup
    
    def get_links_in_parsed(self, soup, filename):
        self.soup = soup
        self.filename = filename
        self.html = "PLACEHOLDER"
        return self.get_links()

    def get_links(self):
        """
        Retrieves all links contained within the page.

        :return: A list of local and remote URLs in the page.
        """
        basename = None
        if self.html is None:
            basename = os.path.basename(self.filename)
            self.html = open(self.filename).read()
        soup = self.parse_html()

        extracted_links = []
        for tag_name in self.link_tags:
            tags = soup.find_all(tag_name)
            for tag in tags:
                link = tag.get(self.link_tags[tag_name])
                # don't include links to ourselves or # links
                # TODO: Should this part be moved to get_local_files instead?
                if (
                    link
                    and (basename and not link.startswith(basename))
                    and not link.strip().startswith("#")
                ):
                    if "?" in link:
                        link, query = link.split("?")
                    if "#" in link:
                        link, marker = link.split("#")
                    extracted_links.append(link)

        return extracted_links

    def get_local_files(self):
        """
        Returns a list of files that are contained in the same directory as the HTML page or in its subdirectories.

        :return: A list of local files
        """
        links = self.get_links()
        local_links = []
        for link in links:
            # NOTE: This technically fails to handle file:// URLs, but we're highly unlikely to see
            # file:// URLs in any distributed package, so this is simpler than parsing out the protocol.
            if "://" not in link:
                local_links.append(link)

        return local_links
    
    def replace_links_in_parsed(self, links_to_replace, soup, filename):
        self.soup = soup
        self.filename = filename
        self.html = "PLACEHOLDER"
        return self.replace_links(links_to_replace)

    def replace_links(self, links_to_replace):
        """
        Updates page links using the passed in replacement dictionary.

        :param links_to_replace: A dictionary of OriginalURL -> ReplacementURL key value pairs.
        :return: An HTML string of the page with all links replaced.
        """
        if self.html is None:
            self.html = open(self.filename).read()
        
        soup = self.parse_html()

        for tag_name in self.link_tags:
            tags = soup.find_all(tag_name)
            for tag in tags:
                link = tag.get(self.link_tags[tag_name])
                if link in links_to_replace:
                    tag[self.link_tags[tag_name]] = links_to_replace[link]

        # return soup.prettify()
        return str(soup)
        # return soup.encode(formatter="html")
