"""
Markdown as an editable source for KPUBs (Kolibri's HTML5 articles).

Web pages are turned into markdown (pandoc's flavour) by ``html_to_markdown``, keeping the meaning of the page: its
headings, lists, tables, figures, emphasis, links, the blocks that mean something, like theorems, definitions and
examples (as fenced divs), and its math, as the TeX it was written in, recovered from however the page shows it:
MathJax (2, 3 and 4), KaTeX, MathML with a TeX annotation, or TeX delimiters in the text. Images go in a media folder
next to the markdown.

``markdown_to_kpub`` turns markdown into a KPUB: an index.html, with each formula converted to MathML by MathJax
(``tex2mathml.js``), which understands far more LaTeX than pandoc's own converter, the images it uses, and the markdown
itself, as index.md, so that the KPUB can be edited and made again. Kolibri renders the MathML, natively or with
MathJax; the TeX also stays with each formula, as its MathML annotation.

Needs pandoc, and, for math, node with the mathjax-full package (version 3)::

    npm install -g mathjax-full@3
"""

import html
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from base64 import b64encode
from urllib.parse import urljoin
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from bs4 import Comment
from bs4 import NavigableString

from ricecooker.config import LOGGER

HERE = os.path.dirname(os.path.abspath(__file__))
TEX2MATHML_SCRIPT = os.path.join(HERE, "tex2mathml.js")
CLEANUP_FILTER = os.path.join(HERE, "markdown_cleanup.lua")

# Where the markdown goes in a KPUB, next to index.html
MARKDOWN_SOURCE = "index.md"
# Where html_to_markdown puts a page's images, next to the markdown
MEDIA_DIR = "media"
# pandoc's arguments to write the markdown: pandoc's markdown, with fenced divs for blocks that mean something, and
# without the raw HTML, ids, classes and attributes that make it hard to read and edit (see markdown_cleanup.lua)
MARKDOWN_WRITER_ARGS = [
    "--to=markdown-raw_html-native_divs-native_spans-link_attributes-header_attributes-smart",
    "--wrap=none",
    "--lua-filter={}".format(CLEANUP_FILTER),
]

MATHJAX_INSTALL_HINT = (
    "MathJax is needed to convert math to MathML: install node and MathJax with `npm install -g mathjax-full@3`, "
    "or set RICECOOKER_MATHJAX_PATH to a mathjax-full directory; see docs/installation.md"
)
PANDOC_INSTALL_HINT = (
    "pandoc is needed to convert between HTML and markdown; see docs/installation.md"
)
PANDOC_TIMEOUT = 300

# Elements of a page that aren't its content
NOISE_SELECTORS = [
    "script",
    "style",
    "noscript",
    "template",
    "link",
    "meta",
    "nav",
    "button",
    "form",
    "input",
    "select",
    "textarea",
    "iframe",
    "[aria-hidden='true']",
    "[hidden]",
]
# Elements whose text is code, where TeX delimiters aren't math
NO_MATH_ELEMENTS = {"code", "pre", "kbd", "samp", "script", "style", "textarea"}
# TeX delimiters in text: \( \), \[ \], $$ $$
TEX_IN_TEXT = re.compile(r"\\\((.+?)\\\)|\\\[(.+?)\\\]|\$\$(.+?)\$\$", re.DOTALL)
TEX_ANNOTATIONS = ("application/x-tex", "tex", "latex", "application/x-latex")
MATHJAX2_FRAME = re.compile(r"^MathJax-Element-\d+-Frame$")
# Formulas that only define macros, like PreTeXt's \lt, used by the formulas after them
DEFINITIONS = re.compile(
    r"^\s*\\(newcommand|renewcommand|providecommand|DeclareMathOperator|def|definecolor|require)\b"
)
# A formula's place in the page while pandoc turns it into markdown, as a word pandoc leaves as it is
PLACEHOLDER = "KPUBMATH{kind}{index:05d}X"
PLACEHOLDER_RE = re.compile(r"KPUBMATH([ID])(\d{5})X")
# pandoc's HTML for the math in markdown, with --mathjax
PANDOC_MATH_RE = re.compile(
    r'<span class="math (inline|display)">\\[(\[](.*?)\\[)\]]</span>', re.DOTALL
)


