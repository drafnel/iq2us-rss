#!/usr/bin/env python

from setuptools import setup

setup(
    name="iq2us-rss",
    version="1.0.1",
    packages=["iq2us_rss"],
    install_requires=[
        "beautifulsoup4",
        "fuzzywuzzy",
        "iso8601",
        "requests",
        "urllib3",
    ],
    entry_points={
        'console_scripts': [
            'iq2us-rss = iq2us_rss.iq2us_rss:main',
        ],
    },
    author="Brandon Casey",
    author_email="drafnel@gmail.com",
    description="Generate RSS feed for Intelligence Squared US debate podcast",
    license="MIT",
    keywords="iq2us intelligence squared podcast rss",
    url="https://github.com/drafnel/iq2us-rss",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
    ],
)
