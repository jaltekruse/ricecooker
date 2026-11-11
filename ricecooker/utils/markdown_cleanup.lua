--[[
Used by markdown_kpub.html_to_markdown when pandoc turns a web page into markdown: keeps the page's structure that
means something, and leaves out the wrappers, ids, classes and styles that are only there for the site's layout and
styling, which would clutter the markdown without meaning anything in a KPUB.

Divs are kept, as fenced divs (::: theorem), when a class says what kind of block they are, like a theorem, a
definition or an example, with that class only, and otherwise replaced by their content. Spans are replaced by their
content. Headings, links, images and code lose their ids, classes and attributes, except a code block's language, and
an image's alt text and title, which pandoc keeps outside of its attributes.
]]

-- Kinds of blocks worth keeping, matched against a class that is the kind, or the kind followed by "-like", as in
-- PreTeXt's classes, e.g. "theorem" matches "theorem" and "theorem-like", but not "theorem-wrapper"
local KINDS = {
  "theorem", "lemma", "corollary", "proposition", "conjecture", "axiom", "principle", "claim", "fact",
  "definition", "example", "exercise", "problem", "question", "activity", "exploration", "investigation",
  "project", "solution", "answer", "hint", "proof", "remark", "note", "warning", "caution", "tip", "important",
  "insight", "aside", "summary", "objectives", "outcomes", "goal", "assemblage", "algorithm", "callout",
  "blockquote", "epigraph", "poem", "abstract",
}

local function kind_of(classes)
  for _, class in ipairs(classes) do
    local lower = class:lower()
    for _, kind in ipairs(KINDS) do
      if lower == kind or lower == kind .. "-like" then
        return kind
      end
    end
  end
  return nil
end

local function plain(attr)
  return pandoc.Attr("", {}, {})
end

function Div(el)
  local kind = kind_of(el.classes)
  if kind then
    return pandoc.Div(el.content, pandoc.Attr("", { kind }, {}))
  end
  return el.content
end

function Span(el)
  return el.content
end

function Header(el)
  el.attr = plain()
  return el
end

function Link(el)
  el.attr = plain()
  return el
end

function Image(el)
  el.attr = plain()
  return el
end

function Code(el)
  el.attr = plain()
  return el
end

function CodeBlock(el)
  local language = el.classes[1]
  for _, class in ipairs(el.classes) do
    local name = class:match("^language%-(.+)$") or class:match("^lang%-(.+)$")
    if name then
      language = name
    end
  end
  el.attr = pandoc.Attr("", language and { language } or {}, {})
  return el
end

function Table(el)
  el.attr = plain()
  return el
end

function Figure(el)
  el.attr = plain()
  return el
end

-- pandoc writes a tight list's items without blank lines, which a fenced div in one needs to be read back, so a list
-- with a block like that in it is made loose
local function loosen(list)
  for _, item in ipairs(list.content) do
    for _, block in ipairs(item) do
      if block.t == "Div" then
        for _, item_again in ipairs(list.content) do
          for i, b in ipairs(item_again) do
            if b.t == "Plain" then
              item_again[i] = pandoc.Para(b.content)
            end
          end
        end
        return list
      end
    end
  end
  return list
end

function BulletList(el)
  return loosen(el)
end

function OrderedList(el)
  return loosen(el)
end