class MarkdownKPUBError(Exception):
    """Raised when a document can't be converted between HTML, markdown and KPUB."""


class MathJaxMissingError(MarkdownKPUBError):
    """Raised when node or MathJax, needed to convert math to MathML, isn't installed."""


class PandocError(MarkdownKPUBError):
    """Raised when pandoc is missing or fails."""


def run_pandoc(args, cwd=None, input_text=None):
    """Run pandoc with ``args``, returns what it writes to stdout"""
    if shutil.which("pandoc") is None:
        raise PandocError(PANDOC_INSTALL_HINT)
    try:
        result = subprocess.run(
            ["pandoc"] + args,
            cwd=cwd,
            input=input_text,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=PANDOC_TIMEOUT,
        )
    except subprocess.CalledProcessError as e:
        raise PandocError("pandoc failed: {}".format((e.stderr or "").strip()[:500]))
    except subprocess.TimeoutExpired as e:
        raise PandocError(str(e))
    return result.stdout


# HTML -> markdown


def _tex_annotation(math):
    """The TeX a MathML <math> element was made from, or None"""
    for annotation in math.find_all("annotation"):
        if (annotation.get("encoding") or "").lower() in TEX_ANNOTATIONS:
            return annotation.get_text()
    return None


def _is_display(element):
    return (element.get("display") or "").lower() in ("block", "true") or element.get(
        "mode"
    ) == "display"


def _replace_with_math(element, tex, display, formulas):
    """Put a placeholder for a formula, whose TeX is ``tex``, in place of ``element``"""
    tex = tex.strip()
    if not tex:
        element.decompose()
        return
    formulas.append((tex, display))
    element.replace_with(
        NavigableString(
            PLACEHOLDER.format(kind="D" if display else "I", index=len(formulas) - 1)
        )
    )


def _extract_katex(root, formulas):
    """KaTeX keeps the TeX in the MathML it adds for screen readers"""
    for element in root.select(".katex-display, .katex"):
        if element.parent is None or element.find_parent(class_="katex"):
            continue
        math = element.find("math")
        tex = _tex_annotation(math) if math else None
        if tex is not None:
            display = "katex-display" in (element.get("class") or [])
            _replace_with_math(element, tex, display, formulas)


def _extract_mathjax3(root, formulas):
    """
    MathJax 3 and 4 show math in mjx-container, with MathML for screen readers, and, in 4, the TeX in data-latex
    """
    for element in root.find_all("mjx-container"):
        if element.parent is None:
            continue
        display = (element.get("display") or "") == "true"
        math = element.find("math")
        shown = element.find("mjx-math", recursive=False)
        tex = element.get("data-latex") or (shown.get("data-latex") if shown else None)
        if tex is None and math is not None:
            tex = _tex_annotation(math)
        if tex is not None:
            _replace_with_math(element, tex, display, formulas)
        elif math is not None:
            # pandoc turns MathML into TeX itself
            if display:
                math["display"] = "block"
            element.replace_with(math)
        else:
            element.decompose()


def _extract_mathjax2(root, formulas):
    """MathJax 2 keeps the TeX in a script, after the math it shows (and a preview)"""
    shown = (
        ".MathJax_Preview, .MathJax_Display, span.MathJax, .MathJax_SVG, .MathJax_CHTML"
    )
    for element in root.select(shown) + root.find_all(id=MATHJAX2_FRAME):
        if element.parent is not None:
            element.decompose()
    for script in root.find_all("script", type=re.compile(r"^math/tex")):
        display = "mode=display" in script["type"]
        _replace_with_math(script, script.get_text(), display, formulas)


