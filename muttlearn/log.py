# -*- coding: utf-8 -*-

# Copyright (C) 2010-2017 Johannes Weißl
# License GPLv3+:
# GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.
# This is free software: you are free to change and redistribute it.
# There is NO WARRANTY, to the extent permitted by law

"""Logging / debug / error functionality."""

import sys
import os.path
import locale

preferredencoding = locale.getpreferredencoding()
verbosity = 0

def info(msg, *args, **kwargs):
    """Output info message to stdout."""
    msg = msg % args
    if type(msg) == unicode:
        msg = msg.encode(preferredencoding)
    end = kwargs['end'] if 'end' in kwargs else '\n'
    sys.stdout.write(msg+end)
    sys.stdout.flush()

def warn(msg, *args, **kwargs):
    """Output warning message to stderr."""
    msg = msg % args
    if type(msg) == unicode:
        msg = msg.encode(preferredencoding)
    end = kwargs['end'] if 'end' in kwargs else '\n'
    if end == '\n':
        msg = 'warning: ' + msg
    sys.stderr.write(msg + end)
    sys.stderr.flush()

def debug(msg, *args, **kwargs):
    """Output debug message to stderr if verbosity >= named parameter 'v'."""
    v = kwargs['v'] if 'v' in kwargs else 1
    if verbosity < v:
        return
    msg = msg % args
    if type(msg) == unicode:
        msg = msg.encode(preferredencoding)
    end = kwargs['end'] if 'end' in kwargs else '\n'
    if end == '\n':
        msg = 'debug: ' + msg
    sys.stderr.write(msg + end)
    sys.stderr.flush()

def error(msg, *args, **kwargs):
    """Output an error message to stderr and exit."""
    msg = msg % args
    if type(msg) == unicode:
        msg = msg.encode(preferredencoding)
    end = kwargs['end'] if 'end' in kwargs else '\n'
    if end == '\n':
        msg = u'muttlearn: %s' % msg
    sys.stderr.write(msg + end)
    sys.stderr.flush()
    sys.exit(1)

class PercentStatus(object):
    def __init__(self, all, prefix=''):
        self.num = 0
        self.all = all
        self.msg = ''
        if prefix:
            info('%s', prefix, end='')
    def inc(self, num=1):
        self.num += num
    def update(self, num):
        self.num = num
    def gen_msg(self):
        if self.all > 0:
            f = 100.0*float(self.num)/float(self.all)
        else:
            f = 100.0
        self.new_msg = '%6.2f%%' % (f,)
    def output(self):
        self.gen_msg()
        if self.new_msg != self.msg:
            info('%s', '\b' * len(self.msg) + self.new_msg, end='')
            self.msg = self.new_msg
    def finish(self):
        info('')


