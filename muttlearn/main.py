# -*- coding: utf-8 -*-

# Copyright (C) 2010-2017 Johannes Weißl
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
import errno

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
cache_messages_tmp_path = cache_messages_path + '.tmp'
cache_messages_lock_path = cache_messages_path + '.lock'

def acquire_lock():
    base = os.path.dirname(cache_messages_lock_path)
    if not os.path.exists(base):
        os.makedirs(base)
    if os.path.exists(cache_messages_lock_path):
        try:
            f = open(cache_messages_lock_path, 'rb')
            pid = int(f.read().strip())
        except IOError, e:
            log.error('could not open lock file: %s', e)
        else:
            f.close()
        try:
            os.kill(pid, 0)
        except OSError, err:
            if err.errno == errno.ESRCH:
                log.info('removing stale lock file %s', cache_messages_lock_path)
            elif err.errno == errno.EPERM:
                log.error('no permission to signal process %d, remove %s manually!', pid, cache_messages_lock_path)
            else:
                log.error('unknown error while signalling process %d, remove %s manually!', pid, cache_messages_lock_path)
        else:
            log.error('already running, if not remove %s manually!', cache_messages_lock_path)
    try:
        f = open(cache_messages_lock_path, 'wb')
        f.write(str(os.getpid())+'\n')
    except IOError, e:
        log.error('could not write lock file: %s', e)
    else:
        f.close()

def release_lock():
    if os.path.exists(cache_messages_lock_path):
        os.remove(cache_messages_lock_path)

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
    for identifier in dstore:
        if progress:
            pstatus.inc()
            pstatus.output()
        msg = scan.Message()
        msg.from_dict_only(dstore[identifier])
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
    if not os.path.exists(cache_messages_path):
        # if there is no cache, it doesn't need to be cleaned
        clean_cache = False
    max_age = options['max_age']
    flag = 'r' if clean_cache else 'c'
    dstore = shelve.open(cache_messages_path, flag=flag, protocol=2)
    dstore_write = shelve.open(cache_messages_tmp_path, flag='n', protocol=2) if clean_cache else dstore
    recipients = {}
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
            d = dstore.get(msg.identifier)
            if use_cache and d and not msg.has_changed(d):
                msg.from_dict(d)
                if clean_cache:
                    dstore_write[msg.identifier] = d
            else:
                if not msg.parse_header():
                    continue
                d = {}
                msg.parse_body()
                if msg.identifier:
                    msg.to_dict(d)
                    dstore_write[msg.identifier] = d

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
    if clean_cache:
        dstore_write.close()
        os.rename(cache_messages_tmp_path, cache_messages_path)
    return recipients


def main(argv=None):

    if not argv:
        argv = sys.argv

    usage = 'usage: muttlearn [options] [-o file] mbox1 [mbox2...]\n'\
            '       muttlearn [options]\n'\
            '       muttlearn -D\n'\
            '       muttlearn --output-only'

    version = u'muttlearn %s\nCopyright (C) 2010-2017 Johannes Weißl\n'\
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


    acquire_lock()

    if options.rebuild_cache:
        use_cache = False
    else:
        use_cache = not config.db_needs_rebuilding()
    if not use_cache:
        options.clean_cache = True
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

    release_lock()

if __name__ == '__main__':
    sys.exit(main())
