#!/usr/bin/env python
# -*- coding: utf-8 -*- #
from __future__ import unicode_literals

AUTHOR = 'Jim Crist'
SITENAME = 'Marginally Stable'
SITEURL = ''

PATH = 'content'

TIMEZONE = u'America/Chicago'

DEFAULT_LANG = 'en'

THEME = u'theme'
DIRECT_TEMPLATES = (('tag', 'category', 'blog'))
PAGINATED_TEMPLATES = {'index': 10,
                       'blog': 10,
                       'tag': 10,
                       'category': 10}
PROFILE_IMAGE_URL = u'http://www.gravatar.com/avatar/85bba1ca66eb909a289448a90e88f53a?s=200'
TOP_IMAGE_URL = '/theme/images/logo.png'

AUTHOR_SAVE_AS = ''
AUTHORS_SAVE_AS = ''
TAGS_SAVE_AS = ''
CATEGORIES_SAVE_AS = ''
ARCHIVES_SAVE_AS = ''


#Plugins:
PLUGIN_PATHS = ['./plugins', '../pelican-plugins']
PLUGINS = ['ipynb.liquid']
NOTEBOOK_DIR = 'notebooks'
MARKUP = ['md', 'rst']

# Feed generation is usually not desired when developing
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None

# Blogroll
#Menu-y goodness
MENUITEMS = [('Blog', '/blog.html'), 
             ('About', '/pages/about.html'),
             ('Talks', '/pages/talks.html'),
             ('AIOS', 'https://github.com/jcrist/AIOs')]

DEFAULT_PAGINATION = 10
