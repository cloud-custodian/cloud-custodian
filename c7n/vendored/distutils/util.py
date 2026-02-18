"""distutils.util

Miscellaneous utility functions -- anything that doesn't fit into
one of the other *util.py modules.

Source: https://github.com/python/cpython/blob/6fea61a9e02260648fbec204e9caac6d5176cc7b/Lib/distutils/util.py
"""


def strtobool(val):
    """Convert a string representation of truth to true (1) or false (0).

    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'; case insensitive.
    Raises ValueError if 'val' is anything else.
    """
    val = val.lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return 1
    elif val in ('n', 'no', 'f', 'false', 'off', '0'):
        return 0
    else:
        raise ValueError("invalid truth value %r" % (val,))
