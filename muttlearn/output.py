# -*- coding: utf-8 -*-

# Copyright (C) 2010 Johannes Weißl
# License GPLv3+:
# GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.
# This is free software: you are free to change and redistribute it.
# There is NO WARRANTY, to the extent permitted by law

"""Output mutt hooks."""

import sys
import re
import locale
import random
import math

import crypto
import log
from muttrc import expand_signature

def vimscript_tidy(script):
    """Return a condensed version of script
    (comments and superfluous whitespace removed, newlines replaced
    with '|')

    """
    lst = script.strip().split('\n')
    lst[:] = [l.strip() for l in lst]
    lst[:] = [l for l in lst if l and not l.startswith('"')]
    return '|'.join(lst)


script_noeditheaders = vimscript_tidy('''
    let f=getline(1)

    " only insert greeting/goodbye if not already there!
    if f==""||f=~"%(attribution_last_char)s$"
        call append(0,%(template)s)

        " if first line was not empty, there is quoted text
        " insert newline to seperate from it
        if f!=""
            call append(%(template_lines)d,"")
        el
            %(after_template)dd
        en

        " move cursor below greeting
        call cursor(%(greeting_lines)d,1)

        " start insert mode
        star
    en
''')

script_editheaders = vimscript_tidy('''
    " search empty line after the headers
    call cursor(1,0)
    let d=search("^$")

    let f=getline(min([line("$"),d+1]))

    " only insert greeting/goodbye if not already there!
    if f==""||f=~"%(attribution_last_char)s$"
        call append(d,%(template)s)

        " if first line was not empty, there is quoted text
        " insert newline to seperate from it
        if f!=""
            call append(d+%(template_lines)d,"")
        en

        " move cursor below greeting
        call cursor(d+%(greeting_lines)d,1)

        " start insert mode
        star
    en
''')



def vimscript_escape(s):
    s = s.replace(u'\n', u'\\n')
    s = s.replace(u'"', u'\\\\"')
    return s

def list2vim(lst):
    """Convert python list to a string containing a vim-script list."""
    return u'[%s]' % ','.join([u'"%s"' % x for x in lst])

def gen_vim_template(greeting=u'', goodbye=u'', language=u'', attribution=u'', signature=u'', edit_headers=False):
    script = u'star'
    template = []

    if greeting or goodbye:
        if greeting:
            greeting = greeting.split(u'\n')+2*[u'']
        else:
            greeting = [u'']
        template += greeting
        if goodbye:
            goodbye = [u'']+goodbye.split(u'\n')
            template += goodbye
        if signature:
            template += [u'']
        d = {
            'template_lines': len(template),
            'template': list2vim(template),
            'after_template': len(template) + 1,
            'greeting_lines': len(greeting),
            'attribution_last_char': attribution[-1],
        }
        if edit_headers:
            script = script_editheaders % d
        else:
            script = script_noeditheaders % d

    if language:
        script += u'|set spell spelllang=%s' % language
    editor = u'$my_default_editor -c"%s"' % vimscript_escape(script.strip())
    return editor

_gen_template_mapping = {
    'vim': gen_vim_template,
}
def gen_template(editor, greeting=u'', goodbye=u'', language=u'', attribution=u'', signature=u'', edit_headers=False, max_path_length=256):
    f = _gen_template_mapping[editor]
    t = f(greeting, goodbye, language, attribution, signature, edit_headers)
    if len(t) < max_path_length:
        return t
    t = f(greeting, u'', language, attribution, signature, edit_headers)
    log.debug('length of editor variable >= %d, skipping goodbye message: %s', max_path_length, goodbye, v=3)
    if len(t) < max_path_length:
        return t
    t = f(u'', u'', language, attribution, signature, edit_headers)
    log.debug('length of editor variable >= %d, skipping greeting message: %s', max_path_length, greeting, v=3)
    if len(t) < max_path_length:
        return t
    log.debug('length of editor variable STILL >= %d, skipping', max_path_length, v=3)
    return None

def get_max_key(d, percentage=100, limit=1):
    if not d:
        return None
    if '' in d:
        if len(d) > 1:
            del d['']
        else:
            return None
    lst = [(b,a) for (a,b) in d.items()]
    if limit == 1:
        return max(lst)[1]
    list.sort(lst, reverse=True)
    num = min(int(math.ceil(len(lst) * float(percentage) / 100.0)), limit)
    return random.choice(lst[:num])[1]

