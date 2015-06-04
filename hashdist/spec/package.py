from pprint import pprint, pformat
import os
from os.path import join as pjoin
import sys
from collections import defaultdict

from ..formats import marked_yaml
from ..formats.marked_yaml import load_yaml_from_file, is_null, marked_yaml_load
from .utils import substitute_profile_parameters, to_env_var
from .. import core
from .exceptions import ProfileError, PackageError
from .spec_ast import when_transform_yaml, sexpr_and, sexpr_or, sexpr_implies, check_no_sub_conditions, eval_condition
from . import spec_ast


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


def parse_deps_and_constraints(doc, when=None):
    """
    Parses the ``dependencies`` and ``constraints`` section of `doc` into a
    list of `Parameter` instances and constraints.

    The build deps are turned into parameters with the same name, as they are referenced
    in build scripts etc. The run deps are turned into parameters with names ``_run_<name>``.
    """
    parameters = {}
    constraints = []

    for c in doc.get_value('constraints', []):
        when = c.when
        c = spec_ast.evaluate_doc(c, {})  # no when clauses *within* or variable expansions
        constraints.append(sexpr_implies(when, c))

    deps_section = doc.value.get('dependencies', None)
    if deps_section is None or not deps_section.value:
        return parameters, constraints

    build_deps = deps_section.get_value('build', [])
    run_deps = deps_section.get_value('run', [])

    for name_pattern, section_lst in [('%s', build_deps), ('_run_%s', run_deps)]:
        for node in section_lst:
            required = not node.value.startswith('+')
            pkg_name = node.value[1:] if not required else node.value
            param_name = name_pattern % pkg_name
            if param_name in parameters:
                raise PackageError(node, 'dependency %s repeated' % pkg_name)

            dep_when = sexpr_and(when, node.when)
            parameters[param_name] = Parameter(
                name=param_name,
                type=PackageType(pkg_name),
                declared_when=dep_when,
                doc=node)
            if required:
                c = (sexpr_implies(dep_when, '%s is not None' % param_name)
                     if dep_when is not None else
                     '%s is not None' % param_name)
                c = marked_yaml.unicode_node(c, node.start_mark, node.end_mark)
                constraints.append(c)
    return parameters, constraints


class DictRepr(object):
    def _repr_dict(self):
        return self.__dict__

    def __repr__(self):
        d = '\n'.join(['  ' + line for line in pformat(self._repr_dict()).split('\n')])
        return '<%s\n%s\n>' % (self.__class__.__name__, d)


class Parameter(DictRepr):
    """
    Declaration of a parameter in a package.
    """
    TYPENAME_TO_TYPE = {'bool': bool, 'str': basestring, 'int': int}
    def __init__(self, name, type, default=None, declared_when='True', doc=None):
        """
        doc: only used for exceptions
        """
        self.name = name
        self.type = type
        self.default = default
        self.declared_when = declared_when
        self._doc = doc

    def copy_with(self, declared_when=None):
        declared_when = declared_when if declared_when is not None else self.declared_when
        return Parameter(self.name, self.type, self.default, declared_when, self._doc)

    def has_package_type(self):
        return isinstance(self.type, PackageType)

    def _check_package_value(self, value):
        return isinstance(value, PackageInstance) or value is None

    def check_type(self, value, node=None):
        if value is None:
            # non-present parameter is handled by constraints system, not type system,
            # primarily because we want the type to be unified across all when-clauses.
            return
        if self.has_package_type():
            if not self._check_package_value(value):
                raise PackageError(node, 'Parameter %s must be a package of type "%s", not %r' % (
                    self.name, self.type.contract, value))
        elif (not isinstance(value, self.type)
              and not (self.type is bool and isinstance(value, (spec_ast.bool_node, marked_yaml.bool_node)))):
            # ^ second condition hacks around bool not being subclassable
            raise PackageError(node, 'Parameter %s has value %r which is not of type %r' % (
                self.name, value, self.type))

    @staticmethod
    def parse_from_yaml(doc, when=None):
        if not isinstance(doc.value, dict):
            raise PackageError(doc, 'Parameters must be declared as "{name: <name>}"')
        type = Parameter.TYPENAME_TO_TYPE[spec_ast.evaluate_doc(doc.value['type'], {})
                                          if 'type' in doc.value else 'str']
        return Parameter(name=spec_ast.evaluate_doc(doc.value['name'], {}),
                         type=type,
                         default=spec_ast.evaluate_doc(doc.value['default'], {}) if 'default' in doc.value else None,
                         declared_when=when,
                         doc=doc)

    def merge_with(self, other_param, default_from_self=False):
        """
        Merges together two parameter declarations (from different YAML files
        with different with-clauses).

        We require type to be the same.

        If default_from_self is True, we let the default from self win, otherwise
        we require them to be the same.
        """
        if self.name != other_param.name:
            raise ValueError()
        if self.type != other_param.type:
            raise PackageError(self._doc, 'Parameter %s declared with conflicting types' % self.name)
        if not default_from_self and self.default != other_param.default:
            raise PackageError(self._doc, 'Parameter %s declared with conflicting default values' % self.name)
        declared_when = sexpr_or(self.declared_when, other_param.declared_when)
        return Parameter(name=self.name, type=self.type, default=self.default, declared_when=declared_when,
                         doc=self._doc)



