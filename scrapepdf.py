#!/usr/bin/env python
#
# Copyright (c) 2010 Richard Boulton
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""Scrape data from the output of "pdftohtml -xml"

"""

from lxml import etree
import re

class FontSpec(object):
    """A Font specification.

    Each specification has the attributes:

     - `size`: point size of font.
     - `family`: font family (eg, "Helvetica").
     - `color`: RGB colour of font.
     - `number`: The fontspec number assigned by pdftohtml.

    The colour can be accessed as "colour", too, for users of English spelling.

    """
    __slots__ = ('family', 'size', 'color', 'number')
    def __init__(self, atts, number):
        self.family = atts['family']
        self.size = float(atts['size'])
        self.color = atts['color']
        self.number = number

    @property
    def colour(self):
        return self.color

    def __str__(self):
        return "FontSpec(%d %s %s %s)" % (self.number, self.family, self.size,
                                          self.color)

    def __repr__(self):
        return "FontSpec({'number': %d, 'family': %r, 'size': %r, " \
               "'color': %r})" % (self.number, self.family, self.size,
                                  self.color)


class DimensionedElement(object):
    @property
    def top(self):
        return float(self.element.attrib['top'])

    @property
    def left(self):
        return float(self.element.attrib['left'])

    @property
    def bottom(self):
        return self.top + self.height

    @property
    def right(self):
        return self.left + self.width

    @property
    def width(self):
        return float(self.element.attrib['width'])

    @property
    def height(self):
        return float(self.element.attrib['height'])


class Text(DimensionedElement):
    """A piece of text, with associated formatting information.

    """
    def __init__(self, element, page, fontspec):
        self.element = element
        self.page = page
        self.fontspec = fontspec
        self.text = etree.tostring(self.element, method="text", encoding=unicode)
        self.props = {}
        DimensionedElement.__init__(self)

    @property
    def font(self):
        return int(self.element.attrib['font'])

    def __str__(self):
        return "Text(%s, %s, %s)" % (self.text, self.page.number, self.fontspec)

    def __repr__(self):
        return "<Text(%r, page=%s, fontspec=%r)>" % (etree.tostring(self.element, encoding=unicode), self.page.number, self.fontspec)


class Page(DimensionedElement):
    """A page.

    The element corresponding to the page is available as the `element`
    property.

    """
    def __init__(self, element):
        self.element = element
        DimensionedElement.__init__(self)

    @property
    def number(self):
        return self.element.attrib['number']

    def __str__(self):
        return "Page(%s)" % (self.number)

    def __repr__(self):
        return "<Page(%r)>" % etree.tostring(self.element, encoding=unicode)


class PdfToHTMLOutputParser(object):
    """Parse an XML document produced from pdftohtml.

    """
    def __init__(self, fd):
        self.fontspecs = {}
        self.tree = etree.parse(fd, etree.HTMLParser())

        for event, spec in etree.iterwalk(self.tree, tag='fontspec'):
            atts = spec.attrib
            fontid = int(atts['id'])
            assert fontid not in self.fontspecs
            self.fontspecs[fontid] = FontSpec(atts, fontid)

    def fontspec(self, fontid):
        """Get the fontspec for a fontspec ID number.

        """
        return self.fontspecs[int(fontid)]

    def pages(self):
        """Iterate over the pages in the document.

        """
        for event, page in etree.iterwalk(self.tree, tag='page'):
            yield Page(page)

    def text(self, page=None):
        """Get the text items.

        If `page` is supplied, it should be a Page (as returned by
        self.pages())

        """
        def text_for_page(page):
            for event, text in etree.iterwalk(page.element, tag='text'):
                fontid = text.attrib['font']
                yield Text(text, page, self.fontspec(text.attrib['font']))

        if page is None:
            for event, page in etree.iterwalk(self.tree, tag='page'):
                page = Page(page)
                for item in text_for_page(page):
                    yield(item)
        else:
            for item in text_for_page(page):
                yield(item)


def calc_lines(items):
    """Group a list of items into lines.

    Returns a list of lists of items.

    """
    # Cope with iterator inputs by forcing into a list.
    items = list(items)

    # Build a list of line centrepoints, and widths.  First we build a list of
    # the centrepoints and widths of all the items, then we iterate through
    # these and merge them together where the centrepoint of a line overlaps an
    # existing line width.

    centres = []
    for item in items:
        centres.append(((item.top + item.bottom) / 2,
                        (item.bottom - item.top) / 2))
    centres.sort()
    lines = []
    curline = centres[0]
    for line in centres:
        dist = line[0] - curline[0]
        if dist < max(line[1], curline[1]):
            curline = ((line[0] + curline[0]) / 2,
                        max(line[1], curline[1]))
        else:
            lines.append(curline)
            curline = line
    lines.append(curline)
    lines.sort()

    # Group elements into lines, by iterating through them in sorted
    # (top->bottom, left->right) order, assigning them to the first
    # relevant line.
    groups = []
    linenum = 0
    curgroup = None
    for item in sorted(items, key=lambda x: (x.top, x.left)):
        while linenum < len(lines):
            centre, wid = lines[linenum]
            if abs((item.top + item.bottom) / 2 - centre) < wid:
                # item sits on line, so add it.
                if curgroup is None:
                    curgroup = []
                    groups.append(curgroup)
                curgroup.append(item)
                break
            elif item.top < centre:
                # item is above the line, so we've somehow missed it
                # This should rarely happen, but could if we've computed a
                # centre-line too harshly.  Put the item on a line of its
                # own; not ideal, but better than losing it.
                groups.append([item])
                curgroup = None
                break
            curgroup = None
            linenum += 1
    return groups


class TextArea(object):
    def __init__(self, item):
        self.left = item.left
        self.right = item.right
        self.top = item.top
        self.bottom = item.bottom

        # Extra offsets to grab items to the left, right, top, bottom.
        self.grab = [0, 0, 0, 0]

        self.items = []
        self.lines = None # this is populated by self.assign_lines()
        self.props = {}
        self.add(item)

    def dist(self, item):
        """Return the distance between this area and a new item.

        """
        # Calculate the horizontal distance
        if self.left < item.left:
            # item is on the right: distance is from its left to my right
            hdist = item.left - self.right - self.grab[1]
        else:
            # item is on the left: distance is from its right to my left
            hdist = self.left - item.right - self.grab[0]
        if hdist < 0:
            hdist = 0

        # Calculate the vertical distance
        if self.top < item.top:
            # item is on the bottom: distance is from its top to my bottom
            vdist = item.top - self.bottom - self.grab[3]
        else:
            # item is on the top: distance is from its bottom to my top
            vdist = self.top - item.bottom - self.grab[2]
        if vdist < 0:
            vdist = 0

        return hdist, vdist, hdist + vdist

    def add(self, item):
        self.items.append(item)
        self.left = min(self.left, item.left)
        self.right = max(self.right, item.right)
        self.top = min(self.top, item.top)
        self.bottom = max(self.bottom, item.bottom)
        self.grab = [0, 0, 0, 0]
        for k, v in item.props.iteritems():
            if k == 'rhsfollow':
                self.grab[1] = float(v)
            if k not in self.props:
                self.props[k] = v

    def assign_lines(self):
        """Group the items into lines.

        """
        self.lines = calc_lines(self.items)

    def __str__(self):
        return "TextArea((%.1f, %.1f), (%.1f, %.1f))" % \
            (self.left, self.right, self.top, self.bottom)


class IgnoreItem(Exception):
    """Exception raised to indicate that an item should be ignored.

    """
    pass

def act_ignore_empty():
    """Cause empty items to be ignored.

    """
    def fn(item):
        if len(item.text.strip()) == 0:
            raise IgnoreItem
    return fn

def act_bullet():
    """Check for items which start with a bullet point.

    """
    def fn(item):
        ltext = item.text.lstrip()
        if ltext.startswith(u'\uf0b7'):
            item.props['startitem'] = True
            item.text = ltext[1:]
            if item.text.strip() == '':
                # There's no text after the bullet, so we should try to attach
                # to a following item.
                item.props['rhsfollow' ] = 300
    return fn

def act_weights():
    """Add properties based on font weights.

    """
    def fn(item):
        for child in item.element:
            tag = child.tag.lower()
            if tag == 'b':
                item.props['bold'] = True
            elif tag == 'i':
                item.props['italic'] = True
    return fn

def act_patterns(patterns):
    """Check for matches to known patterns.

    """
    def fn(item):
        text = item.text.strip()
        for pattern, item_type in patterns:
            if isinstance(pattern, basestring):
                if pattern.strip() == text:
                    item.props['type'] = item_type
                    break
            elif pattern.search(text):
                item.props['type'] = item_type
                break
    return fn

def act_colon_end():
    """Look for items which end with a colon, and mark them as wanting
    something to follow them on the right.

    """
    def fn(item):
        text = item.text.strip()
        if text.endswith(':'):
            item.props['rhsfollow'] = 300
    return fn


class TextGrouper(object):
    """Code to group text objects on a page into some kind of meaningful form.

    Various heuristics are used here, and can be controlled by a set of
    special functions which are run when items come in.

    """
    def __init__(self):
        self.areas = []
        self.patterns = []

        # Some special actions.
        # These consist of a callable, which can raise StopIteration to
        # indicate that no further special actions should be performed, or
        # raise IgnoreItem to cause the item to be ignored.  It may also modify
        # the item as desired (usually by adding items to item.props).

        self.special_fns = [
            act_ignore_empty(),
            act_weights(),
            act_patterns(self.patterns),
            act_bullet(),
            act_colon_end(),
        ]

    def add_patterns(self, *titles):
        self.patterns.extend(titles)

    def merge_item(self, item):
        """Merge an existing item into the nearest text area.

        """
        if len(self.areas) == 0:
            self.areas.append(TextArea(item))
            return

        closest = None
        for num, area in enumerate(self.areas):
            if item.props.get('type', None) != None:
                if area.props.get('type', None) != item.props['type']:
                    continue
            hdist, vdist, dist = area.dist(item)
            if closest is None:
                closest = (num, dist, hdist, vdist)
                continue
            if closest[1] > dist:
                closest = (num, dist, hdist, vdist)

        if closest is None or \
           closest[2] > float(item.fontspec.size) or \
           closest[3] > item.height:
            area = TextArea(item)
            self.areas.append(area)
        else:
            area = self.areas[closest[0]]
            area.add(item)

    def group(self, textitems):
        """Group the supplied list of items into TextArea objects.

        """
        # Sort the items into lines, then flatten that list to just get a list
        # in sorted order by line then x pos.
        text_in_lines = []
        for line in calc_lines(textitems):
            line.sort(key = lambda x: x.left)
            text_in_lines.extend(line)

        for item in text_in_lines:
            stext = item.text.strip()
            action = None
            # Add a space for additional properties on the item
            item.props = {}

            # Apply the special actions
            ignore = False
            try:
                for special_fn in self.special_fns:
                    special_fn(item)
            except StopIteration:
                pass
            except IgnoreItem:
                continue

            # Merge the item into the existing groups.
            self.merge_item(item)

        # Tidy up each area, putting content into lines.
        for area in self.areas:
            area.assign_lines()

    def display(self):
        for area in self.areas:
            print '{'
            for line in area.lines:
                print '  ' + str([(item.text, item.props) for item in line])
            print '}'

    def display_full(self):
        for area in self.areas:
            print area, area.props
            for line in area.lines:
                print '  ['
                for item in line:
                    print "   ", repr(item.text), item.fontspec, item.props
                print '  ]'


if __name__ == '__main__':
    import sys
    fd = open(sys.argv[1])
    doc = PdfToHTMLOutputParser(fd)
    for page in doc.pages():
        grouper = TextGrouper()
        grouper.add_patterns(
            ("Address(es) in UK", "colhead"),
            ("Contact", "colhead"),
            ("Offices outside UK", "heading"),
            (re.compile("providing PA consultancy services this quarter",
                        re.IGNORECASE), "heading"),
            (re.compile("clients for whom", re.IGNORECASE), "heading"),
        )
        grouper.group(doc.text(page))
        grouper.display()
        #grouper.display_full()
        print
