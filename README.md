# iq2us-rss

Generate RSS feed document for Intelligence Squared US Debates.

This module provides functions to scrape the Intelligence Squared US Debates
sitemap to extract urls for each debate, and to scrape the debate pages to
extract the audio podcasts from them, and to generate an RSS document.

Both a python module and command-line utility are provided.

## Basic usage

    $ virtualenv env
    $ . env/bin/activate
    $ ./setup.py install

    $ iq2us-rss -o iq2us-debates.xml https://www.intelligencesquaredus.org/sitemap.xml

    # Or to collect only the unedited audio streams (accomplished by
    # merely selecting the longer stream)...

    $ iq2us-rss --audio unedited -o iq2us-unedited.xml https://www.intelligencesquaredus.org/sitemap.xml

## Develop

    $ virtualenv env
    $ . env/bin/activate
    $ ./setup.py develop

## Example

    import io
    import logging

    from iq2us_rss import iq2us_rss

    logging.basicConfig()

    url = "https://www.intelligencesquaredus.org/sitemap.xml"
    outfile = "iq2us-debates.xml"

    podcasts = iq2us_rss.find_debate_podcasts(url)
    output = io.open(outfile, "w", encoding="UTF-8")
    iq2us_rss.write_rss(output, url, podcasts)
    output.close()
