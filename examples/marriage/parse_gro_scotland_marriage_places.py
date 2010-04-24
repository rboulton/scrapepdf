#!/usr/bin/env python

import os, sys
sys.path.insert(0, os.path.dirname(
    os.path.dirname(
        os.path.dirname(os.path.realpath(__file__))
    )
))
try:
    import simplejson as json
except ImportError:
    import json
import re
import scrapepdf

def iter_areas(filename):
    import sys
    doc = scrapepdf.PdfToHTMLOutputParser(open(filename))

    grouper = scrapepdf.TextGrouper()
    grouper.merge_char_width = 0.5
    grouper.merge_left_margin_only = True

    for num, page in enumerate(doc.pages()):
        grouper.clear_areas()
        grouper.group(doc.text(page=page))
        #grouper.display()
        #grouper.display_full()
        for area in grouper.areas:
            if area.text.startswith('Footnotes:'):
                break
            yield area

def iter_rows(filename):
    """Iterate through all the rows
    """
    row = {}
    last_x = 0
    for area in iter_areas(filename):
        if area.text.startswith('Approved Places for Civil Marriage'):
            continue
        if area.left < last_x:
            yield row
            row = {}
        if area.left == last_x:
            row[area.left] = row[area.left] + u' ' + area.text
        else:
            row[area.left] = area.text
        last_x = area.left
    if len(row) != 0:
        yield row

def iter_rows_merged(filename):
    prev_row = None
    for row in iter_rows(filename):
        if prev_row is None:
            prev_row = row
            continue
        if len(row) == 5:
            # Have a complete new row, so yield the previous one
            yield prev_row
            prev_row = row
            continue
        for x, t in row.iteritems():
            closest_k = None
            for k in sorted(prev_row.keys()):
                if k <= x:
                    closest_k = k
                else:
                    break
            assert closest_k != None
            prev_row[closest_k] = prev_row[closest_k] + u' ' + t
    yield prev_row

def iter_rows_as_lists(filename):
    for row in iter_rows_merged(filename):
        row = list(row.iteritems())
        row.sort()
        yield [item[1].replace('\n', ' ') for item in row]

if __name__ == '__main__':
    data = [row for row in iter_rows_as_lists(sys.argv[1])]
    print json.dumps(data, indent=4)
