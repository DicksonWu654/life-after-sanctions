"""Namespace-independent OFAC XML and Recent Actions text parsers."""
from __future__ import annotations
import io
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

def local(tag):
    return tag.rsplit('}', 1)[-1]

def simple_xml(body):
    entries = {}
    for _, el in ET.iterparse(io.BytesIO(body), events=('end',)):
        tag = local(el.tag)
        if tag != 'sdnEntry':
            continue
        def vals(name):
            return [x.text or '' for x in el.iter() if local(x.tag) == name]
        def val(name):
            return next(iter(vals(name)), '')
        uid = val('uid')
        name = val('lastName')
        first = next((x.text for x in el if local(x.tag) == 'firstName'), '')
        if first:
            name += ', ' + first
        ids = []
        aliases = []
        for alias in el.iter():
            if local(alias.tag) == 'aka':
                fields = {local(x.tag): x.text or '' for x in alias}
                alias_name = fields.get('lastName', '')
                if fields.get('firstName'):
                    alias_name += ', ' + fields['firstName']
                if alias_name:
                    aliases.append(alias_name)
        for ident in el.iter():
            if local(ident.tag) != 'id':
                continue
            fields = {local(x.tag): x.text or '' for x in ident}
            typ = fields.get('idType', '')
            if typ.startswith('Digital Currency Address - '):
                ids.append((typ.split(' - ', 1)[1].strip(), fields.get('idNumber', ''), fields.get('uid', '')))
        entries[uid] = dict(sdn_uid=uid, sdn_name=name, sdn_type=val('sdnType').lower(),
                            programs=';'.join(sorted(set(vals('program')))), ids=ids, aliases=aliases)
        el.clear()
    return entries

def advanced_xml(body):
    types, rows = {}, []
    issue = ''
    for _, el in ET.iterparse(io.BytesIO(body), events=('end',)):
        tag = local(el.tag)
        if tag == 'DateOfIssue':
            vals = {local(x.tag): x.text for x in el}
            issue = f'{int(vals["Year"]):04}-{int(vals["Month"]):02}-{int(vals["Day"]):02}'
        if tag == 'FeatureType' and (el.text or '').startswith('Digital Currency Address - '):
            types[el.attrib['ID']] = el.text.split(' - ', 1)[1].strip()
        if tag == 'DistinctParty':
            uid = el.attrib['FixedRef']
            for feature in el.iter():
                if local(feature.tag) != 'Feature' or feature.attrib.get('FeatureTypeID') not in types:
                    continue
                ticker = types[feature.attrib['FeatureTypeID']]
                for detail in feature.iter():
                    if local(detail.tag) == 'VersionDetail' and detail.text:
                        rows.append(dict(sdn_uid=uid, ticker=ticker, address=detail.text.strip(),
                                         feature_id=feature.attrib['ID']))
            el.clear()
        elif tag in ('Location', 'IDRegDocument', 'SanctionsEntry', 'ProfileRelationship'):
            el.clear()
    return rows, types, issue

class ActionHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bits = []
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag in ('h1', 'h2', 'h3', 'h4', 'p', 'br', 'div'):
            self.bits.append('\n')
        if tag == 'a':
            href = dict(attrs).get('href')
            if href:
                self.links.append(href)
    def handle_endtag(self, tag):
        if tag in ('h1', 'h2', 'h3', 'h4', 'p', 'div'):
            self.bits.append('\n')
    def handle_data(self, data):
        self.bits.append(data)

FEATURE_RE = re.compile(r'Digital Currency Address\s*[-–]\s*([A-Za-z0-9]+)\s+([^\s;<>(),]+)', re.I)

def action_html(body, date, url, raw_ref):
    html = body.decode('utf-8', 'replace')
    title_match = re.search(r'<h1\b[^>]*>(.*?)</h1>', html, re.S | re.I)
    p = ActionHTML()
    p.feed(title_match[1] if title_match else '')
    title = re.sub(r'\s+', ' ', ''.join(p.bits)).strip()
    # Avoid navigation, metadata and footer addresses.
    article = re.search(r'<article\b[^>]*>(.*?)</article>', html, re.S | re.I)
    p = ActionHTML()
    p.feed(article[1] if article else html)
    lines = [re.sub(r'\s+', ' ', x).strip() for x in ''.join(p.bits).splitlines() if x.strip()]
    section = ''
    mentions = []
    for line in lines:
        low = line.lower()
        if 'following' in low and ('added' in low or 'additions' in low):
            section = 'addition'
        elif 'following' in low and ('deletions' in low or 'removed' in low):
            section = 'deletion'
        elif ('following' in low and ('changes' in low or 'updates' in low)) or low.startswith('updated to:'):
            section = 'update'
        if FEATURE_RE.search(line):
          parts = re.split(r'\s*-\s*to\s*-\s*', line, flags=re.I)
          for part_i, part in enumerate(parts):
            part_section = ('update_before' if part_i == 0 else 'update_after') if len(parts) > 1 else section
            entity = part.split(';', 1)[0].split(' (', 1)[0].strip()
            # Program labels are bracketed in OFAC's entry text.
            programs = sorted(set(re.findall(r'\[([A-Z0-9_ -]+)\]', part)))
            for m in FEATURE_RE.finditer(part):
                mentions.append(dict(ticker=m[1].upper(), address=m[2].rstrip('.'),
                    entity=entity, programs=';'.join(programs), section=part_section,
                    date=date, url=url, title=title, raw_ref=raw_ref, text=part))
    return dict(date=date, url=url, title=title, mentions=mentions, lines=lines, links=p.links)

def patch_changes(body):
    ticker = None
    added, removed = [], []
    for line in body.decode('utf-8').splitlines():
        if line.startswith('diff --git '):
            m = re.search(r'b/sanctioned_addresses_([A-Z0-9]+)\.txt$', line)
            ticker = m[1] if m else None
        elif ticker and line.startswith(('+', '-')) and not line.startswith(('+++', '---')):
            value = line[1:].strip()
            if value:
                (added if line[0] == '+' else removed).append((ticker, value))
    return added, removed
