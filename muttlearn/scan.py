# -*- coding: utf-8 -*-

# Copyright (C) 2010 Johannes Weißl
# License GPLv3+:
# GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.
# This is free software: you are free to change and redistribute it.
# There is NO WARRANTY, to the extent permitted by law

"""Scan mailboxes and analyze messages."""

import re
import locale
import os.path
import collections
import time
import math
import gzip
import bz2
import zlib
import mailbox
import email
import email.utils
import email.header
import mmap

import config
import log
from common import filter_any

guessLanguage = lambda x: ''
def prepare():
    """Loads the guess_language module.
    This takes 1-2 seconds, so it is delayed to increase responsiveness.

    """
    global guessLanguage
    try:
        from guess_language import guessLanguage
    except ImportError, e:
        log.debug('failed to import guess_language, language guessing disabled: %s', e)

def decode_header(h, encodings_used=None):
    """Return unicode representation of header body, e.g.:
    '=?utf-8?b?ZMOpasOgIHZ1?=' -> u'déjà vu'

    throws UnicodeDecodeError

    """
    lst = email.header.decode_header(h)
    if encodings_used is not None:
        for x in lst:
            if x[1]:
                encodings_used.add(x[1])
    return unicode(email.header.make_header(lst))

class MessageBody(object):
    _re_control_message = re.compile(r'^-----.*-----$')

    def __init__(self, body, re_quote, re_smileys):
        lines = body.split(u'\n')
        top = []
        attribution = []
        interleaved = []
        bottom = []
        unquoted = []
        quoted = []
        before_attribution = True
        following_quote = False
        cur = top
        for line in lines:
            if self._re_control_message.match(line):
                break
            elif re_quote.match(line) and not re_smileys.match(line):
                if before_attribution:
                    # remove attribution (max: 2 lines)
                    for i in range(2):
                        if top and top[-1] != '':
                            attribution.insert(0, top[-1])
                            del top[-1]
                            del unquoted[-1]
                    cur = interleaved
                    before_attribution = False
                del bottom[:]
                following_quote = True
                if line:
                    quoted.append(line)
            else:
                if not following_quote:
                    bottom.append(line)
                following_quote = False
                if line:
                    unquoted.append(line)
            cur.append(line)
        if bottom:
            del interleaved[-len(bottom):]
        self.top = u'\n'.join(top)
        self.attribution = u'\n'.join(attribution)
        self.interleaved = u'\n'.join(interleaved)
        self.bottom = u'\n'.join(bottom)
        self.unquoted = u'\n'.join(unquoted)
        self.quoted = u'\n'.join(quoted)

class Message(object):
    def __init__(self):
        self.from_hdr = u''
        self.from_email = u''
        self.from_realname = u''
        self.to_emails = set()
        self.to_emails_str = u''
        self.time = -1
        self.age = -1
        self.charset = ''
        self.signature = u''
        self.greeting = u''
        self.goodbye = u''
        self.language = u''
        self.body = u''

        self.mbox_path = u''

    def set_time(self, t):
        self.time = t
        self.age = int((time.time() - self.time) / 3600 / 24)

    def from_dict(self, d):
        self.from_hdr = d['from_hdr']
        self.from_email = d['from_email']
        self.from_realname = d['from_realname']
        self.to_emails = d['to_emails']
        self.to_emails_str = d['to_emails_str']
        self.set_time(d['time'])
        self.charset = d['charset']
        self.signature = d['signature']
        self.greeting = d['greeting']
        self.goodbye = d['goodbye']
        self.language = d['language']
    def from_dict_only(self, d):
        self.from_dict(d)
        self.mbox_path = d['mbox_path']

    def to_dict(self, d):
        # only required in cache only mode
        d['mbox_path'] = self.mbox_path

        d['adler32'] = self.adler32

        d['from_hdr'] = self.from_hdr
        d['from_email'] = self.from_email
        d['from_realname'] = self.from_realname
        d['to_emails'] = self.to_emails
        d['to_emails_str'] = self.to_emails_str
        d['time'] = self.time
        d['charset'] = self.charset
        d['signature'] = self.signature
        d['greeting'] = self.greeting
        d['goodbye'] = self.goodbye
        d['language'] = self.language


