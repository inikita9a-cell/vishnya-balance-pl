"""Adapt old HTML report UI links to this server's current origin, without rewriting runs."""
import html
import re
from urllib.parse import parse_qs, urlsplit, urlunsplit


def public_report_links(document, origin, rid):
    destination = urlsplit(origin)
    if destination.scheme != 'https' or not destination.netloc:
        raise ValueError('PUBLIC_ORIGIN must be an HTTPS origin')
    def replace(match):
        source = urlsplit(html.unescape(match.group(1)))
        query = parse_qs(source.query)
        if query.get('run') != [rid] or query.get('page') not in (['report'], ['registry'], ['pivot']):
            return match.group(0)
        target = urlunsplit((destination.scheme,destination.netloc,'/',source.query,''))
        return 'href="' + html.escape(target,quote=True) + '"'
    return re.sub(r'href="([^"\n]+)"', replace, document)
