import pprint
import os
from os.path import join as pjoin
import sys
from collections import defaultdict

from ..formats.marked_yaml import load_yaml_from_file, is_null, marked_yaml_load
from .utils import substitute_profile_parameters, to_env_var
from .. import core
from .exceptions import ProfileError, PackageError


class PackageType(object):
    """
    Instances are used as the type of parameters of various package types
    """
    def __init__(self, contract):
        self.contract = contract

    def __eq__(self, other):
        return type(self) is type(other) and self.contract == other.contract

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return 'package(%s)' % self.contract


def parse_deps(doc, when='True'):
    """
    Parses the ``dependencies`` section of `doc` into a list of `Parameter` instances
    and constraints. Note that we don't distinguish run-deps and build-deps here.
    """
    deps_section = doc.get('dependencies', {})
    build_deps = deps_section.get('build', [])
    run_deps = deps_section.get('run', [])

    # Produce { dep_name : is_required }
    deps = {}
    for section_lst in [build_deps, run_deps]:
        section_deps = {}  # name -> required
        for x in section_lst:
            required = not x.endswith('?')
            if not required:
                x = x[:-1]
            if x in section_deps:
                raise PackageError(x, 'dependency %s repeated' % x)
            section_deps[x] = required
        for x, required in section_deps.items():
            deps[x] = deps.get(x, False) or required
    # Turn that into Parameter instances and constraints
    dep_params = dict([(name, Parameter(name=name, type=PackageType(name), declared_when=when, doc=name))
                       for name in deps.keys()])
    constraints = ['not (%s) or (%s is not None)' % (when, x) for x, required in deps.items() if required]
    return dep_params, constraints


class DictRepr(object):
    def _repr_dict(self):
        return self.__dict__

    def __repr__(self):
        d = '\n'.join(['  ' + line for line in pprint.pformat(self._repr_dict()).split('\n')])
        return '<%s\n%s\n>' % (self.__class__.__name__, d)


class Parameter(DictRepr):
    """
    Declaration of a parameter in a package.
    """
    TYPENAME_TO_TYPE = {'bool': bool, 'str': str, 'int': int}
    def __init__(self, name, type, default=None, declared_when='True', doc=None):
        """
        doc: only used for exceptions
        """
        self.name = name
        self.type = type
        self.default = default
        self.declared_when = declared_when
        self._doc = doc

    def _check_package_value(self, value):
        return isinstance(value, Package) and value.name == self.type.contract

    def check_type(self, value, node=None):
        if isinstance(self.type, PackageType):
            if not self._check_package_value(value):
                raise PackageError(node, 'Parameter %s must be a package' % self.name)
        elif not isinstance(value, self.type):
            raise PackageError(node, 'Parameter %s has value %r which is not of type %r' % (
                self.name, value, self.type))

    @staticmethod
    def parse_from_yaml(doc, when='True'):
        if 'when' in doc:
            when = '(%s) and (%s)' % (when, doc['when'])
        type = Parameter.TYPENAME_TO_TYPE[doc.get('type', 'str')]
        return Parameter(name=doc['name'],
                         type=type,
                         default=doc.get('default', None),
                         declared_when=when,
                         doc=doc)

    def merge_with(self, other_param):
        """
        Merges together two parameter declarations (from different YAML files
        with different with-clauses).

        For now we require 'type' and 'default' to be the same; these should
        be refactored into constraints eventually at which point we can merge
        them better.
        """
        if self.name != other_param.name:
            raise ValueError()
        for attr in ('type', 'default'):
            a = getattr(self, attr)
            b = getattr(other_param, attr)
            if a != b:
                raise PackageError(self._doc, 'Parameter %s declared with conflicting %s: %s and %s' % (
                    self.name, attr, a, b))

        declared_when = '(%s) or (%s)' % (self.declared_when, other_param.declared_when)
        return Parameter(name=self.name, type=self.type, default=self.default, declared_when=declared_when,
                         doc=self._doc)



