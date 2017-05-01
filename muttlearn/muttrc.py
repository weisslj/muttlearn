# -*- coding: utf-8 -*-

# Copyright (C) 2010-2017 Johannes Weißl
# License GPLv3+:
# GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.
# This is free software: you are free to change and redistribute it.
# There is NO WARRANTY, to the extent permitted by law

import re
import os.path
from subprocess import Popen, PIPE
import collections
import locale

__all__ = ['Muttrc']

def concat_line_splits(lines):
    result = []
    tmp = ''
    for line in lines:
        if line.endswith('\\'):
            tmp += line[:-1]
        elif tmp != '':
            result.append(tmp + line)
            tmp = ''
        else:
            result.append(line)
    return result

def str2value(s, t, cs):
    if t == bool:
        if s == 'yes':
            return True
        elif s == 'no':
            return False
        else:
            raise 'Type Error'
    elif t == int:
        return int(s)
    elif type(s) == str:
        return unicode(s, cs, 'replace')
    return s

def value2str(value, cs):
    t = type(value)
    if t == bool:
        return 'yes' if value else 'no'
    elif t == int:
        return str(value)
    elif t == unicode:
        return value.encode(cs)
    return value

def expand_signature(sig):
    if not sig:
        return u''
    output = ''
    enc = locale.getpreferredencoding()
    if sig.endswith(u'|'):
        output = Popen(sig[:-1], shell=True, stdout=PIPE).communicate()[0]
    else:
        try:
            f = open(os.path.expanduser(sig), 'r')
            output = f.read()
        except IOError:
            pass
        else:
            f.close()
    output = unicode(output, enc)
    if output.endswith(u'\n'):
        output = output[:-1]
    return output

