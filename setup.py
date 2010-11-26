#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2010 Johannes Weißl
# License GPLv3+:
# GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.
# This is free software: you are free to change and redistribute it.
# There is NO WARRANTY, to the extent permitted by law

from distutils.core import setup
import muttlearn

setup(name = 'muttlearn',
      version = muttlearn.__version__,
      description = 'Instead of manually switching profiles, let muttlearn figure it out for you!',
      author = u'Johannes Weißl',
      author_email = 'jargon@molb.org',
      url = 'https://github.com/weisslj/muttlearn',
      packages = ['muttlearn'],
      scripts = ['bin/muttlearn'],
      license = 'GNU GPL v3',
      classifiers = [
          'Development Status :: 4 - Beta',
          'Environment :: Console',
          'Intended Audience :: Developers',
          'Intended Audience :: System Administrators',
          'License :: OSI Approved :: GNU General Public License (GPL)',
          'Natural Language :: English',
          'Operating System :: POSIX',
          'Programming Language :: Python :: 2.5',
          'Programming Language :: Python :: 2.6',
          'Programming Language :: Python :: 2.7',
          'Topic :: Communications :: Email',
          'Topic :: Utilities',
    ]
)