class Package(DictRepr):
    """
    Represents the package on an abstract level: Which name does it have,
    which parameters and dependencies does it have. Also allows to instantiate
    it with a given selection of parameters; returning a PackageSpec.

    """
    def __init__(self, name, parameters, constraints, condition_to_yaml_file):
        """
        Parameters
        ----------
        name:
            Name of package.

        parameters: dict { str: Parameter }
            Parameters this package takes

        constraints: list of str
            Constraints on parameters that must be satisfied to use package

        condition_to_yaml_file : dict { str/None: PackageYAML}
            Dict of when-clause the PackageYAML instance containing the
            definition. The default to fall back for for no matching
            clause has key `None`.
        """
        self.name = name
        self.parameters = parameters
        self.constraints = constraints
        self.condition_to_yaml_file = condition_to_yaml_file

    @staticmethod
    def create_from_yaml_files(yaml_files):
        """
        Construct the Package from a set of PackageYAML instances.
        Parameters and dependencies-as-parameters are extracted from the
        full set of YAML files.
        """
        parameters = {}
        constraints = []

        def add_param(param):
            if param.name in parameters:
                param = parameters[param.name].merge_with(param)
            parameters[param.name] = param

        if len(yaml_files) == 0:
            raise ValueError('Need at least one PackageYaml')
        name = yaml_files[0].used_name
        # Sanity checks
        for f in yaml_files:
            if f.used_name != name:
                raise ValueError('Inconsistent PackageYAML passed')
            if not f.primary and 'when' not in f.doc:
                raise PackageError(f.doc, 'Two specs found for package %s without a when-clause' % name)

        primary_lst = [f for f in yaml_files if f.primary]
        if len(primary_lst) != 1:
            raise ValueError('Exactly one PackageYAML should be primary')

        # Find the explicit expression for the 'primary when'
        otherwise = 'not %s' % ' and not '.join(
            '(%s)' % f.doc['when'] for f in yaml_files if 'when' in f.doc)

        constraints = []
        for f in yaml_files:
            when = f.doc.get('when', otherwise)
            # Add explicit parameters
            for x in f.doc.get('parameters', []):
                add_param(Parameter.parse_from_yaml(x, when))
                required = x.get('required', 'default' not in x)
                if required:
                    constraints.append('not (%s) or (%s is not None)' % (when, x['name']))

            # Add deps parameters
            dep_params, dep_constraints = parse_deps(f.doc, when=when)
            for p in dep_params.values():
                add_param(p)
            constraints.extend(dep_constraints)

        condition_to_yaml_file = dict([(x.doc.get('when', None), x) for x in yaml_files])
        return Package(name, parameters, constraints, condition_to_yaml_file)

    def typecheck_parameter_set(self, param_values, node=None):
        """
        Type-checks the given parameters, and also checks that enough parameters
        are provided. Raises PackageError if there is a problem.
        """
        declared = self.get_declared(param_values, node)
        for param_name, value in declared.items():
            self.parameters[param_name].check_type(value, node=node)

    def get_failing_constraints(self, param_values, node=None):
        """
        In constraints, all parameters are always available regardless of declared_when,
        because most constraints have been combined with other constraints across
        YAML files.

        Raises NameError if a required parameter is not available.

        node: for exception location
        """
        result = []
        for constraint in self.constraints:
            if not eval(constraint, {}, param_values):
                result.append(constraint)
        return result

    def get_declared(self, param_values, node=None):
        declared = {}  # the subset of param_values for parameters that have been declared, with defaults filled in
        for param in self.parameters.values():
            try:
                is_declared = eval(param.declared_when, {}, dict(param_values))
            except NameError as e:
                raise PackageError(node, 'Lacking a parameter needed to determine if %s should '
                                   'be declared: %r' % (param.name, e))
            if is_declared:
                declared[param.name] = param_values.get(param.name, param.default)
        return declared

    def instantiate(self, parameter_values):
        pass



class PackageYAML(object):
    """
    Holds content of a package yaml file

    The content is unmodified except for `{{VAR}}` variable expansion.

    Attributes
    ----------

    doc : dict
        The deserialized yaml source

    used_name : str
        See constructor

    in_directory : bool
        Whether the yaml file is in its private package directory that
        may contain other files.

    primary : bool
        Whether this is the primary YAML file allowed to have a `parameters`
        section.

    filename : str
        Full qualified name of the package yaml file

    hook_filename : str or ``None``
        Full qualified name of the package ``.py`` hook file, if it
        exists.
    """

    def __init__(self, used_name, filename, primary, in_directory):
        """
        Constructor

        Parameters
        ----------

        used_name : str
            The actual package name (as overridden by ``use:``, if
            present. E.g. ``mpich``, and not the virtual package
            name``mpi``).

        filename : str
            Full qualified name of the package yaml file

        primary : str
            Whether this is the primary YAML file allowed to have a
            `parameters` section.

        in_directory : boolean
            Whether the package yaml file is in its own directory.
        """
        print filename, primary
        self.used_name = used_name
        self.filename = filename
        self.primary = primary
        self._init_load(filename)
        self.in_directory = in_directory
        hook = os.path.abspath(pjoin(os.path.dirname(filename), used_name + '.py'))
        self.hook_filename = hook if os.path.exists(hook) else None

    def _init_load(self, filename):
        doc = load_yaml_from_file(filename)
        # YAML-level pre-processing
        doc = preprocess_default_to_parameters(doc)
        # End pre-precessing
        self.doc = doc

    def __repr__(self):
        return self.filename

    @property
    def dirname(self):
        """
        Name of the package directory.

        Returns
        -------

        String, full qualified name of the directory containing the
        yaml file.

        Raises
        ------

        A ``ValueError`` is raised if the package is a stand-alone
        yaml file, that is, there is no package directory.
        """
        if self.in_directory:
            return os.path.dirname(self.filename)
        else:
            raise ValueError('stand-alone package yaml file')