def _extract_mathml(root, formulas):
    """MathML that has its TeX"""
    for math in root.find_all("math"):
        tex = _tex_annotation(math)
        if tex is not None:
            _replace_with_math(math, tex, _is_display(math), formulas)


def _split_tex_in_text(text, formulas):
    """The pieces of a text, with placeholders for the TeX in it"""
    pieces = []
    last = 0
    for match in TEX_IN_TEXT.finditer(str(text)):
        pieces.append(NavigableString(str(text)[last : match.start()]))
        inline, display, dollars = match.groups()
        tex = next(group for group in (inline, display, dollars) if group is not None)
        formulas.append((tex.strip(), inline is None))
        kind = "I" if inline is not None else "D"
        pieces.append(
            NavigableString(PLACEHOLDER.format(kind=kind, index=len(formulas) - 1))
        )
        last = match.end()
    pieces.append(NavigableString(str(text)[last:]))
    return pieces


def _extract_tex_in_text(root, formulas):
    """TeX in the page's text, which MathJax would typeset in a browser"""
    for text in list(root.find_all(string=TEX_IN_TEXT)):
        if isinstance(text, Comment) or any(
            parent.name in NO_MATH_ELEMENTS for parent in text.parents
        ):
            continue
        for piece in _split_tex_in_text(text, formulas):
            text.insert_before(piece)
        text.extract()


def _extract_math(root, formulas):
    """
    Replace the page's math with placeholders, adding each formula's TeX, and whether it is displayed, to ``formulas``
    """
    # MathJax 3 before MathJax 2, whose output shares the MathJax class
    for extract in (
        _extract_katex,
        _extract_mathjax3,
        _extract_mathjax2,
        _extract_mathml,
        _extract_tex_in_text,
    ):
        extract(root, formulas)


def _blocks_as_divs(root):
    """
    pandoc leaves out the <article>, <aside> and <details> elements around blocks like theorems, activities and hints,
    make them divs, which it keeps, with their classes, for markdown_cleanup.lua to keep those that mean something
    """
    for element in root.find_all(["article", "aside", "details"]):
        classes = list(element.get("class") or [])
        if element.name == "aside":
            classes.append("aside")
        element.name = "div"
        element.attrs = {"class": classes} if classes else {}
    for summary in root.find_all("summary"):
        summary.name = "p"


def _inline_svgs(soup, root):
    """pandoc leaves out <svg> elements, show them as images instead"""
    for svg in root.find_all("svg"):
        if svg.parent is None or svg.find_parent("svg"):
            continue
        if not svg.get("xmlns"):
            svg["xmlns"] = "http://www.w3.org/2000/svg"
        data = b64encode(str(svg).encode("utf-8")).decode("ascii")
        img = soup.new_tag("img", src="data:image/svg+xml;base64," + data)
        label = svg.get("aria-label") or (svg.title.get_text() if svg.title else "")
        if label:
            img["alt"] = label
        svg.replace_with(img)


def _download_images(root, base_url, fetch):
    """Download the page's images that are on the web, for pandoc to put in the media folder with the others"""
    for img in root.find_all("img", src=True):
        src = img["src"]
        if src.startswith("data:"):
            continue
        url = urljoin(base_url, src) if base_url else src
        if urlparse(url).scheme not in ("http", "https"):
            continue
        try:
            content = fetch(url)
        except Exception as e:  # noqa: BLE001 a page is still worth having without one of its images
            LOGGER.warning("Could not download image {}: {}".format(url, e))
            content = None
        if not content:
            img["src"] = url
            continue
        mimetype = mimetypes.guess_type(urlparse(url).path)[0] or "image/png"
        img["src"] = "data:{};base64,{}".format(
            mimetype, b64encode(content).decode("ascii")
        )


def _default_fetch(url):
    import requests

    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def _math_markdown(tex, display):
    if display:
        # a blank line would end the paragraph the formula is in
        tex = "\n".join(line for line in tex.splitlines() if line.strip())
        return "$${}$$".format(tex)
    # pandoc only reads $...$ as math when there's no space just inside the dollars
    return "${}$".format(" ".join(tex.split()))


