import json

try:
    import argparse
except ImportError:
    from ..deps import argparse


def fetch_parameters_from_json(filename, key):
    with file(filename) as f:
        doc = json.load(f)
    if key in ('', '/'):
        return doc
    for step in key.split('/'):
        try:
            doc = doc[step]
        except KeyError:
            raise Exception("Key %s not found in JSON document '%s'" % (key, filename))
    return doc


def parameter_pair(string):
    """Split a string based on the '=' delimiter into a pair of strings.

    It is illegal for the first string to contain a '=' (since it will be split)
    It is legal for the second string to contain the '=' character

    :param string: Parameter string of the form, 'PATH=/usr/bin'
    :return: Parameter tuple of the form ('PATH','/usr/bin')
    """
    try:
        p1, p2 = string.split('=', 1)
        return p1, p2
    except:
        raise argparse.ArgumentTypeError('Unable to parse as parameter: %r' % string)