class PackageSpec(object):
    """
    Wraps a package spec document to provide some facilities (act on it/understand it).

    The document provided to the constructor should be a complete stand-alone
    specification. The `load` staticmethod is available to load a package spec
    from a profile, this includes pre-preprocessing to assemble together the
    package spec with its ancestor specifications (given in the `extends` clause).
    """
    def __init__(self, name, doc, hook_files, parameters):
        self.name = name
        self.doc = doc
        self.hook_files = hook_files
        deps = doc.get('dependencies', {})
        self.build_deps = deps.get('build', [])
        self.run_deps = deps.get('run', [])
        self.parameters = parameters
        if not isinstance(self.build_deps, list) or not isinstance(self.run_deps, list):
            raise TypeError('dependencies must be a list')

    @staticmethod
    def load(profile, name):
        """
        Loads a single package from a profile.

        Includes ancestors, which are merged in as appropriate. This
        involves a transform pipeline to put the spec on a simple
        format where all information in ancestors is inlined, and
        stages are ordered.

        Parameters
        ----------

        profile : :class:`~hashdist.spec.profile.Profile`
            The profile, which defines parameters to be used.

        name : str
            The package name. This may be different from the name of
            the yaml file if you override ``pkg_name: {use:
            alternate_name}`` in the profile.
        """
        package_parameters = defaultdict(str, profile.parameters)
        package_parameters.update(profile.packages.get(name, {}))
        package_parameters['package'] = name
        from package_loader import PackageLoader
        loader = PackageLoader(name, package_parameters,
                               load_yaml=profile.load_package)
        return PackageSpec(name, loader.stages_topo_ordered(),
                           loader.get_hook_files(), loader.parameters)

    def fetch_sources(self, source_cache):
        for source_clause in self.doc.get('sources', []):
            source_cache.fetch(source_clause['url'], source_clause['key'], self.name)

    def assemble_build_script(self, ctx):
        """
        Return the build script.

        As a side effect, all referenced files are stored in the build
        context.

        Returns:
        --------

        String. A bash script that should be run to build the package.
        """
        lines = ['set -e', 'export HDIST_IN_BUILD=yes']
        for stage in self.doc['build_stages']:
            lines += ctx.dispatch_build_stage(stage)
        return '\n'.join(lines) + '\n'

    def assemble_build_spec(self, source_cache, ctx, dependency_id_map, dependency_packages, profile):
        """
        Return the ``build.json`` buildspec.

        As a side effect, the build script (see
        :meth:`assemble_build_script`) that should be run to build the
        package is uploaded to the given source cache.

        Arguments:
        ----------

        source_cache : :class:`hashdist.core.source_cache.SourceCache`
            The source cache where the build script is to be stored.

        ctx : :class:`hashdist.spec.hook_api.PackageBuildContext`
            Part of the hook api

        Returns:
        --------

        The ``build.json`` for building the package.
        """
        assert ctx.parameters == self.parameters  # TODO: why duplicate the parameters?

        if isinstance(dependency_id_map, dict):
            dependency_id_map = dependency_id_map.__getitem__
        imports = []
        build_deps = self.doc.get('dependencies', {}).get('build', [])
        for dep_name in build_deps:
            imports.append({'ref': '%s' % to_env_var(dep_name), 'id': dependency_id_map(dep_name)})

        dependency_commands = []
        for dep_name in self.build_deps:
            dep_pkg = dependency_packages[dep_name]
            dependency_commands += dep_pkg.assemble_build_import_commands()

        build_script_key = self._store_files(source_cache, ctx, profile)
        build_spec = self._create_build_spec(imports,
            dependency_commands, self._postprocess_commands(),
            [{'target': '.', 'key': build_script_key}])
        return build_spec

    def _store_files(self, source_cache, ctx, profile):
        """
        Store all referenced files in the source cache

         Arguments:
        ----------

        source_cache : :class:`hashdist.core.source_cache.SourceCache`
            The source cache where the build script and files are stored.

        ctx : :class:`hashdist.spec.hook_api.PackageBuildContext`
            Part of the hook api

        profile : :class:`hashdist.spec.profile.Profile`
            The profile, which knows how to find files that are
            referenced in the package.

        Returns:
        --------

        The key associated to the files in the source cache.
        """
        build_script = self.assemble_build_script(ctx)
        files = {}
        for to_name, from_name in ctx._bundled_files.iteritems():
            p = profile.find_package_file(self.name, from_name)
            if p is None:
                raise ProfileError(from_name, 'file "%s" not found' % from_name)
            with open(profile.resolve(p)) as f:
                files['_hashdist/' + to_name] = f.read()
        files['_hashdist/build.sh'] = build_script
        return source_cache.put(files)

    def assemble_link_dsl(self, target, link_type='relative'):
        """
        Creates the input document to ``hit create-links`` from the information in a package
        description.
        """
        link_action_map = {'relative':'relative_symlink',
                           'absolute':'absolute_symlink',
                           'copy':'copy'}

        ref = to_env_var(self.name)
        rules = []
        for in_stage in self.doc['profile_links']:
            if 'link' in in_stage:
                select = substitute_profile_parameters(in_stage["link"], self.parameters)
                rules.append({
                    "action": link_action_map[link_type],
                    "select": "${%s_DIR}/%s" % (ref, select),
                    "prefix": "${%s_DIR}" % ref,
                    "target": target,
                    "dirs": in_stage.get("dirs", False)})
            elif 'exclude' in in_stage:
                select = substitute_profile_parameters(in_stage["exclude"], self.parameters)
                rules.append({"action": "exclude",
                              "select": select})
            elif 'launcher' in in_stage:
                select = substitute_profile_parameters(in_stage["launcher"], self.parameters)
                if link_type != 'copy':
                    rules.append({"action": "launcher",
                                  "select": "${%s_DIR}/%s" % (ref, select),
                                  "prefix": "${%s_DIR}" % ref,
                                  "target": target})
            elif 'copy' in in_stage:
                select = substitute_profile_parameters(in_stage["copy"], self.parameters)
                rules.append({"action": "copy",
                    "select": "${%s_DIR}/%s" % (ref, select),
                    "prefix": "${%s_DIR}" % ref,
                    "target": target,
                    "dirs": in_stage.get("dirs", False)})
            else:
                raise ValueError('Need either "copy", "link", "launcher" or "exclude" '
                                 'key in profile_links entries')
        return rules

    def assemble_build_import_commands(self):
        """
        Return the ``when_build_dependency`` commands from dependencies.
        """
        cmds = [self._process_when_build_dependency(env_action)
                for env_action in self.doc.get('when_build_dependency', [])]
        return cmds

    def _process_when_build_dependency(self, action):
        action = dict(action)
        if not ('prepend_path' in action or 'append_path' in action or 'set' in action):
            raise ValueError('when_build_dependency action must be one of '
                             'prepend_path, append_path, set')
        value = substitute_profile_parameters(action['value'], self.parameters)
        value = value.replace('${ARTIFACT}', '${%s_DIR}' % to_env_var(self.name))
        if '$' in value.replace('${', ''):
            # a bit crude, but works for now -- should properly disallow non-${}-variables,
            # in order to prevent $ARTIFACT from cropping up
            raise ProfileError(action['value'].start_mark, 'Please use "${VAR}", not $VAR')
        action['value'] = value
        return action

    def _create_build_spec(self, imports,
                          dependency_commands, postprocess_commands,
                           extra_sources=()):
        parameters = self.parameters
        if 'BASH' not in parameters:
            raise ProfileError(self.doc, 'BASH must be provided in profile parameters')

        # sources
        sources = list(extra_sources)
        for source_clause in self.doc.get("sources", []):
            target = source_clause.get("target", ".")
            sources.append({"target": target, "key": source_clause["key"]})

        # build commands
        commands = list(dependency_commands)
        commands.append({"set": "BASH", "nohash_value": parameters['BASH']})
        if 'PATH' in parameters:
            commands.insert(0, {"set": "PATH", "nohash_value": parameters['PATH']})
        commands.append({"cmd": ["$BASH", "_hashdist/build.sh"]})
        commands.extend(postprocess_commands)

        # assemble
        build_spec = {
            "name": self.name,
            "build": {
                "import": imports,
                "commands": commands,
                },
            "sources": sources,
            }
        return core.BuildSpec(build_spec)

    def _postprocess_commands(self):
        hit_args = []
        for stage in self.doc.get('post_process', []):
            for arg in stage.get('hit', []):
                hit_args.append('--' + arg)
        if len(hit_args) == 0:
            return []
        return [{'hit': ['build-postprocess'] + hit_args}]


def preprocess_default_to_parameters(doc):
    def guess_type(value):
        if value in ('true', 'false'):
            return bool
        else:
            try:
                int(value)
            except ValueError:
                return str
            else:
                return int

    if 'defaults' not in doc:
        return doc
    doc = dict(doc)  # copy
    parameters = doc['parameters'] = []
    defaults = doc.pop('defaults')
    parameters = []
    for key, value in defaults.items():
        parameters.append({'name': key, 'default': value, 'type': guess_type(value)})
    return doc