class MailboxMessage(Message):
    _re_msgid = re.compile(r'^Message-ID:[ \t]*(.*?)\n[^ \t]', re.M | re.I | re.S)
    _re_signature = re.compile(r'\n-- \n(.*)$', re.DOTALL)
    _re_greeting = re.compile(r'^(.{2,40})\n\n')
    _re_goodbye = re.compile(r'\n\n((?:.{2,40}\n.{2,40})|(?:.{2,40}\n\n.{2,40})|(?:.{2,40}))$')
    _re_quote = re.compile(r'^([ \t]*[|>:}#])+')
    _re_smileys = re.compile(r'(>From )|(:[-^]?[][)(><}{|/DP])')
    _assumed_charsets = ['us-ascii', 'iso-8859-1', 'utf-8']

    def __init__(self, path, mbox, mbox_key):
        super(MailboxMessage, self).__init__()
        self.mbox_path = path
        self.mbox = mbox
        self.mbox_key = mbox_key

        buf = mbox.get_string(mbox_key)
        self.adler32 = zlib.adler32(buf)
        msgid_match = self._re_msgid.search(buf)
        self.msgid = msgid_match.group(1).strip() if msgid_match else ''
        if not self.msgid:
            log.debug('message has no Message-ID, cannot cache: %s -> %s', path, mbox_key)

    def parse_header(self):
        msg = self.mbox.get_message(self.mbox_key)
        self.msg = msg
        msgid = self.msgid or self.mbox_key

        self.encodings_used = set()
        try:
            self.from_hdr = decode_header(msg['From'], self.encodings_used)
        except UnicodeDecodeError, e:
            log.debug('can not decode From: header of %s: %s', msgid, str(e))
            return False

        try:
            to_hdr = decode_header(msg['To'], self.encodings_used)
        except UnicodeDecodeError, e:
            log.debug('can not decode To: header of %s: %s', msgid, str(e))
            return False

        date_str = decode_header(msg['Date'])

        from_decoded = email.utils.getaddresses([self.from_hdr])
        if not from_decoded or not from_decoded[0][1]:
            log.debug('mail has no sender: %s', msgid)
            return False
        self.from_email = from_decoded[0][1].lower()
        self.from_realname = from_decoded[0][0]
        self.to_emails = set(e.lower() for n, e in email.utils.getaddresses([to_hdr]))
        if not self.to_emails:
            log.debug('mail has no recipient: %s', msgid)
            return False
        self.to_emails_str = ' '.join(sorted(self.to_emails))

        msg_time = time.time()
        if date_str:
            date_tuple = email.utils.parsedate_tz(date_str)
            if date_tuple:
                msg_time = email.utils.mktime_tz(date_tuple)
        self.set_time(msg_time)

        return True

    def parse_body(self):
        msgid = self.msgid or self.mbox_key

        if self.msg.is_multipart():
            for part in self.msg.walk():
                if part.get_content_type() == 'text/plain':
                    self.msg = part
                    break
            else:
                log.debug('%s message contains no text/plain subpart: %s', self.msg.get_content_type(), msgid, v=2)
                return False
        if self.msg.get_content_type() != 'text/plain':
            log.debug('content type %s not supported: %s', self.msg.get_content_type(), msgid, v=2)
            return False

        self.charset = self.msg.get_content_charset('')

        unicode_error = None
        if self.charset:
            try: self.body = unicode(self.msg.get_payload(decode=True), self.charset)
            except (UnicodeDecodeError, LookupError), e: unicode_error = e
        else:
            for charset in self._assumed_charsets:
                try: self.body = unicode(self.msg.get_payload(decode=True), charset)
                except (UnicodeDecodeError, LookupError), e: unicode_error = e
                else:
                    self.charset = charset
                    unicode_error = None
                    break
        # if body is ascii, look at header for future send_charset
        if self.charset == 'us-ascii' and self.encodings_used:
            self.charset = self.encodings_used.pop()

        # if unicode conversion failed, skip body detection altogether
        # nobody benefits from distorted strings
        if unicode_error is not None:
            log.debug('can not decode body of %s: %s', msgid, unicode_error)
            return False

        if not self.body:
            log.debug('empty body: %s', msgid, v=3)
            return False

        # convert dos line feeds to unix line feeds
        self.body = self.body.replace(u'\r\n', u'\n')
        self.body = self.body.strip(u'\n')

        # start with signature detection because it is the easiest/safest
        match = self._re_signature.search(self.body)
        self.signature = match.group(1) if match else u''
        if self.signature:
            self.body = self._re_signature.sub(u'', self.body, 1).rstrip('\n')

        if not config.get('personalize_mailinglists') and filter_any(config.is_mailinglist, self.to_emails):
            return False

        match = self._re_greeting.search(self.body)
        self.greeting = match.group(1) if match else u''
        if self.greeting:
            body = self._re_greeting.sub(u'', self.body, 1).lstrip('\n')
            mb = MessageBody(body, self._re_quote, self._re_smileys)
            words_to_guess = u' '.join(re.split(r'\W+', u'%s %s' % (mb.unquoted, mb.quoted))[:20])
            guessed_language = guessLanguage(words_to_guess)
            self.language = guessed_language if guessed_language != 'UNKNOWN' else ''
            if not mb.unquoted:
                self.greeting = u''

            match = self._re_goodbye.search(mb.top.rstrip('\n'))
            if not match:
                match = self._re_goodbye.search(mb.bottom.rstrip('\n'))
            if match:
                body = self._re_goodbye.sub(u'', body, 1).strip('\n')
                if body:
                    self.goodbye = match.group(1)

        return True

