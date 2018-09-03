#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate RSS feed document for Intelligence Squared US Debates.

This module provides functions to scrape the Intelligence Squared US Debates
sitemap to extract urls for each debate, and to scrape the debate pages to
extract the audio podcasts from them, and to generate an RSS document.

Example:

    import io
    import logging

    from iq2us_rss import iq2us_rss

    logging.basicConfig()

    url = "https://www.intelligencesquaredus.org/sitemap.xml"
    outfile = "iq2us-debates.xml"

    podcasts = iq2us_rss.find_debate_podcasts(url)
    output = io.open(outfile, "w", encoding="UTF-8")
    iq2us_rss.write_rss(output, url, "iq2us debates", podcasts)
    output.close()
"""
import argparse
import cgi
import collections
import datetime
import io
import logging
import sys

import bs4
import iso8601
import requests
import urllib3.util.retry

if sys.version_info[0] < 3:
    from urlparse import urlparse
else:
    from urllib.parse import urlparse
    unicode = str


_logger = logging.getLogger(__name__)
_logger.addHandler(logging.NullHandler())


DEFAULT_TIMEOUT = 15


Debate = collections.namedtuple("Debate", ["url", "last_modified"])
"""Represents a debate page extracted from the iq2us sitemap.

:ivar url: debate url
:vartype url: str
:ivar last_modified: datestamp of last modification of debate page
:vartype last_modified: :class:`datetime.datetime`
"""


Podcast = collections.namedtuple("Podcast", ["title", "desc", "pubDate", "url", "type", "duration"])
"""Represents a podcast extracted from an iq2us debate page.