def _page_content(soup, content_selector, exclude_selector):
    """The element with the page's content, without what isn't content"""
    root = soup.select_one(content_selector) if content_selector else None
    if root is None:
        articles = soup.find_all("article")
        root = (
            soup.find("main")
            or (articles[0] if len(articles) == 1 else None)
            or soup.body
            or soup
        )
    noise = NOISE_SELECTORS + ([exclude_selector] if exclude_selector else [])
    for element in root.select(", ".join(noise)):
        if element.parent is not None:
            element.decompose()
    # headings and links with nothing to read in them, like icons the site adds
    for element in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "a"]):
        if (
            element.parent is not None
            and not element.get_text().strip()
            and not element.find("img")
        ):
            element.decompose()
    for comment in root.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    return root


def _rename_svgz(resource_dir, markdown):
    """pandoc names SVG images .svgz, which browsers take to be compressed"""
    media = os.path.join(resource_dir, MEDIA_DIR)
    if not os.path.isdir(media):
        return markdown
    for name in os.listdir(media):
        if name.endswith(".svgz"):
            svg = name[: -len("z")]
            os.replace(os.path.join(media, name), os.path.join(media, svg))
            markdown = markdown.replace(
                "{}/{}".format(MEDIA_DIR, name), "{}/{}".format(MEDIA_DIR, svg)
            )
    return markdown


def _restore_math(markdown, formulas):
    """Put the formulas back in place of their placeholders, as TeX, with the macro definitions first"""

    def restore(match):
        tex, display = formulas[int(match.group(2))]
        if DEFINITIONS.match(tex):
            return ""
        return _math_markdown(tex, display)

    markdown = PLACEHOLDER_RE.sub(restore, markdown)
    # Macro definitions, wherever they were in the page, go first, for the formulas that use them
    definitions = list(
        dict.fromkeys(tex for tex, _ in formulas if DEFINITIONS.match(tex))
    )
    if definitions:
        markdown = _math_markdown("\n".join(definitions), True) + "\n\n" + markdown
    return markdown


def html_to_markdown(
    html_text,
    resource_dir,
    base_url=None,
    content_selector=None,
    exclude_selector=None,
    fetch=None,
):
    """
    Markdown for a web page, keeping its content and the meaning of its structure, with its math as the TeX it was
    written in, and its images in a media folder in ``resource_dir``, where the markdown is meant to be kept.

    ``content_selector`` picks the page's content, by CSS selector, by default its <main>, or its only <article>, or
    its <body>, and ``exclude_selector`` leaves out parts of it that aren't, like controls the site adds. Images on
    the web are downloaded, resolved against ``base_url``, with ``fetch(url) -> bytes``.
    """
    os.makedirs(resource_dir, exist_ok=True)
    soup = BeautifulSoup(html_text, "html.parser")
    formulas = []
    # first, as MathJax 2's TeX is in scripts, which are removed with the rest of what isn't content, and macro
    # definitions can be outside of the content
    _extract_math(soup, formulas)
    root = _page_content(soup, content_selector, exclude_selector)
    _blocks_as_divs(root)
    _inline_svgs(soup, root)
    _download_images(root, base_url, fetch or _default_fetch)

    content = (
        root.decode_contents() if root.name in ("body", "[document]") else str(root)
    )
    markdown = run_pandoc(
        ["--from=html"]
        + MARKDOWN_WRITER_ARGS
        + ["--extract-media={}".format(MEDIA_DIR)],
        cwd=resource_dir,
        input_text="<!DOCTYPE html><html><body>{}</body></html>".format(content),
    )
    return _restore_math(_rename_svgz(resource_dir, markdown), formulas)


# TeX -> MathML