class Package(DictRepr):
    """
    Represents the package on an abstract level: Which name does it have,
    which parameters and constraints does it have, and its ancestors. The
    parameters and constraints of its ancestors are copied over.

    Also allows to instantiate it with a given selection of parameters;
    returning a PackageInstance.
    """
    GLOBAL_PARAMETERS = [
        Parameter('BASH', basestring),
        Parameter('package', basestring),
        ]

    def __init__(self, name, parameters, constraints, condition_to_yaml_file,
                 parents=()):
        """
        Call create_from_yaml_files instead of calling constructor directly.

        Parameters
        ----------
        name:
            Name of an abstract package specification. This should be globally
            unique within context of a profile.

        parameters: dict { str: Parameter }
            Parameters this package takes

        constraints: list of str
            Constraints on parameters that must be satisfied to use package

        condition_to_yaml_file : dict { str/None: PackageYAML}
            Dict of when-clause the PackageYAML instance containing the
            definition. The default to fall back for for no matching
            clause has key `None`.

        parents : list of (when, Package)
            Note: The parameters and constraints of parents have already
            been included in `self`
        """
        self.name = name
        self.parameters = dict(parameters)
        self.parameters.update(dict([(p.name, p) for p in self.GLOBAL_PARAMETERS]))
        self.constraints = constraints
        self.condition_to_yaml_file = condition_to_yaml_file
        self.parents = parents
        # Prevent diamond inheritance to keep things simpler
        self.ancestor_names = set()
        for when, parent in parents:
            common = self.ancestor_names.intersection(parent.ancestor_names)
            if common:
                raise PackageError(None, 'Package %s has diamond inheritance (not supported) on: %r' %
                                   (self.name, list(common)))
            self.ancestor_names.update(parent.ancestor_names)
            self.ancestor_names.add(parent.name)

    def get_yaml(self, param_values, node=None):
        candidates = []
        for cond, doc in self.condition_to_yaml_file.items():
            if cond is None:
                continue
            if eval_condition(cond, param_values):
                candidates.append(doc)
        if len(candidates) > 1:
            raise ProfileError(node, 'More than one candidate YAML file '
                               'for package %s (when clauses not specific enough)' % self.name)
        elif len(candidates) == 0:
            try:
                return self.condition_to_yaml_file[None]
            except KeyError:
                raise ProfileError(node, 'No candidate YAML files for package %s (no when clause matches parameters)'
                                   % self.name)
        else:
            return candidates[0]

    @staticmethod
    def create_from_yaml_files(profile, yaml_files):
        """
        Construct the Package from a set of PackageYAML instances.
        Parameters and dependencies-as-parameters are extracted from the
        full set of YAML files.

        profile is used to load any ancestors
        """
        parameters = {}
        constraints = []

        def add_param(param, default_from_self):
            # default_from_self=True is used when including parameters from ancestors; at this point
            # parameters from the package file has already been populated and we
            # use these default values
            if param.name in parameters:
                param = parameters[param.name].merge_with(param, default_from_self=default_from_self)
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
        otherwise = None if len(yaml_files) == 1 else 'not %s' % ' and not '.join(
            '(%s)' % f.doc['when'] for f in yaml_files if 'when' in f.doc)

        # when-transform each document. For now this is only used to parse the extends
        # section, with interpreter-style parsing for the rest
        tdocs = []
        for f in yaml_files:
            doc = marked_yaml.copy_dict_node(f.doc)
            when = doc.pop('when', None)
            tdoc = when_transform_yaml(doc)
            tdoc.when = when
            tdocs.append(tdoc)

        constraints = []
        parents = []
        # First pass: Explicit parameters in leaf-level package specs
        for doc in tdocs:
            when = doc.when if doc.when is not None else otherwise

            # Add explicit parameters.
            for x in doc.get_value('parameters', []):
                param_when = sexpr_and(when, x.when)
                add_param(Parameter.parse_from_yaml(x, param_when), default_from_self=False)
                required = (spec_ast.evaluate_doc(x.value['required'], {})
                            if 'required' in x.value
                            else ('default' not in x.value))
                if required:
                    if param_when is None:
                        constraints.append('%s is not None' % spec_ast.evaluate_doc(x.value['name'], {}))
                    else:
                        constraints.append('not (%s) or (%s is not None)' % (
                            param_when, spec_ast.evaluate_doc(x.value['name'], {})))

            # Add deps parameters
            dep_params, dep_constraints = parse_deps_and_constraints(doc, when=when)
            for p in dep_params.values():
                add_param(p, default_from_self=False)
            constraints.extend(dep_constraints)

        # Second pass: Parameters from ancestors
        for doc in tdocs:
            when = doc.when if doc.when is not None else otherwise

            for parent_name in doc.get_value('extends', []):
                parent_when = sexpr_and(when, parent_name.when)
                parent = profile.load_package(spec_ast.evaluate_doc(parent_name, {}))
                for param in parent.parameters.values():
                    add_param(param.copy_with(declared_when=sexpr_and(parent_when, param.declared_when)),
                              default_from_self=True)
                for constraint in parent.constraints:
                    if parent_when is None:
                        constraints.append(constraint)
                    else:
                        constraints.append('not (%s) or (%s)' % (parent_when, constraint))
                parents.append((parent_when, parent))

        # Attach the YAML files too, we just transform them first to remove the sections
        # parsed above. Group them by their 'when' clause and take the 'when' clause out
        # of document too. Also the document will now be using spec_ast nodes.
        # (TODO: Get rid of PackageYAML in this context, make a new class..)
        condition_to_yaml_file = {}
        for doc, f in zip(tdocs, yaml_files):
            when = doc.when
            for section in ['dependencies', 'parameters', 'extends']:
                doc.value.pop(section, None)
            condition_to_yaml_file[when] = f.copy_with_doc(doc)

        return Package(name, parameters, constraints, condition_to_yaml_file, parents=parents)

    def typecheck_parameter_set(self, param_values, node=None):
        """
        Type-checks the given parameter values, and also checks that enough parameters
        are provided, and returns the subset that is declared.
        Raises PackageError if there is a problem.
        """
        declared = self.get_declared(param_values, node)
        for param_name, value in param_values.items():
            if param_name not in self.parameters:
                raise ProfileError(param_name, 'Parameter "%s" not declared in any variation on package "%s"' %
                                   (param_name, self.name))
            self.parameters[param_name].check_type(value, node=node)
        return declared

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
            if not eval_condition(constraint, param_values):
                result.append(constraint)
        return result

    def get_declared(self, param_values, node=None):
        declared = {}  # the subset of param_values for parameters that have been declared, with defaults filled in
        for param in self.parameters.values():
            try:
                is_declared = eval_condition(param.declared_when, dict(param_values))
            except NameError as e:
                raise PackageError(node, 'Lacking a parameter needed to determine if %s should '
                                   'be declared: %r' % (param.name, e))
            if is_declared:
                declared[param.name] = param_values.get(param.name, param.default)
        return declared

    def check_constraints(self, param_values, node=None):
        for c in self.constraints:
            if not eval_condition(c, param_values):
                raise ProfileError(node, '%s package: constraint not satisfied: "%s"' % (self.name, c))

    def instantiate(self, param_values, node=None):
        package = self.pre_instantiate(param_values, node)
        package.init()
        return package

    def pre_instantiate(self, param_values, node=None):
        self.check_constraints(param_values, node=node)
        return PackageInstance(self, param_values)


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

    def __init__(self, used_name, filename, primary, in_directory, doc=None):
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

        doc : document
            Parsed YAML file, possibly post-processed, assumed to be present
            in the given location. If None it will be loaded.
        """
        self.used_name = used_name
        self.filename = filename
        self.primary = primary
        if doc is None:
            doc = self._init_load(filename)
        self.doc = doc
        self.in_directory = in_directory
        hook = os.path.abspath(pjoin(os.path.dirname(filename), used_name + '.py'))
        self.hook_filename = hook if os.path.exists(hook) else None

    def copy_with_doc(self, doc):
        return PackageYAML(used_name=self.used_name, filename=self.filename, primary=self.primary,
                           in_directory=self.in_directory, doc=doc)

    def _init_load(self, filename):
        doc = load_yaml_from_file(filename)
        if doc is None:
            doc = marked_yaml.dict_node({}, None, None)
        # YAML-level pre-processing
        doc = preprocess_default_to_parameters(doc)
        # End pre-precessing
        return doc

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


class PackageInstance(object):
    """
    Binds a PackageSpec to a set of parameter values.

    This object is made available to template expansion in templates.
    Therefore a lot of the internal routines that belong to a PackageInstance
    are, as a namespace issue, hidden away in the PackageInstanceImpl
    class/`_impl` attribute.

    Because packages can refer to one another cyclically, we need a two-stage
    construction. First construct, then param_values dict remain mutable, then
    call `init()` after which _impl becomes available and the package should
    be considered immutable.
    """
    def __init__(self, spec, param_values):
        self._spec = spec
        self._param_values = param_values

    def init(self):
        self._impl = PackageInstanceImpl(self)

    def __getattr__(self, key):
        try:
            return self._param_values[key]
        except KeyError:
            raise AttributeError("package has no property '%s'" % key)

    def __repr__(self):
        return "%s(%r)" % (self._spec.name, self._param_values)


class PackageInstanceImpl(object):
    """
    Combination of PackageSpec with given parameter values, so that it is ready
    for build script generation and hashing. This contains the part of PackageInstance
    that should only be available to hashdist.spec, not in spec file API.
    """
    def __init__(self, api_part):
        from .package_loader import PackageLoader

        self._spec = api_part._spec
        self._param_values = api_part._param_values

        loader = PackageLoader(self._spec, self._param_values)
        self.doc = loader.doc
        self.hook_files = loader.get_hook_files()
        self.build_deps = dict([(key, value) for key, value in self._param_values.items()
                                if not key.startswith('_run_') and isinstance(value, PackageInstance)])

    def fetch_sources(self, source_cache):
        for source_clause in self.doc.get('sources', []):
            source_cache.fetch(source_clause['url'], source_clause['key'], self._spec.name)

    def assemble_build_spec(self, source_cache, ctx, dependency_id_map, profile):
        """
        Return the ``build.json`` buildspec.

        As a side effect, the build script (see
        :fimc:`assemble_build_script`) that should be run to build the
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
        if isinstance(dependency_id_map, dict):
            dependency_id_map = dependency_id_map.__getitem__

        imports = []
        dependency_commands = []
        for key, value in self.build_deps.items():
            imports.append({'ref': '%s' % to_env_var(key), 'id': dependency_id_map(value)})
            dependency_commands += value._impl.assemble_build_import_commands(key)

        build_script_key = self._store_files(source_cache, ctx, profile)
        build_spec = create_build_spec(
            name=self._spec.name,
            doc=self.doc,
            parameters=self._param_values,
            imports=imports,
            dependency_commands=dependency_commands,
            extra_sources=[{'target': '.', 'key': build_script_key}])
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
        build_script = assemble_build_script(self.doc, ctx)
        files = {}
        for to_name, from_name in ctx._bundled_files.iteritems():
            p = profile.find_package_file(self._spec.name, from_name)
            if p is None:
                raise ProfileError(from_name, 'file "%s" not found' % from_name)
            with open(profile.resolve(p)) as f:
                files['_hashdist/' + to_name] = f.read()
        files['_hashdist/build.sh'] = build_script
        return source_cache.put(files)

    def assemble_link_dsl(self, name_in_using, target, link_type='relative'):
        """
        Creates the input document to ``hit create-links`` from the information in a package
        description.
        """
        link_action_map = {'relative':'relative_symlink',
                           'absolute':'absolute_symlink',
                           'copy':'copy'}

        ref = to_env_var(name_in_using)
        rules = []
        for in_stage in self.doc['profile_links']:
            if 'link' in in_stage:
                select = substitute_profile_parameters(in_stage["link"], self._param_values)
                rules.append({
                    "action": link_action_map[link_type],
                    "select": "${%s_DIR}/%s" % (ref, select),
                    "prefix": "${%s_DIR}" % ref,
                    "target": target,
                    "dirs": in_stage.get("dirs", False)})
            elif 'exclude' in in_stage:
                select = substitute_profile_parameters(in_stage["exclude"], self._param_values)
                rules.append({"action": "exclude",
                              "select": select})
            elif 'launcher' in in_stage:
                select = substitute_profile_parameters(in_stage["launcher"], self._param_values)
                if link_type != 'copy':
                    rules.append({"action": "launcher",
                                  "select": "${%s_DIR}/%s" % (ref, select),
                                  "prefix": "${%s_DIR}" % ref,
                                  "target": target})
            elif 'copy' in in_stage:
                select = substitute_profile_parameters(in_stage["copy"], self._param_values)
                rules.append({"action": "copy",
                    "select": "${%s_DIR}/%s" % (ref, select),
                    "prefix": "${%s_DIR}" % ref,
                    "target": target,
                    "dirs": in_stage.get("dirs", False)})
            else:
                raise ValueError('Need either "copy", "link", "launcher" or "exclude" '
                                 'key in profile_links entries')
        return rules

    def assemble_build_import_commands(self, name_in_using):
        """
        Return the ``when_build_dependency`` commands from dependencies.
        """
        cmds = [self._process_when_build_dependency(env_action, name_in_using)
                for env_action in self.doc.get('when_build_dependency', [])]
        return cmds

    def _process_when_build_dependency(self, action, name_in_using):
        action = dict(action)
        if not ('prepend_path' in action or 'append_path' in action or 'set' in action):
            raise ValueError('when_build_dependency action must be one of '
                             'prepend_path, append_path, set')
        value = substitute_profile_parameters(action['value'], self._param_values)
        value = value.replace('${ARTIFACT}', '${%s_DIR}' % to_env_var(name_in_using))
        if '$' in value.replace('${', ''):
            # a bit crude, but works for now -- should properly disallow non-${}-variables,
            # in order to prevent $ARTIFACT from cropping up
            raise ProfileError(action['value'].start_mark, 'Please use "${VAR}", not $VAR')
        action['value'] = value
        return action