class Muttrc(object):
    _re_variable = re.compile(r'\$[A-Za-z][A-Za-z0-9_]*')
    _re_variable_letter = re.compile(r'[A-Za-z0-9_]')
    _re_comment = re.compile(r'^[ \t]*(?:#.*|)$')
    def __init__(self, defaults=None):
        self.defaults = defaults.copy() if defaults else {}
        self.variables = self.defaults.copy()
        self.alternates = []
        self.unalternates = []
        self.subscribe = []
        self.unsubscribe = []
        self.lists = []
        self.unlists = []
        self.address_groups = collections.defaultdict(lambda: [])
        self.mailboxes = []
        self.charset = self.get('charset') or locale.getpreferredencoding()
        self.error = None
    def parse(self, path):
        try:
            f = open(path)
            lines = [l.rstrip('\n') for l in f]
        except IOError:
            self.error = 'can not open config file "%s"' % path
            return
        else:
            f.close()
        lines[:] = concat_line_splits(lines)
        lines[:] = [l for l in lines if not self._re_comment.match(l)]
        for line in lines:
            lst = self.parse_line(line)
            for cmd in lst:
                c = cmd[0]
                args = cmd[1:]
                # every command needs an argument...
                if not args:
                    self.error = 'command "%s" needs an argument' % c
                    continue
                try:
                    f = getattr(self, 'handle_%s_cmd' % c)
                except AttributeError:
                    self.error = 'unknown command "%s"' % c
                    continue
                f(args)
    def merge_defaults(self, defaults):
        for k, v in defaults.items():
            if k not in self.defaults:
                self.defaults[k] = v
            if k not in self.variables:
                self.variables[k] = v
    def get(self, key, default=None):
        if key in self.variables:
            return self.variables[key]
        return default
    def toggle(self, key):
        if key in self.variables:
            val = self.variables[key]
            if type(val) == bool:
                self.variables[key] = False if val else True
            elif val == 'no':
                self.variables[key] = 'yes'
            elif val == 'yes':
                self.variables[key] = 'no'
    def unset(self, key):
        if key in self.variables:
            val = self.variables[key]
            if type(val) == bool:
                self.variables[key] = False
            # mutt doesn't unset numbers
            elif type(val) != int:
                self.variables[key] = ''
    def reset(self, key):
        if key in self.defaults:
            self.variables[key] = self.defaults[key]
    def set(self, key, value):
        if key == 'config_charset':
            self.charset = value
        if key in self.variables:
            value_type = type(self.variables[key])
        else:
            value_type = type(value)
        value = str2value(value, value_type, self.charset)
        self.variables[key] = value
    def dump(self, key, enc=locale.getpreferredencoding()):
        val = self.variables[key]
        t = type(val)
        if t == bool:
            val_str = ' is set' if val else ' is unset'
        elif t == int:
            val_str = '=%d' % val
        else:
            val_str = '="%s"' % value2str(val, enc).replace('"', '\\"')
        return '%s%s' % (key, val_str)
    def _is_in_address_group(self, addr, add, remove):
        for expr in add:
            if re.match(expr, addr):
                break
        else:
            return False
        for expr in remove:
            if re.match(expr, addr):
                return False
        return True
    def is_this_me(self, addr):
        return self._is_in_address_group(addr, self.alternates, self.unalternates)
    def is_this_subscribed(self, addr):
        return self._is_in_address_group(addr, self.subscribe, self.unsubscribe)
    def is_this_listed(self, addr):
        return self._is_in_address_group(addr, self.lists, self.unlists)
    def expand_command(self, val):
        p = Popen(val, shell=True, stdout=PIPE)
        output = p.stdout.readline().rstrip('\n')
        p.wait()
        return output
    def expand_path(self, path):
        if not path:
            return path
        first = path[0]
        rest = path[1:]
        if first == '!':
            path = self.expand_path(self.variables['spoolfile']) + rest
        elif first == '>':
            path = self.expand_path(self.variables['mbox']) + rest
        elif first == '<':
            path = self.expand_path(self.variables['record']) + rest
        elif first == '~':
            path = os.getenv('HOME') + rest
        elif first == '=' or first == '+':
            path = os.path.join(self.expand_path(self.variables['folder']), rest)
        return path
    def expand_variable(self, var):
        if var in self.variables:
            return value2str(self.variables[var], self.charset)
        return os.getenv(var, '')
    def handle_set_cmd(self, args):
        while args:
            args = self._handle_set_cmd(args)
    def handle_unset_cmd(self, args):
        for arg in args:
            self.unset(arg)
    def handle_reset_cmd(self, args):
        for arg in args:
            self.reset(arg)
    def handle_toggle_cmd(self, args):
        for arg in args:
            self.toggle(arg)
    def _handle_set_cmd(self, args):
        unset = False
        toggle = False
        needs_value = False
        has_value = False
        args_needed = 1
        if len(args) < args_needed:
            self.error = 'command \'set\' needs an argument'
            return
        var = str(args[0])
        val = 'yes'
        if len(var) > len('no') and var.startswith('no'):
            unset = True
            var = var[2:]
        elif len(var) > len('inv') and var.startswith('inv'):
            toggle = True
            var = var[3:]
        if len(args) > 1 and args[1] == '=':
            args_needed = 3
            needs_value = True
            if len(args) > 2:
                val = args[2]
                has_value = True
        if (unset or toggle) and needs_value:
            self.error = 'variables cannot start with "no" or "inv" (%s)' % var
            return
        if needs_value and not has_value:
            self.error = 'no value specified for "set %s ="' % var
        if unset:
            self.unset(var)
        elif toggle:
            self.toggle(var)
        else:
            self.set(var, val)
        return args[args_needed:]
    def handle_source_cmd(self, args):
        path = os.path.expanduser(args[0])
        if os.path.exists(path):
            self.parse(path)
    def _handle_address_group_add_cmd(self, args, add, remove):
        expect_group = False
        group = None
        for arg in args:
            if expect_group:
                group = str(arg)
                expect_group = False
                continue
            if arg == '-group':
                expect_group = True
            else:
                expr = str(arg)
                add.append(expr)
                if group:
                    self.address_groups[group].append(expr)
    def _handle_address_group_remove_cmd(self, args, add, remove):
        expect_group = False
        group = None
        for arg in args:
            if expect_group:
                group = arg
                expect_group = False
                for expr in self.address_groups[group]:
                    if expr in self.alternates:
                        add.remove(expr)
                    else:
                        remove.append(expr)
                continue
            if arg == '-group':
                expect_group = True
            elif arg == '*':
                del add[:]
            else:
                if arg in self.alternates:
                    add.remove(arg)
                else:
                    remove.append(arg)
    def handle_alternates_cmd(self, args):
        self._handle_address_group_add_cmd(args, self.alternates, self.unalternates)
    def handle_unalternates_cmd(self, args):
        self._handle_address_group_remove_cmd(args, self.alternates, self.unalternates)
    def handle_subscribe_cmd(self, args):
        self._handle_address_group_add_cmd(args, self.subscribe, self.unsubscribe)
    def handle_unsubscribe_cmd(self, args):
        self._handle_address_group_remove_cmd(args, self.subscribe, self.unsubscribe)
    def handle_lists_cmd(self, args):
        self._handle_address_group_add_cmd(args, self.lists, self.unlists)
    def handle_unlists_cmd(self, args):
        self._handle_address_group_remove_cmd(args, self.lists, self.unlists)
    def handle_mailboxes_cmd(self, args):
        for arg in args:
            path = os.path.realpath(self.expand_path(arg))
            self.mailboxes.append(path)
    def handle_unmailboxes_cmd(self, args):
        for arg in args:
            if arg == '*':
                del self.mailboxes[:]
                continue
            path = os.path.realpath(self.expand_path(arg))
            if path in self.mailboxes:
                del self.mailboxes[path]
    def parse_line(self, line):
        result = []
        command = []
        escaped = False
        in_quotes = None
        in_variable = False
        variable = ''
        shell_command = ''
        buf = ''
        for i, c in enumerate(line):
            if in_variable and not self._re_variable_letter.match(c):
                buf += self.expand_variable(variable)
                in_variable = False
                variable = ''
            if escaped:
                escaped = False
                if c == 'r':
                    c = '\r'
                elif c == 'n':
                    c = '\n'
                buf += c
                continue
            if c == '\\' and not in_quotes == 'single':
                escaped = True
                continue
            if in_quotes:
                if in_quotes == 'single':
                    if c == "'":
                        in_quotes = None
                    else:
                        buf += c
                    continue
                elif in_quotes == 'double':
                    if c == '"':
                        in_quotes = None
                elif in_quotes == 'backticks':
                    if c == '`':
                        buf += self.expand_command(shell_command)
                        in_quotes = None
                        shell_command = ''
                    else:
                        shell_command += c
                    continue
            if (c == ' ' or c == '\t') and not in_quotes:
                if buf:
                    command.append(buf)
                    buf = ''
            elif c == '"':
                in_quotes = 'double'
            elif c == "'" and not in_quotes: 
                in_quotes = 'single'
            elif c == '`' and not in_quotes:
                in_quotes = 'backticks'
            elif c == '$':
                in_variable = True
            elif c == ';' and not in_quotes:
                if buf:
                    command.append(buf)
                    buf = ''
                result.append(command)
                command = []
            elif c == '#' and not in_quotes:
                i -= 1
                break
            elif c == '=' and not in_quotes and command and command[0] == 'set':
                if command[-1] == '=':
                    buf += c
                else:
                    if buf:
                        command.append(buf)
                    command.append(c)
                    buf = ''
            else:
                if in_variable:
                    variable += c
                else:
                    buf += c
        if buf:
            command.append(buf)
        result.append(command)
        return result
