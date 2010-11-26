# -*- coding: utf-8 -*-

# Copyright (C) 2010 Johannes Weißl
# License GPLv3+:
# GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.
# This is free software: you are free to change and redistribute it.
# There is NO WARRANTY, to the extent permitted by law

"""Get S/MIME and PGP public/secret keys/addresses."""

try:
    import pyme
    import pyme.core
    import pyme.pygpgme
    HAVE_CRYPTO = True
except ImportError, e:
    HAVE_CRYPTO = False
    IMPORT_ERROR = e


PROTO_PGP   = 1 << 0
PROTO_SMIME = 1 << 1
PROTO_ALL   = PROTO_PGP | PROTO_SMIME

def _gpgme_proto(proto):
    """Map proto constants to internal gpgme ones."""
    _gpgme_proto_mapping = {
        PROTO_PGP   : pyme.pygpgme.GPGME_PROTOCOL_OpenPGP,
        PROTO_SMIME : pyme.pygpgme.GPGME_PROTOCOL_CMS,
        PROTO_ALL   : pyme.pygpgme.GPGME_PROTOCOL_OpenPGP
    }
    return _gpgme_proto_mapping[proto]

def _get_valid_subkey(key, check_attr):
    """Check if key has a valid subkey, and return it's keyid or None.

    check_attr is the attribute of the subkey used for checking, e.g.:
      * 'can_encrypt'  for public keys
      * 'secret'       for private keys

    """
    valid = 0
    for subkey in key.subkeys:
        keyid = subkey.keyid
        if not keyid or subkey.expired or subkey.invalid or subkey.revoked or subkey.disabled:
            break
        valid += getattr(subkey, check_attr)
        if valid:
            break
    return subkey.keyid if valid else None

def seq_any_endswith(s, suffix):
    """Return True if at least one key in sequence s ends with suffix."""
    for x in s:
        if x.endswith(suffix):
            return x
    return None

class Context(object):
    def __init__(self):
        # necessary to prevent segfault in some older versions of GPGME
        pyme.core.check_version()
        self.ctx = pyme.core.Context()
    def get_pubkey_emails(self, proto=PROTO_ALL):
        """Return a set of all email addresses to which encrypted messages
        can be sent."""
        return self._get_pubkey_emails(_gpgme_proto(proto))
    def get_seckeys(self, proto=PROTO_ALL):
        """Return a dictionary {email: keyid} for all email addresses which
        can be used for decrypting."""
        return self._get_seckeys(_gpgme_proto(proto))
    def get_seckeys_unique(self, proto=PROTO_ALL, preferred=''):
        keys = self.get_seckeys(proto=proto)
        n = {}
        for email in keys:
            if preferred:
                key = seq_any_endswith(keys[email], preferred)
                if key:
                    n[email] = key
                    continue
            n[email] = keys[email].pop()
        return n
    def _get_pubkey_emails(self, gpgme_proto):
        """Internal method for get_pubkey_emails()."""
        pyme.pygpgme.gpgme_set_protocol(self.ctx.wrapped, gpgme_proto)
        emails = set()
        for key in self.ctx.op_keylist_all(None, 0):
            if _get_valid_subkey(key, 'can_encrypt'):
                for uid in key.uids:
                    email = uid.email.lstrip('<').rstrip('>').lower()
                    if email:
                        emails.add(email)
        return emails
    def _get_seckeys(self, gpgme_proto):
        """Internal method for get_seckeys()."""
        pyme.pygpgme.gpgme_set_protocol(self.ctx.wrapped, gpgme_proto)
        keys = {}
        for key in self.ctx.op_keylist_all(None, 1):
            keyid = _get_valid_subkey(key, 'secret')
            if keyid:
                for uid in key.uids:
                    email = uid.email.lstrip('<').rstrip('>').lower()
                    if email:
                        if email in keys:
                            keys[email].add(keyid)
                        else:
                            keys[email] = set([keyid])
        return keys