class Recipient(object):
    values = [
        'to_emails_str',
        'from_hdr',
        'from_email',
        'from_realname',
        'signature',
        'greeting',
        'goodbye',
        'charset',
        'language',
        'mbox_path',
    ]
    weight_formula = compile('1.0 / math.sqrt(age + 1)', '<string>', 'eval')
    def __init__(self, emails, msg=None):
        self.emails = emails
        for v in self.values:
            setattr(self, v, collections.defaultdict(lambda: 0.0))
        if msg:
            self.add(msg)
    def reset(self):
        for v in self.values:
            getattr(self, v).clear()
    def add(self, msg):
        incr_step = eval(self.weight_formula, {'age': msg.age, 'math': math})
        for v in self.values:
            getattr(self, v)[getattr(msg, v)] += incr_step
    def to_dict(self, d):
        d['emails'] = self.emails
        for v in self.values:
            d[v] = dict(getattr(self, v))
    def from_dict(self, d):
        for v in self.values:
            setattr(self, v, collections.defaultdict(lambda: 0.0, d[v]))

class Mailbox(object):
    def __init__(self, path, type='auto'):
        if not os.path.exists(path):
            log.error('mailbox "%s" does not exist', path)
        self.path = os.path.realpath(path)
        if type == 'auto':
            type = self.recognize()
        if type == 'mbox':
            self.mb = mailbox.mbox(path, create=False)
            self.try_decompress()
        elif type == 'Maildir':
            self.mb = mailbox.Maildir(path, factory=None, create=False)
        elif type == 'MH':
            self.mb = mailbox.MH(path, create=False)
        elif type == 'MMDF':
            self.mb = mailbox.MMDF(path, create=False)
            self.try_decompress()
        elif type == 'Babyl':
            self.mb = mailbox.Babyl(path, create=False)
        else:
            self.mb = None

    def __len__(self):
        return len(self.mb)

    def messages(self):
        for k in self.mb.iterkeys():
            yield MailboxMessage(self.path, self.mb, k)

    def try_decompress(self):
        if re.match(r'.*\.gz$', self.path):
            self.mb._file.close()
            self.mb._file = gzip.GzipFile(self.path)
        elif re.match(r'.*\.bz2$', self.path):
            self.mb._file.close()
            self.mb._file = bz2.BZ2File(self.path)

    def recognize(self):
        t = ''
        if os.path.isdir(self.path):
            if os.path.isdir(os.path.join(self.path, 'cur')):
                t = 'Maildir'
            else:
                t = 'MH'
        elif os.path.isfile(self.path):
            try:
                f = open(self.path, mode='rb')
                map = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                if map[:5] == 'BABYL':
                    t = 'Babyl'
                elif map[:5] == '\x01\x01\x01\x01\n':
                    t = 'MMDF'
                else:
                    t = 'mbox'
                map.close()
                f.close()
            except (IOError, mmap.error), e:
                log.error('cannot open mailbox %s: %s', self.path, str(e))
        return t

def init(options):
    try:
        re_quote = re.compile(options['quote_regexp'])
        MailboxMessage._re_quote = re_quote
    except re.error, e:
        log.error('quote_regexp is invalid regexp: %s', e)
    try:
        re_smileys = re.compile(options['smileys'])
        MailboxMessage._re_smileys = re_smileys
    except re.error, e:
        log.error('smileys is invalid regexp: %s', e)
    try:
        re_greeting = re.compile(options['greeting_regexp'])
        MailboxMessage._re_greeting = re_greeting
    except re.error, e:
        log.error('greeting_regexp is invalid regexp: %s', e)
    try:
        re_goodbye = re.compile(options['goodbye_regexp'])
        MailboxMessage._re_goodbye = re_goodbye
    except re.error, e:
        log.error('goodbye_regexp is invalid regexp: %s', e)
    try:
        weight_formula = compile(options['weight_formula'], '<string>', 'eval')
        Recipient.weight_formula = weight_formula
    except (SyntaxError, TypeError), e:
        log.error('weight_formula is invalid: %s', e)
    if options['assumed_charset']:
        MailboxMessage._assumed_charsets[:] = options['assumed_charset'].split(':')
