# -*- coding: utf-8 -*-

# Copyright (C) 2010-2017 Johannes Weißl
# License GPLv3+:
# GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.
# This is free software: you are free to change and redistribute it.
# There is NO WARRANTY, to the extent permitted by law

"""Vimscripts."""

def vimscript_tidy(script):
    """Return a condensed version of script
    (comments and superfluous whitespace removed, newlines replaced
    with '|')

    """
    lst = script.strip().split(u'\n')
    lst[:] = [l.strip() for l in lst]
    lst[:] = [l for l in lst if l and not l.startswith(u'"')]
    return u'|'.join(lst)


vimscripts = {}
def init():
    for edit_headers in [True, False]:
        vimscripts[edit_headers] = {}
        d = u'd' if edit_headers else u'0'
        dplus = u'd+' if edit_headers else u''
        for posting_style in [u'tofu', u'inline']:
            vimscripts[edit_headers][posting_style] = {}
            for use_signature in [True, False]:
                vimscripts[edit_headers][posting_style][use_signature] = {}
                for use_placeholder in [True, False]:
                    script = u''
                    if edit_headers:
                        script += u'''
" search empty line after the headers
call cursor(1,0)
let d=search("^$")

let f=getline(min([line("$"),d+1]))
'''
                    else:
                        script += u'''
let f=getline(1)
'''
                    script += u'''
" only insert greeting/goodbye if not already there!
if f==""||f=~"%(attribution_last_char)s$"
'''
                    if posting_style == u'tofu':
                        script += u'''
    call append('''+d+u''',%(template)s)
'''
                        if not edit_headers:
                            script += u'''
    " The input file contains an empty line, which can only be removed
    " after first append(). This is not true if there is quoted text!
    " In this case, we even have to append one line to separate
    " (not when there is a signature)!
    if f==""
        %(after_template)dd
'''
                            if not use_signature:
                                script += u'''
    el
        call append(%(template_lines)d,"")
'''
                            script += u'''
    en
'''
                        else: # edit_headers
                            script += u'''
    " if first line was not empty, there is quoted text
    " insert newline to seperate from it
    if f!=""
        call append(d+%(template_lines)d,"")
    en
'''
                    else: # posting_style == u'inline'
                        script += u'''
    " append greeting
    call append('''+d+u''',%(greeting)s)
'''
                        if not edit_headers:
                            script += u'''
    " The input file contains an empty line, which can only be removed
    " after first append(). This is not true if there is quoted text!
    if f==""
        %(after_greeting)dd
    en
'''
                        elif use_signature: # edit_headers
                            script += u'''
    " signature inserts newline, not needed!
    if f==""
        call cursor(d+%(after_greeting)d, 0)
        d
    en
'''
                        if use_signature:
                            script += u'''
    " append goodbye message at the end, but before signature
    let s=search("^-- $")-1
    if s<0
        let s=line("$")
    en
    call append(s,%(goodbye)s)
    if f!=""
        call cursor(s,0)
        d
    en
'''
                        else:  # not use_signature
                            script += u'''
    " append goodbye message at the end
    call append("$",%(goodbye)s)
'''


# just cursor positioning from here!
                    if posting_style == u'inline' or use_placeholder:
                        script += u'''
    " move cursor to beginning of file
    call cursor(1,1)
'''
                    else:
                        script += u'''
    " move cursor below greeting
    call cursor('''+dplus+u'''%(after_greeting)d,1)

    " start insert mode
    star
'''
                    script += u'''
en
'''
                    vimscripts[edit_headers][posting_style][use_signature][use_placeholder] = vimscript_tidy(script)
