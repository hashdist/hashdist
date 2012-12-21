import json

def fetch_parameters_from_json(filename, key):
    with file(filename) as f:
        doc = json.load(f)
    for step in key.split('/'):
        doc = doc[step]
    return doc
