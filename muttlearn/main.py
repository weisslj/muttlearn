# -*- coding: utf-8 -*-

# Copyright (C) 2010 Johannes Weißl
# License GPLv3+:
# GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.
# This is free software: you are free to change and redistribute it.
# There is NO WARRANTY, to the extent permitted by law

import sys
import locale
import re
import optparse
import shelve
import os.path

import scan
import config
import output
import log
from common import filter_any, __version__

cache_recipients_path = os.path.expanduser('~/.muttlearn/cache_recipients')
def save_recipients(recipients):
    dstore = shelve.open(cache_recipients_path, flag='n', protocol=2)
    for k in recipients:
        d = {}
        recipients[k].to_dict(d)
        dstore[k.encode('utf-8')] = d
    dstore.close()
def load_recipients():
    dstore = shelve.open(cache_recipients_path, flag='r', protocol=2)
    recipients = {}
    for k in dstore:
        r = scan.Recipient(dstore[k]['emails'])
        r.from_dict(dstore[k])
        recipients[unicode(k, 'utf-8')] = r
    dstore.close()
    return recipients

cache_messages_path = os.path.expanduser('~/.muttlearn/cache_messages')
def gen_recipients_from_cache(options, progress=False):
    if not os.path.exists(cache_messages_path):
        return {}
    max_age = options['max_age']
    dstore = shelve.open(cache_messages_path, flag='r', protocol=2)
    recipients = {}
    n_messages = len(dstore)
    log.info('cache only, %d messages', n_messages)
    if progress:
        pstatus = log.PercentStatus(n_messages, prefix='      ')
    for msgid in dstore:
        if progress:
            pstatus.inc()
            pstatus.output()
        msg = scan.Message()
        msg.from_dict_only(dstore[msgid])
        if options['skip_multiple_recipients'] and len(msg.to_emails) > 1:
            continue
        if options['exclude_mails_to_me'] and filter_any(config.is_this_me, msg.to_emails):
            continue
        if options['only_include_mails_from_me'] and not config.is_this_me(msg.from_email):
            continue
        if max_age >= 0 and msg.age > max_age:
            continue
        if msg.to_emails_str not in recipients:
            r = scan.Recipient(msg.to_emails, msg)
            recipients[msg.to_emails_str] = r
        else:
            recipients[msg.to_emails_str].add(msg)
    if progress:
        pstatus.finish()
    dstore.close()
    return recipients

def gen_recipients(mailboxes, options, use_cache=True, clean_cache=False, progress=False):
    base = os.path.dirname(cache_messages_path)
    if not os.path.exists(base):
        os.makedirs(base)
    max_age = options['max_age']
    dstore = shelve.open(cache_messages_path, protocol=2)
    recipients = {}
    if clean_cache:
        store_keys_used = set()
    n_mailboxes = len(mailboxes)
    for i, mb in enumerate(mailboxes):
        if progress:
            n_messages = len(mb)
            log.info('[%d/%d] %s: %d messages', i+1, n_mailboxes, mb.path, n_messages)
            pstatus = log.PercentStatus(n_messages, prefix='      ')
        for msg in mb.messages():
            if progress:
                pstatus.inc()
                pstatus.output()
            msgid = msg.msgid
            d = dstore.get(msgid)
            if msgid and d and d['adler32'] == msg.adler32 and use_cache:
                msg.from_dict(d)
                if clean_cache:
                    store_keys_used.add(msgid)
            else:
                if not msg.parse_header():
                    continue
                d = {}
            if options['skip_multiple_recipients'] and len(msg.to_emails) > 1:
                continue
            if options['exclude_mails_to_me'] and filter_any(config.is_this_me, msg.to_emails):
                continue
            if options['only_include_mails_from_me'] and not config.is_this_me(msg.from_email):
                continue
            if max_age >= 0 and msg.age > max_age:
                continue
            if not d:
                msg.parse_body()
                if msgid:
                    msg.to_dict(d)
                    dstore[msgid] = d
                    if clean_cache:
                        store_keys_used.add(msgid)

            if msg.to_emails_str not in recipients:
                r = scan.Recipient(msg.to_emails, msg)
                recipients[msg.to_emails_str] = r
            else:
                recipients[msg.to_emails_str].add(msg)
        if progress:
            pstatus.finish()
    if clean_cache:
        keys_to_delete = set(dstore.keys()) - store_keys_used
        for k in keys_to_delete:
            del dstore[k]
    dstore.close()
    return recipients


