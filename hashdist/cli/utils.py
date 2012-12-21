import json

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
