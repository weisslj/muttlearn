# -*- coding: utf-8 -*-

# Copyright (C) 2010-2017 Johannes Weißl
# License GPLv3+:
# GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.
# This is free software: you are free to change and redistribute it.
# There is NO WARRANTY, to the extent permitted by law

"""Test vim scripts."""

import sys
import locale
import subprocess
import os
import os.path

from muttlearn import vimscript, output

attribution = u'Anna wrote:'
signature_string = u'Joe'

empty = u'\n'
signature = u'\n-- \n%s\n' % signature_string
edit_headers = u'From: joe@test\nTo: anna@test\nSubject: test\n\n'
reply = u'%s\n> foo\n> bar\n> baz\n' % attribution

inputs = {
    'new': {
        'noedit_headers': {
            'nosignature': empty,
            'signature':   signature,
        },
        'edit_headers': {
            'nosignature': edit_headers,
            'signature':   edit_headers + signature,
        },
    },
    'reply': {
        'noedit_headers': {
            'nosignature': reply,
            'signature':   reply + signature,
        },
        'edit_headers': {
            'nosignature': edit_headers + reply,
            'signature':   edit_headers + reply + signature,
        },
    },
}

greeting = u''
greeting = u'Hello Anna,'
goodbye = u''
goodbye = u'Regards,\nJoe'
placeholder = u'<++>' # use search & replace

if greeting:
    if goodbye:
        out_empty = u'%s\n\n\n\n%s\n' % (greeting, goodbye)
        out_empty_placeholder = u'%s<++>\n\n<++>\n\n%s<++>\n' % (greeting, goodbye)
        out_greeting = u'%s\n\n' % greeting
        out_goodbye = u'\n\n%s\n' % goodbye
        out_greeting_placeholder = u'%s<++>\n\n' % greeting
        out_goodbye_placeholder = u'<++>\n\n%s<++>\n' % goodbye
    else:
        out_empty = u'%s\n\n\n' % greeting
        out_empty_placeholder = u'%s<++>\n\n\n' % greeting
        out_greeting = u'%s\n\n' % greeting
        out_goodbye = u'\n'
        out_greeting_placeholder = u'%s<++>\n\n' % greeting
        out_goodbye_placeholder =u'\n'
else:
    if goodbye: # not tested
        out_empty = u'\n\n%s\n' % goodbye
        out_empty_placeholder = u'<++>\n\n%s<++>\n' % goodbye
        out_greeting = u'\n'
        out_goodbye = u'\n\n%s\n' % goodbye
        out_greeting_placeholder = u'\n'
        out_goodbye_placeholder = u'<++>\n\n%s<++>\n' % goodbye
    else: # overwritten below!
        out_empty = u''
        out_empty_placeholder = u''
        out_greeting = u''
        out_goodbye = u''
        out_greeting_placeholder = u''
        out_goodbye_placeholder = u''


outputs = {
    'new': {
        'noedit_headers': {
            'nosignature': {
                'tofu': {
                    'noplaceholder': out_empty,
                    'placeholder':   out_empty_placeholder,
                },
                'inline': {
                    'noplaceholder': out_empty,
                    'placeholder':   out_empty_placeholder,
                },
            },
            'signature': {
                'tofu': {
                    'noplaceholder': out_empty + signature,
                    'placeholder':   out_empty_placeholder + signature,
                },
                'inline': {
                    'noplaceholder': out_empty + signature,
                    'placeholder':   out_empty_placeholder + signature,
                },
            },
        },
        'edit_headers': {
            'nosignature': {
                'tofu': {
                    'noplaceholder': edit_headers + out_empty,
                    'placeholder':   edit_headers + out_empty_placeholder,
                },
                'inline': {
                    'noplaceholder': edit_headers + out_empty,
                    'placeholder':   edit_headers + out_empty_placeholder,
                },
            },
            'signature': {
                'tofu': {
                    'noplaceholder': edit_headers + out_empty + signature,
                    'placeholder':   edit_headers + out_empty_placeholder + signature,
                },
                'inline': {
                    'noplaceholder': edit_headers + out_empty + signature,
                    'placeholder':   edit_headers + out_empty_placeholder + signature,
                },
            },
        },
    },
    'reply': {
        'noedit_headers': {
            'nosignature': {
                'tofu': {
                    'noplaceholder': out_empty + u'\n' + reply,
                    'placeholder':   out_empty_placeholder + u'\n' + reply,
                },
                'inline': {
                    'noplaceholder': out_greeting + reply + out_goodbye,
                    'placeholder':   out_greeting_placeholder + reply + out_goodbye_placeholder,
                },
            },
            'signature': {
                'tofu': {
                    'noplaceholder': out_empty + u'\n' + reply + signature,
                    'placeholder':   out_empty_placeholder + u'\n' + reply + signature,
                },
                'inline': {
                    'noplaceholder': out_greeting + reply + out_goodbye + signature,
                    'placeholder':   out_greeting_placeholder + reply + out_goodbye_placeholder + signature,
                },
            },
        },
        'edit_headers': {
            'nosignature': {
                'tofu': {
                    'noplaceholder': edit_headers + out_empty + u'\n' + reply,
                    'placeholder':   edit_headers + out_empty_placeholder + u'\n' + reply,
                },
                'inline': {
                    'noplaceholder': edit_headers + out_greeting + reply + out_goodbye,
                    'placeholder':   edit_headers + out_greeting_placeholder + reply + out_goodbye_placeholder,
                },
            },
            'signature': {
                'tofu': {
                    'noplaceholder': edit_headers + out_empty + u'\n' + reply + signature,
                    'placeholder':   edit_headers + out_empty_placeholder + u'\n' + reply + signature,
                },
                'inline': {
                    'noplaceholder': edit_headers + out_greeting + reply + out_goodbye + signature,
                    'placeholder':   edit_headers + out_greeting_placeholder + reply + out_goodbye_placeholder + signature,
                },
            },
        },
    },
}