:ivar title: podcast title
:vartype title: str
:ivar desc: description of podcast
:vartype desc: str
:ivar pubDate: publication date, or None if not known
:vartype pubDate: :class:`datetime.datetime`
:ivar url: podcast audio url
:vartype url: str
:ivar type: mime type
:vartype type: str
:ivar duration: length of podcast audio in seconds
:vartype duration: int
"""


def get_parser():
    """Returns parser for standard command-line options.
    """
    parser = argparse.ArgumentParser(
        description="Generate RSS feed for debates on the iq2us website.")
    parser.add_argument("--log-level", default="INFO",
                        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
                        help="set logging level (default \"%(default)s\")")
    parser.add_argument("--audio", default="unedited",
                        choices=["all", "edited", "unedited"],
                        help="audio stream to extract (default \"%(default)s\")")
    parser.add_argument("--since", type=int,
                        help="ignore podcasts older than <SINCE> days")
    parser.add_argument("--sort", dest="sort", action="store_true",
                        default=True, help=argparse.SUPPRESS)
    parser.add_argument("--no-sort", dest="sort", action="store_false",
                        help="don't sort podcast entries by publication date")
    parser.add_argument("--title", default="[unofficial] Intelligence Squared U.S. Debates",
                        help="title of generated podcast rss feed (default \"%(default)s\")")
    parser.add_argument("-o", "--output", help="output filename")
    parser.add_argument("url", help="iq2us sitemap url e.g. " +
                        "\"https://www.intelligencesquaredus.org/sitemap.xml\"")

    return parser


def _get_retry_session():
    session = requests.Session()
    retry = urllib3.util.retry.Retry(
        total=6,
        read=3,
        connect=3,
        backoff_factor=0.3,
        status_forcelist=(500, 502, 504)
    )
    adapter = requests.adapters.HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def find_podcasts(url, timeout=DEFAULT_TIMEOUT, session=None):
    """Extract podcast(s) from an iq2us debate page.

    Scrapes iq2us debate page and extracts podcasts it finds.

    :param url: URL for iq2us debate.
    :type url: str
    :param timeout: connect and/or read timeout
    :type timeout: tuple(float, float) or float
    :param session: (optional) session to use
    :type session: :class:`requests.Session`

    :returns: generator for podcasts
    :rtype: :class:`Podcast`
    """
    _logger.info("scraping debate page (%s)", url)

    parts = urlparse(url)

    if parts.scheme == "file":
        _logger.debug("reading debate page from file %s", parts.path)
        body = open(parts.path)
    else:
        _logger.debug("retrieving debate page from url %s", url)

        if not session:
            session = _get_retry_session()

        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()

        body = resp.text

        resp.close()

    soup = bs4.BeautifulSoup(body, "html.parser")

    # Scrape debate description from the "div" tag having class "details"
    desc = ''.join(soup.find("div", class_="details").stripped_strings)

    # Try to use the published_time metadata as a proxy for debate date.
    pub_date_meta = soup.find("meta", property="article:published_time")
    pub_date = None
    if pub_date_meta:
        try:
            pub_date = iso8601.parse_date(pub_date_meta['content'])
        except ValueError:
            _logger.exception("failed parsing published_time as iso8601 date")
            pub_date = None

    # Podcast entries on the "debates" page are expected to look like this:
    # <div id='debate-podcasts'>
    #   <div class='wrapper'>
    #     <div class='node node-podcast col col-4 t-col-3' data-nid='7085'>
    #       <div class='panoply-podcast'>
    #         <div class='bottom'>
    #           <audio data-duration='3042' data-title='Should We Abolish the Death Penalty?' controls>
    #             <source  src='https://traffic.megaphone.fm/PNP6862751282.mp3' type='audio/mpeg'>
    #           </audio>
    #         </div>
    #       </div>
    #     </div>
    #     <div class='node node-podcast col col-4 t-col-3' data-nid='7085'>
    #       <div class='panoply-podcast'>
    #         <div class='bottom'>
    #           <audio data-duration='5734' data-title='Should We Abolish the Death Penalty? [Unedited]' controls>
    #             <source  src='https://traffic.megaphone.fm/ISQ7799258386.mp3?updated=1470153445' type='audio/mpeg'>
    #           </audio>
    #         </div>
    #       </div>
    #     </div>
    #   </div>
    # </div>
    for elem in soup.find_all(id="debate-podcasts"):
        for podcast in elem.find_all(class_="panoply-podcast"):
            for src in podcast.find_all("audio"):
                _logger.debug("found audio tag: %s", src)
                yield Podcast(unicode(src['data-title']), desc, pub_date,
                              unicode(src.source['src']), unicode(src.source['type']),
                              unicode(src['data-duration']))


def find_debates(url, timeout=DEFAULT_TIMEOUT, session=None):
    """Extract debate urls from iq2us sitemap.

    Scrapes iq2us sitemap and extracts debate urls.

    :param url: URL of iq2us sitemap.
    :type url: str
    :param timeout: connect and/or read timeout
    :type timeout: tuple(float, float) or float
    :param session: (optional) session to use
    :type session: :class:`requests.Session`

    :returns: generator for debate urls
    :rtype: :class:`Debate`
    """
    _logger.info("scraping iq2us sitemap (%s)", url)

    parts = urlparse(url)

    if parts.scheme == "file":
        body = open(parts.path)
    else:
        if not session:
            session = _get_retry_session()

        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()

        body = resp.text

        resp.close()

    soup = bs4.BeautifulSoup(body, "html.parser")

    debate_path = "/debates/"

    # "debates" entries in the sitemap are expected to look like this:
    # <url>
    #   <loc>https://www.intelligencesquaredus.org/debates/afghanistan-lost-cause</loc>
    #   <lastmod>2016-08-23T18:12Z</lastmod>
    #   <changefreq>never</changefreq>
    #   <priority>1.0</priority>
    # </url>
    for urltag in soup.find_all("url"):
        loc = urltag.loc
        if not loc:
            continue

        url_item = unicode(loc.string)

        parts = urlparse(url_item)
        if parts.path[:len(debate_path)] != debate_path:
            continue

        if urltag.lastmod:
            try:
                lastmod = iso8601.parse_date(urltag.lastmod.string)
            except ValueError:
                _logger.exception("failed parsing lastmod \"%s\" (%s)",
                                  urltag.lastmod.string, url_item)
                lastmod = datetime.datetime(1970, 1, 1, 0, 0, 0, 0, iso8601.UTC)
        else:
            lastmod = datetime.datetime(1970, 1, 1, 0, 0, 0, 0, iso8601.UTC)

        yield Debate(url_item, lastmod)


def all_debates(debates):
    """Debate filter returning all debates.
    """
    return debates


def all_podcasts(debate, podcasts):
    """Podcast filter returning all podcasts.
    """
    return podcasts


def find_debate_podcasts(url, debate_filter=all_debates,
                         podcast_filter=all_podcasts, timeout=DEFAULT_TIMEOUT,
                         session=None):
    """Extract debate podcasts from iq2us sitemap.

    Scrapes iq2us sitemap and extracts debate podcasts.

    :param url: URL for iq2us sitemap.
    :type url: str
    :param filter: (optional) podcast filter
    :type filter: function
    :param timeout: connect and/or read timeout
    :type timeout: tuple(float, float) or float
    :param session: (optional) session to use
    :type session: :class:`requests.Session`

    :returns: generator for debate podcasts
    :rtype: tuple of :class:`Debate` and :class:`Podcast`
    """
    if not session:
        session = _get_retry_session()

    for debate in debate_filter(find_debates(url, timeout=timeout, session=session)):

        _logger.info("found %s", debate)

        try:
            for podcast in podcast_filter(debate,
                                          find_podcasts(debate.url,
                                                        timeout=timeout,
                                                        session=session)):
                _logger.info("found %s", podcast)
                yield (debate, podcast)
        except requests.exceptions.RequestException as e:
            _logger.error("failed retrieving debate page %s: %s", debate, e)


def _get_content_length(url, timeout, session):
    """Return content length of content at url.
    """
    resp = session.head(url, timeout=timeout)
    resp.raise_for_status()

    while resp.is_redirect:
        resp = session.send(resp.next, timeout=timeout)
        resp.raise_for_status()

    for key in resp.headers:
        if key.lower() == 'content-length':
            return resp.headers[key]

    return 0


def write_rss(fh, url, title, podcast_tuples, get_content_length=True,
              timeout=DEFAULT_TIMEOUT, session=None):
    """Produce an rss feed for the podcast tuples.

    :param fh: output file handle
    :type fh: :class:`io.file`
    :param url: home page url
    :type url: str
    :param title: podcast title
    :type title: str
    :param podcast_tuples:
    :type podcast_tuples:
    """
    if url.endswith("/sitemap.xml"):
        base_url = url[:-len("sitemap.xml")]
    else:
        base_url = url

    now = datetime.datetime.utcnow()

    rfc822_format = "%a, %d %b %Y %H:%M:%S -0000"
    rfc822_time = now.strftime(rfc822_format)

    fh.write(u'<?xml version="1.0" encoding="UTF-8" ?>\n')
    fh.write(u'<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">\n')
    fh.write(u'<channel>\n')
    fh.write(u'  <title>{}</title>\n'.format(cgi.escape(title, quote=True)))
    fh.write(u"  <description>Intelligence Squared U.S. Debates bring Oxford-style debate to America – one motion, one moderator, two panelists for the motion and two against. From clean energy and the financial crisis, to the Middle East and the death of mainstream media, Intelligence Squared U.S. brings together the world's leading authorities on the day's most important issues. Join the debate online and cast your vote for each topic at www.iq2us.org.</description>\n")
    fh.write(u'  <link>{}</link>\n'.format(base_url))
    fh.write(u'  <language>en-us</language>\n')
    fh.write(u'  <image>\n')
    fh.write(u'    <url>http://static.megaphone.fm/podcasts/bcc042ec-fb48-11e5-b604-930d2eb6cae2/image/uploads_2F1482274927463-5ma333ntgbmg85er-552d6f3f61ced4ca865638c3f33802a3_2FIQ2-Panoply3.jpg</url>\n')
    fh.write(u'    <title>{}</title>\n'.format(cgi.escape(title, quote=True)))
    fh.write(u'    <link>{}</link>\n'.format(base_url))
    fh.write(u'  </image>\n')
    fh.write(u'  <lastBuildDate>{}</lastBuildDate>\n'.format(rfc822_time))
    fh.write(u'  <pubDate>{}</pubDate>\n'.format(rfc822_time))
    fh.write(u'  <generator>https://github.com/drafnel/iq2us-rss</generator>\n')
    fh.write(u'  <docs>https://validator.w3.org/feed/docs/rss2.html</docs>\n')
    fh.write(u'  <ttl>60</ttl>\n')

    if get_content_length and not session:
        session = _get_retry_session()

    for debate, podcast in podcast_tuples:
        pubdate = podcast.pubDate if podcast.pubDate else debate.last_modified

        if get_content_length:
            _logger.info("retrieving content length of podcast stream %s", podcast.url)
            try:
                content_length = _get_content_length(podcast.url, timeout, session)
            except requests.exceptions.RequestException as e:
                _logger.error("failed retrieving content length for %s: %s",
                              podcast, e)
                content_length = 0
        else:
            content_length = 0

        fh.write(u'  <item>\n')
        fh.write(u'    <title>{}</title>\n'.format(
            cgi.escape(podcast.title, quote=True)))
        fh.write(u'    <link>{}</link>\n'.format(
            cgi.escape(debate.url, quote=True)))
        fh.write(u'    <description>{}</description>\n'.format(
            cgi.escape(podcast.desc, quote=True)))
        fh.write(u'    <pubDate>{}</pubDate>\n'.format(
            pubdate.astimezone(iso8601.UTC).strftime(rfc822_format)))
        fh.write(u'    <enclosure url="{}" length="{}" type="{}" />\n'.format(
            podcast.url, content_length, podcast.type))
        fh.write(u'    <itunes:duration>{}</itunes:duration>\n'.format(
            podcast.duration))
        fh.write(u'  </item>\n')

    fh.write(u'</channel>\n')
    fh.write(u'</rss>\n')


def main():
    """iq2us main function.
    """
    logging.basicConfig()

    parser = get_parser()

    args = parser.parse_args()

    if args.log_level:
        _logger.setLevel(args.log_level)

    since = None
    if args.since:
        since = datetime.datetime.utcnow().replace(tzinfo=iso8601.UTC) - \
                datetime.timedelta(args.since)
        def debate_filter(debates):
            for debate in debates:
                if debate.last_modified < since:
                    continue
                yield debate
        _logger.info("ignoring debates older than %s", since.isoformat())
    else:
        debate_filter = all_debates

    if args.output:
        fh = io.open(args.output, "w", encoding="UTF-8")
    else:
        if sys.stdout.isatty():
            encoding = sys.stdout.encoding
        else:
            encoding = "UTF-8"
        fh = io.open(sys.stdout.fileno(), mode="w", encoding=encoding,
                     closefd=False)

    if args.audio == "unedited":
        if args.title == parser.get_default("title"):
            args.title += " [unedited]"
        def podcast_filter(_, podcasts):
            # Assume the longest podcast is the "unedited" one
            podcast_list = []
            for podcast in podcasts:
                if since and podcast.pubDate and podcast.pubDate < since:
                    continue
                podcast_list.append(podcast)
            if podcast_list:
                yield max(podcast_list, key=lambda podcast: podcast.duration)
    elif args.audio == "edited":
        if args.title == parser.get_default("title"):
            args.title += " [edited]"
        def podcast_filter(_, podcasts):
            # Assume the shortest podcast is the "edited" one
            podcast_list = []
            for podcast in podcasts:
                if since and podcast.pubDate and podcast.pubDate < since:
                    continue
                podcast_list.append(podcast)
            if podcast_list:
                yield min(podcast_list, key=lambda podcast: podcast.duration)
    else:
        if args.title == parser.get_default("title"):
            args.title += " [all-debates]"
        if args.since:
            def podcast_filter(_, podcasts):
                for podcast in podcasts:
                    if podcast.pubDate and podcast.pubDate < since:
                        continue
                    yield podcast
        else:
            podcast_filter = all_podcasts

    podcast_tuples = find_debate_podcasts(args.url, debate_filter=debate_filter,
                                          podcast_filter=podcast_filter)

    if args.sort:
        podcast_tuples = sorted(podcast_tuples,
                                key=lambda ent: \
                                    ent[1].pubDate if ent[1].pubDate else \
                                    ent[0].last_modified,
                                reverse=True)

    write_rss(fh, args.url, args.title, podcast_tuples)

    fh.close()

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