def assemble_build_script(doc, ctx):
    """
    Return the build script.

    As a side effect, all referenced files are stored in the build
    context.

    Parameters
    ----------
    doc: document
      Processed to the point of being present in PackageImpl.doc (i.e.
      past PackageLoader processing)
    ctx: PackageBuildContext
      context

    Returns:
    --------

    String. A bash script that should be run to build the package.
    """
    lines = ['set -e', 'export HDIST_IN_BUILD=yes']
    for stage in doc['build_stages']:
        lines += ctx.dispatch_build_stage(stage)
    return '\n'.join(lines) + '\n'


def _postprocess_commands(doc):
    hit_args = []
    for stage in doc.get('post_process', []):
        for arg in stage.get('hit', []):
            hit_args.append('--' + arg)
    if len(hit_args) == 0:
        return []
    return [{'hit': ['build-postprocess'] + hit_args}]


def create_build_spec(name, doc, parameters, imports,
                      dependency_commands,
                      extra_sources=()):
    if 'BASH' not in parameters:
        raise ProfileError(doc, 'BASH must be provided in profile parameters')

    # sources
    sources = list(extra_sources)
    for source_clause in doc.get("sources", []):
        target = source_clause.get("target", ".")
        sources.append({"target": target, "key": source_clause["key"]})

    # build commands
    commands = list(dependency_commands)
    commands.append({"set": "BASH", "nohash_value": parameters['BASH']})
    if 'PATH' in parameters:
        commands.insert(0, {"set": "PATH", "nohash_value": parameters['PATH']})
    commands.append({"cmd": ["$BASH", "_hashdist/build.sh"]})
    commands.extend(_postprocess_commands(doc))

    # assemble
    build_spec = {
        "name": name,
        "build": {
            "import": imports,
            "commands": commands,
            },
        "sources": sources,
        }
    return core.BuildSpec(build_spec)


def preprocess_default_to_parameters(doc):
    def guess_type(value):
        if isinstance(value, marked_yaml.bool_node):
            return 'bool'
        else:
            try:
                int(value)
            except ValueError:
                return 'str'
            else:
                return 'int'

    if 'defaults' not in doc:
        return doc
    doc = marked_yaml.copy_dict_node(doc)
    defaults = doc.pop('defaults')
    if 'parameters' in doc:
        raise PackageError(defaults, 'A spec cannot have both "defaults" and "parameters", please move '
                                     'information from the deprecated defaults section to parameters')
    parameters = doc['parameters'] = marked_yaml.list_node([], defaults.start_mark, defaults.end_mark)
    for key, value in defaults.items():
        parameters.append(marked_yaml.dict_node(
            {'name': key,
             'default': value,
             'type': marked_yaml.unicode_node(guess_type(value), value.start_mark, value.end_mark)},
            start_mark=key.start_mark, end_mark=value.end_mark))
    return doc