def main(argv=None):

    if not argv:
        argv = sys.argv

    usage = 'usage: muttlearn [options] [-o file] mbox1 [mbox2...]\n'\
            '       muttlearn [options]\n'\
            '       muttlearn -D\n'\
            '       muttlearn --output-only'

    version = u'muttlearn %s\nCopyright (C) 2010 Johannes Weißl\n'\
        'License GPLv3+: GNU GPL version 3 or later '\
        '<http://gnu.org/licenses/gpl.html>.\n'\
        'This is free software: you are free to change and redistribute it.\n'\
        'There is NO WARRANTY, to the extent permitted by law.' % __version__
    desc = 'muttlearn is an alternative to manually maintaining profiles in mutt. '\
        'It scans your mailboxes, learns how you want to write mails (e.g. '\
        'with which from address, what signature, what greeting, etc.) and '\
        'outputs send-hooks per recipient or group of recipients.'

    locale.setlocale(locale.LC_ALL, '')

    parser = optparse.OptionParser(usage=usage,
                                   version=version,
                                   description=desc,
                                   prog='muttlearn')

    parser.add_option('-o', dest='output', default=None, metavar='FILE',
        help='output file, "-" for stdout')
    parser.add_option('-D', dest='dump_vars', action='store_true', default=False,
        help='print the value of all configuration options to stdout.')
    parser.add_option('-F', dest='muttlearnrc', default=None, metavar='FILE',
        help='use alternative config file instead of ~/.muttlearnrc')
    parser.add_option('-v', '--verbose', dest='verbosity', action='count', default=0,
        help='be verbose (multiple times: more verbose)')
    parser.add_option('-p', '--progress', action='store_true', default=False,
        help='show progress')
    parser.add_option('--muttrc', default=None, metavar='FILE',
        help='use this file instead of ~/.muttrc to get mutt defaults')
    parser.add_option('-n', '--no-muttrc', dest='read_muttrc', action='store_false', default=True,
        help='do not read ~/.muttrc')
    parser.add_option('-C', '--rebuild-cache', action='store_true', default=False,
        help='rebuild message cache (slow)')
    parser.add_option('-c', '--clean-cache', action='store_true', default=False,
        help='remove unused messages from the cache')
    parser.add_option('--output-only', action='store_true', default=False,
        help='do not scan messages, just output (very fast)')

    options, args = parser.parse_args(argv[1:])

    log.verbosity = options.verbosity

    if not options.read_muttrc and options.muttrc:
        parser.error('-n and --muttrc cannot both be specified')

    config.init(conf_path=options.muttlearnrc,
                mutt_conf_path=options.muttrc,
                read_muttrc=options.read_muttrc)

    if options.dump_vars:
        config.dump()
        return

    if not options.output:
        options.output = config.get('output_file').encode(locale.getpreferredencoding())
    if not options.output:
        parser.error('no output file specified, use $output_file or -o')

    mailbox_paths = args if args else config.get_mailboxes()
    if not mailbox_paths:
        parser.error('no mailbox specified for learning!')

    if options.rebuild_cache:
        use_cache = False
    else:
        use_cache = not config.db_needs_rebuilding()
    if not use_cache:
        log.debug('rebuilding message cache (slow!)')
        config.save_to_cache()
    else:
        log.debug('using message cache (faster)')

    if options.output_only:
        #recipients = load_recipients()
        recipients = gen_recipients_from_cache(config.options(),
                                               progress=options.progress)
    else:
        scan.init(config.options())
        scan.prepare()
    
        mailboxes = [scan.Mailbox(path, 'auto') for path in mailbox_paths]
    
        recipients = gen_recipients(mailboxes,
                                    config.options(),
                                    use_cache=use_cache,
                                    clean_cache=options.clean_cache,
                                    progress=options.progress)

        #save_recipients(recipients)

    if options.output == '-':
        outfile = sys.stdout
    else:
        try:
            outfile = open(options.output, 'wb')
        except IOError, e:
            log.error('error opening output file: %s', e)


    mutt_out = output.MuttOutput(outfile, config.options())
    mutt_out.output_header()
    # result is sorted, so that larger address groups are matched later.
    # Also comparison of output files is easier when debugging.
    for addr in sorted(recipients, key=lambda x:(len(x),x)):
        mutt_out.output_recipient(recipients[addr])

    if options.output != '-':
        outfile.close()

if __name__ == '__main__':
    sys.exit(main())