def escape_mutt_shellcmd(s):
    """Escape newlines used in a shell command in muttrc."""
    return s.replace(u'\n', u'\\\\\\\\n')

def escape_double_quote(s):
    """Escape double quotes."""
    return s.replace(u'"', u'\\"')

def keyid2mutt(keyid):
    """Convert S/MIME or PGP key id into mutt format."""
    return u'0x' + keyid[-8:]

def dict_key_startswith(d, prefix):
    """Return True if at least one key of dictionary d starts with prefix."""
    for k in d.keys():
        if k.startswith(prefix):
            return True
    return False

class MuttOutput(object):
    def __init__(self, outfile, options):
        self.outfile = outfile
        self.options = options
        self.output_charset = locale.getpreferredencoding()

        self.enable_from = options['gen_from']
        self.override_from = options['override_from']
        self.enable_send_charset = options['gen_send_charset']
        if self.enable_send_charset:
            self.send_charsets = options['send_charset'].split(u':')
        self.enable_locale = options['gen_locale']

        self.enable_crypto = crypto.HAVE_CRYPTO and options['gen_crypt']
        if not crypto.HAVE_CRYPTO and options['gen_crypt']:
            log.warn('failed to import pyme, but gen_crypt=yes: %s', crypto.IMPORT_ERROR)
        if self.enable_crypto:
            cryptcon = crypto.Context()
            pref_pgp_sec_key = options['pgp_sign_as']
            pref_smime_sec_key = options['smime_default_key']
            self.pgp_pub_emails = cryptcon.get_pubkey_emails(crypto.PROTO_PGP)
            self.pgp_sec_keys = cryptcon.get_seckeys_unique(crypto.PROTO_PGP, preferred=pref_pgp_sec_key[2:])
            self.smime_pub_emails = cryptcon.get_pubkey_emails(crypto.PROTO_SMIME)
            self.smime_sec_keys = cryptcon.get_seckeys_unique(crypto.PROTO_SMIME, preferred=pref_smime_sec_key[2:])
            self.crypt_order = options['crypt_order'].split(u':')


        self.enable_signature = options['gen_sig']
        self.enable_attribution = dict_key_startswith(options, 'attribution_')
        self.enable_date_format = dict_key_startswith(options, 'date_format_')

        self.editor_type = options['editor_type']
        self.editor_supported = self.editor_type and self.editor_type in _gen_template_mapping

        self.known_languages = options['known_languages']
        self.known_languages_set = set(options['known_languages'].split(u':'))

        self.enable_greeting = options['gen_greeting']
        self.enable_goodbye = options['gen_goodbye']
        self.enable_spellcheck = options['activate_spell_check']

        self.editor_required = self.enable_greeting or self.enable_goodbye or self.enable_spellcheck
        if self.editor_required and not self.editor_supported:
            log.warn('editor not supported, disabling template / spell check')
            self.enable_greeting = False
            self.enable_goodbye = False
            self.enable_spellcheck = False
        if (self.enable_greeting or self.enable_goodbye) and not self.enable_signature:
            self.default_signature = expand_signature(options['signature'])

        self.enable_fcc = options['gen_fcc']


    def is_known_language(self, language):
        return self.known_languages == u'*' or language in self.known_languages_set

    def write(self, msg):
        if type(msg) == unicode:
            msg = msg.encode(self.output_charset, 'replace')
        self.outfile.write(msg)

    def output_header(self):
        self.write(u'\n'.join(self.generate_header()))

    def generate_header(self):
        lines = []
        def app(msg=u''):
            lines.append(msg)

        app(u'# vim:set syn=muttrc:')
        app(u'# ')
        app(u'# muttlearn output file, generated by:')
        app(u'# %s' % ' '.join(sys.argv))
        app()

        send_hook_line = []
        send_hook_sets = []
        def app_sets(msg):
            send_hook_sets.append(msg)

        if self.enable_from:
            if self.override_from:
                send_hook_line.append(u'unmy_hdr From:')
            else:
                app_sets(u'from=$my_default_from')
                app_sets(u'realname=$my_default_realname')
        if self.enable_send_charset:
            app_sets(u'send_charset=$my_default_send_charset')
        if self.enable_locale:
            app_sets(u'locale=$my_default_locale')
        if self.enable_crypto:
            app_sets(u'crypt_autoencrypt=$my_default_crypt_autoencrypt')
            app_sets(u'smime_is_default=$my_default_smime_is_default')
            app_sets(u'smime_default_key=$my_default_smime_default_key')
            app_sets(u'pgp_sign_as=$my_default_pgp_sign_as')
        if self.enable_signature:
            app_sets(u'signature=$my_default_signature')
        if self.enable_attribution:
            app_sets(u'attribution=$my_default_attribution')
        if self.enable_date_format:
            app_sets(u'date_format=$my_default_date_format')
        if self.editor_supported and self.editor_required:
            app_sets(u'editor=$my_default_editor')

        if send_hook_sets:
            send_hook_line.append(u'set ' + u' '.join(send_hook_sets))

        if send_hook_sets:
            app(u'# save current values to access them after overwriting')
            if self.enable_from and not self.override_from:
                app(u'set my_default_from=$from')
                app(u'set my_default_realname=$realname')
            if self.enable_send_charset:
                app(u'set my_default_send_charset=$send_charset')
            if self.enable_locale:
                app(u'set my_default_locale=$locale')
            if self.enable_crypto:
                app(u'set my_default_crypt_autoencrypt=$crypt_autoencrypt')
                app(u'set my_default_smime_is_default=$smime_is_default')
                app(u'set my_default_smime_default_key=$smime_default_key')
                app(u'set my_default_pgp_sign_as=$pgp_sign_as')
            if self.enable_signature:
                app(u'set my_default_signature=$signature')
            if self.enable_attribution:
                app(u'set my_default_attribution=$attribution')
            if self.enable_date_format:
                app(u'set my_default_date_format=$date_format')
            if self.editor_supported and self.editor_required:
                app(u'set my_default_editor=$editor')
            app()
        if send_hook_line:
            app(u'# if none of the send-hooks match, use saved defaults')
            app(u"send-hook '~t .' '%s'" % u' ; '.join(send_hook_line))

        if send_hook_line or self.enable_fcc:
            app()
            app()

        return lines

    def _get_crypt_setting(self, from_email, emails):
        pgp_pub_emails = self.pgp_pub_emails
        pgp_sec_keys = self.pgp_sec_keys
        smime_pub_emails = self.smime_pub_emails
        smime_sec_keys = self.smime_sec_keys

        for crypt_type in self.crypt_order:
            if crypt_type == 'pgp_both' and emails.issubset(pgp_pub_emails) and from_email in pgp_sec_keys:
                crypt_setting = [u'smime_is_default=no', u'crypt_autosign=yes', u'crypt_autoencrypt=yes']
                key = keyid2mutt(pgp_sec_keys[from_email])
                crypt_setting.append(u'pgp_sign_as=%s' % key)
                break
            elif crypt_type == 'smime_both' and emails.issubset(smime_pub_emails) and from_email in smime_sec_keys:
                crypt_setting = [u'smime_is_default=yes', u'crypt_autosign=yes', u'crypt_autoencrypt=yes']
                key = keyid2mutt(smime_sec_keys[from_email])
                crypt_setting.append(u'smime_default_key=%s' % key)
                break
            elif crypt_type == 'smime_sign' and from_email in smime_sec_keys:
                crypt_setting = [u'smime_is_default=yes', u'crypt_autosign=yes', u'crypt_autoencrypt=no']
                key = keyid2mutt(smime_sec_keys[from_email])
                crypt_setting.append(u'smime_default_key=%s' % key)
                break
            elif crypt_type == 'pgp_sign' and from_email in pgp_sec_keys:
                crypt_setting = [u'smime_is_default=no', u'crypt_autosign=yes', u'crypt_autoencrypt=no']
                key = keyid2mutt(pgp_sec_keys[from_email])
                crypt_setting.append(u'pgp_sign_as=%s' % key)
                break
            elif crypt_type == 'smime_crypt' and emails.issubset(smime_pub_emails):
                crypt_setting = [u'smime_is_default=yes', u'crypt_autosign=no', u'crypt_autoencrypt=yes']
                break
            elif crypt_type == 'pgp_crypt' and emails.issubset(pgp_pub_emails):
                crypt_setting = [u'smime_is_default=no', u'crypt_autosign=no', u'crypt_autoencrypt=yes']
                break
        else:
            crypt_setting = [u'crypt_autosign=no', u'crypt_autoencrypt=no']
        return crypt_setting

    def output_recipient(self, r):
        self.write(u'\n'.join(self.generate_recipient(r)))

    def generate_recipient(self, r):
        options = self.options

        send_hook_line = []
        send_hook_sets = []
        def app(msg=u'', *args, **kwargs):
            msg = msg % args
            send_hook_sets.append(msg)

        to_emails = r.emails
        from_email = get_max_key(r.from_email)

        to_emails_pattern = u' '.join([u'~t "^%s$"' % re.escape(e) for e in sorted(to_emails)])
        if len(to_emails) == 1:
            to_emails_pattern = u'^' + to_emails_pattern

        if self.enable_from:
            if self.override_from:
                send_hook_line.append(u"my_hdr From: %s" % get_max_key(r.from_hdr))
            else:
                app(u'from="%s"', from_email)
                realname = get_max_key(r.from_realname)
                val_realname = u'$my_default_realname'
                if realname:
                    val_realname = u'"%s"' % realname
                app(u'realname=%s', val_realname)

        if self.enable_send_charset:
            val_send_charset = u'$my_default_send_charset'
            charset = get_max_key(r.charset)
            if charset:
                charsets = self.send_charsets[:]
                if charset not in charsets:
                    charsets.insert(1, charset)
                val_send_charset = u'"%s"' % u':'.join(charsets)
            app(u'send_charset=%s', val_send_charset)

        language = get_max_key(r.language)
        if not language or not self.is_known_language(language):
            language = u''

        if self.enable_locale:
            val_locale = u'$my_default_locale'
            if language:
                locale_alias = language + u'.' + locale.getpreferredencoding()
                locale_name = locale.normalize(locale_alias)
                # only write locale setting if alias could be resolved!
                if locale_name != locale_alias:
                    val_locale = u'"%s"' % locale_name
            app(u'locale=%s', val_locale)

        if self.enable_crypto:
            crypt_setting = self._get_crypt_setting(from_email, to_emails)
            send_hook_sets.extend(crypt_setting)

        if self.enable_signature:
            val_signature = u'$my_default_signature'
            echo_cmd = options['echo_cmd']
            signature = get_max_key(r.signature)
            if signature:
                val_signature = u'"%s %s|"' % (echo_cmd, escape_mutt_shellcmd(signature))
            app(u'signature=%s', val_signature)
        else:
            signature = self.default_signature

        attribution = u''
        if self.enable_attribution:
            val_attribution = u'$my_default_attribution'
            attribution = options.get('attribution_'+language)
            if attribution:
                val_attribution = u'"%s"' % attribution
            app(u'attribution=%s', val_attribution)
        if not attribution:
            attribution = options['attribution']

        if self.enable_date_format:
            val_date_format = u'$my_default_date_format'
            date_format = options.get('date_format_'+language)
            if date_format:
                val_date_format = u'"%s"' % date_format
            app(u'date_format=%s', val_date_format)

        if self.editor_supported and self.editor_required:
            val_editor = u'$my_default_editor'
            greeting = u''
            if self.enable_greeting:
                greeting = get_max_key(r.greeting, options['greeting_random_percent'], options['greeting_random_max'])
            goodbye = u''
            if self.enable_goodbye:
                goodbye = get_max_key(r.goodbye, options['goodbye_random_percent'], options['goodbye_random_max'])

            spelllang = language if self.enable_spellcheck else u''
            template = gen_template(self.editor_type, greeting, goodbye, spelllang, attribution, signature, options['edit_headers'], options['max_path_length'])
            if template:
                val_editor = u'"%s"' % escape_double_quote(template)
            app(u'editor=%s', val_editor)

        if send_hook_sets:
            send_hook_line.append(u'set ' + u' '.join(send_hook_sets))

        lines = []
        if send_hook_line:
            lines.append(u"send-hook '%s' '%s'" % (to_emails_pattern, ' ; '.join(send_hook_line)))

        if self.enable_fcc:
            lines.append(u"fcc-hook '%s' '%s'" % (to_emails_pattern, get_max_key(r.mbox_path)))

        if lines:
            lines.insert(0, u'# %s' % ', '.join(sorted(to_emails)))
            lines.extend(2*[u''])

        return lines