# if no greeting and no goodbye are specified, leave input unmodified
if not greeting and not goodbye:
    for it_sendstyle in ['new', 'reply']:
        for it_edit_headers in ['noedit_headers', 'edit_headers']:
            for it_signature in ['nosignature', 'signature']:
                for it_posting_style in ['tofu', 'inline']:
                    for it_placeholder in ['noplaceholder', 'placeholder']:
                        outputs[it_sendstyle][it_edit_headers][it_signature][it_posting_style][it_placeholder] = \
                                inputs[it_sendstyle][it_edit_headers][it_signature]


def check(arg_sendstyle, arg_edit_headers, arg_signature, arg_posting_style, arg_placeholder):

    kwargs = {
                'greeting': greeting,
                'goodbye': goodbye,
                'attribution': attribution,
                'signature': (signature_string if arg_signature == 'signature' else u''),
                'posting_style': unicode(arg_posting_style),
                'edit_headers': (arg_edit_headers == 'edit_headers'),
                'placeholder': (placeholder if arg_placeholder == 'placeholder' else u'')
    }

    saved_tidy = vimscript.vimscript_tidy
    saved_escape = output.vimscript_escape

    vimscript.init()
    output.vimscripts = vimscript.vimscripts
    script = output.gen_vim_script(**kwargs)

    vimscript.vimscript_tidy = lambda x: x
    vimscript.init()
    output.vimscripts = vimscript.vimscripts
    output.vimscript_escape = lambda x: x
    script_debug = output.gen_vim_script(**kwargs)

    vimscript.vimscript_tidy = saved_tidy
    output.vimscript_escape = saved_escape

    f = open('tmp/input', mode='wb')
    f.write(inputs[arg_sendstyle][arg_edit_headers][arg_signature].encode(locale.getpreferredencoding()))
    f.close()

    subprocess.call("vim -c\"%s\" -c'w!tmp/output' -c'q!' tmp/input" % script.encode(locale.getpreferredencoding()), shell=True)
    subprocess.call("vim -c\"%s\" -c'w!tmp/output_again' -c'q!' tmp/output" % script.encode(locale.getpreferredencoding()), shell=True)

    f = open('tmp/output', mode='rb')
    s = unicode(f.read(), locale.getpreferredencoding())
    f.close()

    f = open('tmp/output_again', mode='rb')
    s_again = unicode(f.read(), locale.getpreferredencoding())
    f.close()

    return s, s_again, script_debug

def out(msg, *args, **kwargs):
    msg = msg % args
    if type(msg) == unicode:
        msg = msg.encode(locale.getpreferredencoding())
    end = kwargs['end'] if 'end' in kwargs else u'\n'
    if type(end) == unicode:
        end = end.encode(locale.getpreferredencoding())
    sys.stdout.write(msg+end)

def outcmp(s1, s2):
    s1 = s1[:-1] if s1.endswith(u'\n') else s1
    s2 = s2[:-1] if s2.endswith(u'\n') else s2
    s1 = s1.split(u'\n')
    s2 = s2.split(u'\n')
    diff = len(s1) - len(s2)
    if diff < 0:
        s1 += -diff*[u'~']
    else:
        s2 += diff*[u'~']
    for x, y in zip(s1, s2):
        out(u'%-36s | %-36s', x, y)

def out_all(s_input, s_good, s_bad):
    out(u'-----------------------------------input--------------------------------------')
    out(s_input, end=u'')
    out(u'--------------Good-----------------output--------------Bad--------------------')
    outcmp(s_good, s_bad)

if not os.path.exists('tmp'):
    os.mkdir('tmp')

for it_sendstyle in ['new', 'reply']:
    for it_edit_headers in ['noedit_headers', 'edit_headers']:
        for it_signature in ['nosignature', 'signature']:
            for it_posting_style in ['tofu', 'inline']:
                for it_placeholder in ['noplaceholder', 'placeholder']:
                    s, s_again, script_debug = check(it_sendstyle, it_edit_headers, it_signature, it_posting_style, it_placeholder)
                    if s != s_again or s != outputs[it_sendstyle][it_edit_headers][it_signature][it_posting_style][it_placeholder]:
                        out(u'++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
                        print 'bad :', it_sendstyle, it_edit_headers, it_signature, it_posting_style, it_placeholder
                        out(u'-----------------------------------script-------------------------------------')
                        out(script_debug)
                        if s != s_again:
                            out_all(inputs[it_sendstyle][it_edit_headers][it_signature],
                                    s,
                                    s_again)
                        else:
                            out_all(inputs[it_sendstyle][it_edit_headers][it_signature],
                                    outputs[it_sendstyle][it_edit_headers][it_signature][it_posting_style][it_placeholder],
                                    s)
                        out(u'++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
                        sys.exit(0)
                    else:
                        print 'good:', it_sendstyle, it_edit_headers, it_signature, it_posting_style, it_placeholder
