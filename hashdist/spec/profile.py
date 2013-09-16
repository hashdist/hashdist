"""

Not supported:

 - Diamond inheritance

"""

import os
import shutil
from os.path import join as pjoin

from .marked_yaml import marked_yaml_load
from .utils import substitute_profile_parameters
from .. import core

class ConflictingProfilesError(Exception):
    pass

class FileNotFoundError(Exception):
    def __init__(self, msg, relname):
        Exception.__init__(self, msg)
        self.relname = relname

class FileResolver(object):
    """
    Represents a tree of directories containing profile information.
    Is used to resolve which file to load things from.
    """
    def __init__(self, children):
        self.children = children


class Profile(object):
    """

    Profiles acts as nodes in a tree, with `extends` containing the
    parent profiles (which are child nodes in a DAG).
    """
    def __init__(self, basedir, doc_name, doc, extends, rm_on_close=False):
        self.basedir = basedir
        self.doc_name = doc_name
        self.doc = doc
        self.extends = extends
        self.rm_on_close = rm_on_close
        # for now, we require that bases have non-overlapping parameter keys
        self.parameters = {}
        for base in extends:
            for k, v in base.parameters.iteritems():
                if k in self.parameters:
                    raise ConflictingProfilesError('two base profiles set same parameter %s' % k)
                self.parameters[k] = v
        self.parameters.update(doc['parameters'])

    def close(self):
        if self.rm_on_close:
            shutil.rmtree(self.basedir)

    def find_file(self, relname):
        path = pjoin(self.basedir, relname)
        if not os.path.exists(path):
            path = None
            for base in self.extends:
                path_in_base = base.find_file(relname)
                if path_in_base is not None:
                    if path is not None:
                        raise ConflictingProfilesError('file %s found in two different base profiles' % relname)
                    path = path_in_base
        return path

    def get_python_path(self, path=None):
        """
        Constructs a list that can be inserted into sys.path to make
        .py-files in the base subdirectory of this profile and any
        base-profile available.
        """
        if path is None:
            path = []
        for base in self.extends:
            base.get_python_path(path)
        path.insert(0, pjoin(self.basedir, 'base'))
        return path

    def __repr__(self):
        return '<Profile %s>' % pjoin(self.basedir, self.doc_name)

def load_profile(include_doc):
    """
    Loads a Profile given an include document fragment, e.g.::

        profile: profile.yaml
        dir: /path/to/local/directory

    or::

        profile: linux/profile.yaml
        url: git://github.com/hashdist/hashstack.git
        key: git:5aeba2c06ed1458ae4dc5d2c56bcf7092827347e

    The load happens recursively, including fetching any remote
    dependencies.
    """
    profile_rel_file = include_doc['profile']
    assert 'dir' in include_doc
    basedir = include_doc['dir']
    assert os.path.isabs(basedir)
    with open(pjoin(basedir, profile_rel_file)) as f:
        doc = marked_yaml_load(f)
    if 'extends' in doc:
        extends = [load_profile(parent_include) for parent_include in doc['extends']]
        del doc['extends']
    else:
        extends = []
    return Profile(basedir, profile_rel_file, doc, extends, rm_on_close=False)