def _node_environment():
    """The environment node runs tex2mathml.js in, where it can find MathJax"""
    env = dict(os.environ)
    mathjax_path = os.environ.get("RICECOOKER_MATHJAX_PATH")
    if mathjax_path:
        env["MATHJAX_FULL_PATH"] = mathjax_path
        return env
    paths = [p for p in env.get("NODE_PATH", "").split(os.pathsep) if p]
    npm = shutil.which("npm")
    if npm:
        try:
            global_root = subprocess.run(
                [npm, "root", "-g"], capture_output=True, encoding="utf-8", timeout=60
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            global_root = ""
        if global_root:
            paths.append(global_root)
    env["NODE_PATH"] = os.pathsep.join(paths)
    return env


def mathjax_available():
    """Whether MathJax is installed, to convert TeX to MathML"""
    try:
        tex_to_mathml([("x", False)])
    except MathJaxMissingError:
        return False
    return True


def tex_to_mathml(formulas):
    """
    MathML for each of ``formulas``, a list of ``(tex, display)``, converted by MathJax, with the TeX as its
    annotation, or None for those MathJax can't convert
    """
    if not formulas:
        return []
    node = shutil.which("node")
    if node is None:
        raise MathJaxMissingError(MATHJAX_INSTALL_HINT)
    try:
        result = subprocess.run(
            [node, TEX2MATHML_SCRIPT],
            input=json.dumps(
                [{"tex": tex, "display": display} for tex, display in formulas]
            ),
            capture_output=True,
            encoding="utf-8",
            env=_node_environment(),
            timeout=PANDOC_TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        raise MarkdownKPUBError(str(e))
    if result.returncode != 0:
        if "Cannot find module" in result.stderr:
            raise MathJaxMissingError(MATHJAX_INSTALL_HINT)
        raise MarkdownKPUBError(
            "Converting math to MathML failed: {}".format(result.stderr.strip()[:500])
        )
    mathml = []
    for (tex, _), converted in zip(formulas, json.loads(result.stdout)):
        if "error" in converted:
            LOGGER.warning(
                "MathJax could not convert {!r}, showing it as TeX: {}".format(
                    tex, converted["error"]
                )
            )
            mathml.append(None)
        else:
            mathml.append(converted["mathml"])
    return mathml


def _pandoc_mathml(formulas):
    """MathML for each of ``formulas`` from pandoc's own converter, for when MathJax isn't installed"""
    markdown = "\n\n".join(
        "PANDOCFORMULA " + _math_markdown(tex, display) for tex, display in formulas
    )
    converted = run_pandoc(
        ["--from=markdown", "--to=html5", "--mathml", "--wrap=none"],
        input_text=markdown,
    )
    paragraphs = re.findall(r"<p>PANDOCFORMULA (.*?)</p>", converted, re.DOTALL)
    if len(paragraphs) != len(formulas):
        raise MarkdownKPUBError("pandoc did not convert each formula")
    return [
        paragraph if paragraph.startswith("<math") else None for paragraph in paragraphs
    ]


_warned_mathjax_missing = False


def convert_math_to_mathml(html_text):
    """
    Replace the math in HTML from pandoc's --mathjax output, as TeX in <span class="math inline|display">, with
    MathML, converted by MathJax, or by pandoc when MathJax isn't installed
    """
    global _warned_mathjax_missing
    found = list(PANDOC_MATH_RE.finditer(html_text))
    if not found:
        return html_text
    formulas = [
        (html.unescape(match.group(2)), match.group(1) == "display") for match in found
    ]
    try:
        mathml = tex_to_mathml(formulas)
    except MathJaxMissingError:
        if not _warned_mathjax_missing:
            LOGGER.warning(
                "{}. Using pandoc's MathML, which leaves out some of LaTeX.".format(
                    MATHJAX_INSTALL_HINT
                )
            )
            _warned_mathjax_missing = True
        mathml = _pandoc_mathml(formulas)
    converted = iter(mathml)

    def replace(match):
        result = next(converted)
        if DEFINITIONS.match(html.unescape(match.group(2))):
            # it only defines macros for the formulas after it, there's nothing to show
            return ""
        if result is not None:
            return result
        # the TeX can't be converted, show it
        return '<code class="tex">{}</code>'.format(match.group(2))

    # the paragraphs that only had macro definitions in them
    return PANDOC_MATH_RE.sub(replace, html_text).replace("<p></p>", "")


# markdown -> KPUB

KPUB_PAGE = """<!DOCTYPE html>
<html{lang}>
<head>
<meta charset="utf-8">
<title>{title}</title>
</head>
<body>
{body}
</body>
</html>
"""


def _copy_local_images(body, markdown_dir, kpub_dir):
    """Copy the images the page uses, by paths relative to the markdown, into the KPUB, at the same paths"""
    for match in re.finditer(r'<img\b[^>]*\bsrc="([^"]+)"', body):
        src = html.unescape(match.group(1))
        if re.match(r"^[a-z][a-z0-9+.-]*:", src, re.IGNORECASE) or src.startswith("/"):
            if not src.startswith("data:"):
                LOGGER.warning(
                    "Image {} is not in the KPUB, it will need a connection to show".format(
                        src
                    )
                )
            continue
        source = os.path.normpath(os.path.join(markdown_dir, src))
        dest = os.path.normpath(os.path.join(kpub_dir, src))
        if not dest.startswith(os.path.normpath(kpub_dir) + os.sep):
            LOGGER.warning(
                "Image {} is outside the markdown's folder, leaving it out".format(src)
            )
            continue
        if os.path.isfile(source) and not os.path.exists(dest):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(source, dest)
        elif not os.path.exists(dest):
            LOGGER.warning("Image {} was not found".format(source))


def markdown_to_kpub(markdown, kpub_dir, markdown_dir=None, title=None, language=None):
    """
    Write a KPUB's files to ``kpub_dir``, from ``markdown``: index.html, with its math as MathML, the images it uses,
    from paths relative to ``markdown_dir``, and the markdown itself, as index.md, so the KPUB can be edited and made
    again. Returns the path of index.html.
    """
    os.makedirs(kpub_dir, exist_ok=True)
    body = run_pandoc(
        ["--from=markdown", "--to=html5", "--mathjax", "--wrap=none"],
        input_text=markdown,
    )
    body = convert_math_to_mathml(body)
    if markdown_dir:
        _copy_local_images(body, markdown_dir, kpub_dir)
    if title is None:
        heading = re.search(r"<h[1-6][^>]*>(.*?)</h[1-6]>", body, re.DOTALL)
        title = (
            re.sub(r"<[^>]+>", "", heading.group(1)).strip() if heading else "Untitled"
        )
    else:
        title = html.escape(title)
    page = KPUB_PAGE.format(
        lang=' lang="{}"'.format(html.escape(language)) if language else "",
        title=title,
        body=body,
    )
    index = os.path.join(kpub_dir, "index.html")
    with open(index, "w", encoding="utf-8") as f:
        f.write(page)
    with open(os.path.join(kpub_dir, MARKDOWN_SOURCE), "w", encoding="utf-8") as f:
        f.write(markdown)
    return index


def html_to_kpub(
    html_text,
    kpub_dir,
    base_url=None,
    content_selector=None,
    exclude_selector=None,
    fetch=None,
    title=None,
    language=None,
):
    """A KPUB, written to ``kpub_dir``, of a web page, made from markdown (see html_to_markdown and markdown_to_kpub)"""
    with tempfile.TemporaryDirectory() as resource_dir:
        markdown = html_to_markdown(
            html_text,
            resource_dir,
            base_url=base_url,
            content_selector=content_selector,
            exclude_selector=exclude_selector,
            fetch=fetch,
        )
        return markdown_to_kpub(
            markdown,
            kpub_dir,
            markdown_dir=resource_dir,
            title=title,
            language=language,
        )
