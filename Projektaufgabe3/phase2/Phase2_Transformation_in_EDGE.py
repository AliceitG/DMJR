import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

allowed_fields = {'author', 'title', 'pages', 'year', 'volume', 'journal', 'number', 'ee', 'url', 'booktitle', 'crossref'}


def normalize_input(text: str) -> str:
    return (text
        .replace('&uuml;', 'ü')
        .replace('&auml;', 'ä')
        .replace('&ouml;', 'ö')
        .replace('&Uuml;', 'Ü')
        .replace('&Auml;', 'Ä')
        .replace('&Ouml;', 'Ö')
        .replace('&szlig;', 'ß'))


def text_of(elem, tag):
    child = elem.find(tag)
    return (child.text or '').strip() if child is not None and child.text else ''


def venue_from_record(pub):
    key = pub.attrib.get('key', '').lower()
    booktitle = text_of(pub, 'booktitle').lower()
    journal = text_of(pub, 'journal').lower()

    if 'sigmod' in key or 'sigmod' in booktitle:
        return 'sigmod'
    if 'pvldb' in key or 'vldb' in journal:
        return 'vldb'
    if 'icde' in key or 'icde' in booktitle:
        return 'icde'
    if 'pacmmod' in key:
        return 'pacmmod'
    return 'unknown'


def publication_sid(pub):
    key = pub.attrib.get('key', '')
    return key.split('/')[-1] if key else pub.tag


def build_tree(input_path: Path, output_dir: Path):
    xml_text = normalize_input(input_path.read_text(encoding='utf-8'))
    src_root = ET.fromstring(xml_text)
    edge_root = ET.Element('bib')
    venue_nodes = {}
    year_nodes = {}

    for pub in src_root:
        venue = venue_from_record(pub)
        year = text_of(pub, 'year')
        pub_sid = publication_sid(pub)

        if venue not in venue_nodes:
            venue_nodes[venue] = ET.SubElement(edge_root, 'venue', {'name': venue})

        key = (venue, year)
        if key not in year_nodes:
            year_nodes[key] = ET.SubElement(venue_nodes[venue], 'year', {'value': year})

        pub_elem = ET.SubElement(year_nodes[key], pub.tag, {'key': pub_sid})

        for child in pub:
            if child.tag in allowed_fields:
                field = ET.SubElement(pub_elem, child.tag)
                field.text = (child.text or '').strip()

    output_dir.mkdir(parents=True, exist_ok=True)

    pretty_xml = minidom.parseString(ET.tostring(edge_root, encoding='utf-8')).toprettyxml(indent='  ')
    (output_dir / 'edge_model.xml').write_text(pretty_xml, encoding='utf-8')

    lines = ['bib']
    for venue in edge_root:
        lines.append(f"  {venue.attrib['name']}")
        for year in venue:
            lines.append(f"    {year.attrib['value']}")
            for pub in year:
                lines.append(f"      {pub.tag}: {pub.attrib['key']}")
                for field in pub:
                    lines.append(f"        {field.tag}: {field.text}")
    (output_dir / 'tree_preview.txt').write_text('\n'.join(lines), encoding='utf-8')

    print('\n'.join(lines))
    return edge_root


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python edge_transform_only_tree.py toy_example.txt [output_dir]')
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('output_tree')
    build_tree(input_path, output_dir)
