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

    org = {}
    grouper = scrapepdf.TextGrouper()
    grouper.add_patterns(
        (re.compile("DAVID CAMERON:"), "CAMERON"),
        (re.compile("NICK CLEGG:"), "CLEGG"),
        (re.compile("GORDON BROWN:"), "BROWN"),
        (re.compile("ADAM BOULTON:"), "INTERVIEWER"),
        (re.compile("ALASTAIR STEWART:"), "INTERVIEWER"),
        (re.compile("AUDIENCE MEMBER:"), "AUDIENCE"),
    )

    for num, page in enumerate(doc.pages()):
        if num < 1:
            # Skip introduction page
            continue
        grouper.clear_areas()
        grouper.group(doc.text(page=page))
        #grouper.display()
        #grouper.display_full()
        for area in grouper.areas:
            yield area

class Speech(object):
    def __init__(self, speaker, words=u''):
        self.speaker = speaker
        self.words = words

    def add(self, words):
        self.words = self.words.strip() + u" " + words

    def __repr__(self):
        return 'Speech(%r, %r)' % (self.speaker, self.words)

def find_speeches(filename):
    speeches = []
    for area in iter_areas(filename):
        for line in area.lines:
            for item in line:
                itemtype = item.props.get('type', None)
                if itemtype is not None:
                    speeches.append(Speech(itemtype))
                else:
                    speeches[-1].add(item.text)
    return speeches

if __name__ == '__main__':
    speeches = find_speeches(sys.argv[1])
    print(json.dumps(speeches, indent=4, default=lambda s: (s.speaker, s.words)))
