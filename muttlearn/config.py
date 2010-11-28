# -*- coding: utf-8 -*-

# Copyright (C) 2010 Johannes Weißl
# License GPLv3+:
# GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.
# This is free software: you are free to change and redistribute it.
# There is NO WARRANTY, to the extent permitted by law

import os
import os.path
import locale
import shelve

import muttrc
import log

# Muttrc object, needs initialization by init()
rc = None

def default_editor():
    """Return default editor, based on environment variables."""
    return os.getenv('VISUAL', os.getenv('EDITOR', 'vi'))

def default_charset():
    """Return default charset, based on locale."""
    return locale.getpreferredencoding()

def default_echo_cmd():
    """Return default echo_cmd, based on /bin/sh link."""
    echo_cmd = 'echo'
    if os.path.islink('/bin/sh'):
        bin_sh = os.path.basename(os.readlink('/bin/sh'))
        # dash builtin echo recognises escape sequences
        if bin_sh == 'dash':
            echo_cmd = 'echo'
        elif bin_sh == 'bash':
            echo_cmd = 'echo -e'
        elif bin_sh == 'csh':
            echo_cmd = '/bin/echo -e'
        elif bin_sh == 'zsh':
            echo_cmd = 'echo -e'
    return echo_cmd

mutt_defaults = {
    # original mutt settings
    'assumed_charset':       '',
    'attribution':           'On %d, %n wrote:',
    'charset':               default_charset(),
    'config_charset':        '',
    'edit_headers':          False,
    'editor':                default_editor(),
    'folder':                '~/Mail',
    'locale':                'C',
    'mbox':                  '~/mbox',
    'pgp_sign_as':           '',
    'quote_regexp':          r'^([ \t]*[|>:}#])+',
    'record':                '~/sent',
    'send_charset':          'us-ascii:iso-8859-1:utf-8',
    'sig_dashes':            True,
    'sig_on_top':            False,
    'signature':             '~/.signature',
    'smime_default_key':     '',
    'smileys':               r'(>From )|(:[-^]?[][)(><}{|/DP])',
    'smime_is_default':      False,
    'spoolfile':             '',
}

defaults = {
    'echo_cmd':              default_echo_cmd(),
    'editor_type':           u'',
    'exclude_mails_to_me':   True,
    'only_include_mails_from_me': True,
    'personalize_mailinglists': False,
    'gen_from':              True,
    'gen_sig':               True,
    'gen_fcc':               True,
    'skip_multiple_recipients': False,
    'gen_greeting':          True,
    'greeting_random_percent':   25,
    'greeting_random_max': 5,
    'known_languages':       u'*',
    'gen_locale':            True,
    'activate_spell_check':  True,
    'gen_goodbye':           True,
    'goodbye_random_percent':    25,
    'goodbye_random_max': 5,
    'gen_send_charset':      True,
    'max_age':               -1,
    'crypt_order':           u'pgp_both:smime_both:smime_sign:pgp_sign',
    'gen_crypt':             False,
    'weight_formula':        u'1.0 / math.sqrt(age + 1)',
    'output_file':           u'',
    'override_from':         False,
    'max_path_length':       256,
}

variables_used_in_scan = set([
    'max_age',
    'quote_regexp',
    'smileys',
    'exclude_mails_to_me',
    'only_include_mails_from_me',
    'personalize_mailinglists',
])

members_used_in_scan = set([
    'alternates',
    'unalternates',
])

def default_editor_type(editor):
    """Guess editor type based on full editor command (using basename)."""
    editor_name = os.path.basename(editor.split()[0])
    if editor_name == 'vi' or editor_name == 'vim':
        return 'vim'
    return ''

config_path = os.path.expanduser('~/.muttlearnrc')

def init(conf_path=None, mutt_conf_path=None, read_muttrc=True):
    global rc, config_path
    rc = muttrc.Muttrc(defaults=mutt_defaults)
    if read_muttrc:
        if not mutt_conf_path:
            paths = [os.path.expanduser(p) for p in ['~/.muttrc', '~/.mutt/muttrc']]
            mutt_conf_path = paths[0] if os.path.exists(paths[0]) else paths[1]
        rc.parse(mutt_conf_path)
    defaults['editor_type'] = default_editor_type(rc.get('editor'))
    rc.merge_defaults(defaults)
    # mailboxes command is reused
    del rc.mailboxes[:]
    if conf_path:
        config_path = os.path.realpath(conf_path)
    if not os.path.exists(config_path):
        save_default()
        log.error('config file did not exist, created default one in: %s', config_path)
    else:
        rc.parse(config_path)

    options = rc.variables
    options['output_file'] = rc.expand_path(options['output_file'])
    if options['gen_sig'] and (not options['sig_dashes'] or options['sig_on_top']):
        log.error('config error: if gen_sig=yes, these settings are required: sig_dashes=yes and sig_on_top=no')
    if options['exclude_mails_to_me'] and not rc.alternates:
        log.warn('config conflict: exclude_mails_to_me is set, but no "alternates" are specified!')
        options['exclude_mails_to_me'] = False
    if options['only_include_mails_from_me'] and not rc.alternates:
        log.warn('config conflict: only_include_mails_from_me is set, but no "alternates" are specified!')
        options['only_include_mails_from_me'] = False

cache_conf_path = os.path.expanduser('~/.muttlearn/cache_config')
cache_version = 0

def db_needs_rebuilding():
    """Check if configuration values that affect scanning process have changed."""
    if not os.path.exists(cache_conf_path):
        return True
    d = shelve.open(cache_conf_path, flag='r', protocol=2)
    if cache_version > d['version']:
        log.debug('cache too old (version %d > %d), need to rebuild', cache_version, d['version'])
        return True
    vardict = dict([(k, rc.variables[k]) for k in variables_used_in_scan])
    if d['variables'] != vardict:
        return True
    for k in members_used_in_scan:
        if d[k] != getattr(rc, k):
            return True
    return False

def save_to_cache():
    """Save configuration values that affect scanning process to cache file."""
    base = os.path.dirname(cache_conf_path)
    if not os.path.exists(base):
        os.makedirs(base)
    d = shelve.open(cache_conf_path, flag='n', protocol=2)
    vardict = dict([(k, rc.variables[k]) for k in variables_used_in_scan])
    d['variables'] = vardict
    for k in members_used_in_scan:
        d[k] = getattr(rc, k)
    d['version'] = cache_version
    d.close()

def get(key, default=None):
    return rc.get(key, default)

def set(key, value):
    rc.set(key, value)

def options():
    return rc.variables

def is_this_me(addr):
    """Check if addr is originating from the user."""
    return rc.is_this_me(addr)

def is_mailinglist(addr):
    """Check if addr is a mailing list address."""
    return rc.is_this_listed(addr) or rc.is_this_subscribed(addr)

def save_default():
    if os.path.exists(config_path):
        return
    base = os.path.dirname(config_path)
    if not os.path.exists(base):
        os.makedirs(base)
    f = open(config_path, 'wb')
    f.write(r'''\
# muttlearn configuration

# Specify mailboxes to be used for learning mails. It is advisable to include
# only mailboxes which contain outgoing mails, sent by you, not INBOX or
# mailing lists. Syntax is similar to mutt's "mailboxes" / "unmailboxes"
# command. This is overridden by positional parameters to muttlearn.
unmailboxes *
mailboxes ~/sent

# Output file for the generated hooks. This is overridden by the -o parameter.
set output_file = ~/.mutt/automatic-send-hooks

# Generate From: header by setting $from and $realname (see $override_from).
set gen_from = yes

# If set, use my_hdr From: (which overrides $reverse_name etc.)
set override_from = no

# Generate fcc hook (where message gets saved after sending)
set gen_fcc = yes

# Generate signature.
# Can only be true if $sig_dashes is set and $sig_on_top is unset.
set gen_sig = yes

# If python package guess_language is installed, the most frequently used
# language can be guessed. Since this is sometimes faulty, this
# colon-delimited list specifies all 'valid' languages to consider.
# A single star '*' means all languages.
set known_languages = en:de

# Set $locale to the most common locale for the guessed language.
set gen_locale = yes

# $attribution and $date_format can't be learned (too difficult because of
# the $index_format / strftime(3) strings), so it is possible to
# define them for each language, using '_xx' postfix (xx = lang code), e.g.:
set attribution_de = "Am %d, schrieb %n:"
set date_format_de = "%a %e. %b %Y um %T %Z"

# Activate spell checking in the guessed language. Works only for supported
# editors (see $editor_type).
set activate_spell_check = yes

# The maximum age of messages to consider (in days)
# Negative value: no limit
set max_age = -1

# Generate greeting message, e.g. "Hey Joe!\n\n".
# Works only for supported editors (see $editor_type).
set gen_greeting = yes

# Generate goodbye message, e.g. "\nSee You, Anna".
# Works only for supported editors (see $editor_type).
set gen_goodbye = yes

# If gen_crypt=yes, the following variables will be generated per recipient:
# - $smime_is_default
# - $crypt_autosign
# - $crypt_autoencrypt
# - $pgp_sign_as / $smime_default_key
set gen_crypt = yes

# vim: syntax=muttrc''')
    f.close()

def get_mailboxes():
    # mailbox names must be normal strings, otherwise python's mailbox
    # module throws errors
    enc = locale.getpreferredencoding()
    return [x.encode(enc) for x in rc.mailboxes]

def dump():
    for k in mutt_defaults:
        print rc.dump(k)
    for k in defaults:
        print rc.dump(k)
