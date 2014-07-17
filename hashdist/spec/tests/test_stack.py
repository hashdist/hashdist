import unittest
import os
from os.path import join as pjoin
from .. import profile
from .. import package

from hashdist.util.logger_setup import getLogger
null_logger = getLogger('null_logger')


class BaseStack(unittest.TestCase):

    def load_stack(self, dirpath, profile_name):
        """
        Load stack and store profile and packagespecs in attributes
        """
        profile_file = pjoin(os.path.dirname(__file__), 'test_stack', dirpath, profile_name)
        with profile.TemporarySourceCheckouts(None) as checkouts:
            doc = profile.load_and_inherit_profile(checkouts, profile_file)
            self.profile = profile.Profile(null_logger, doc, checkouts)
            for name in self.profile.packages:
                pkg = package.PackageSpec.load(self.profile, name)
                setattr(self, name, pkg)


class TestUseAlternatePackage(BaseStack):

    def setUp(self):
        self.load_stack('use_alternate_package', 'profile.yaml')

    def test_profile(self):
        self.assertEqual(self.profile.packages['original'],
                         {'use': 'alternate'})
        self.assertEqual(self.profile.packages['base_original'],
                         {'use': 'base_alternate'})

    def assertDsl(self, dsl, **kwds):
        for key, value in kwds.items():
            self.assertEqual(dsl[0][key], value)

    def test_use(self):
        """Test ``original: {use: alternate}`` in the profile"""
        # Due to the use:, the alternate package is actually loaded
        pkg = self.original
        self.assertEqual(pkg.parameters['filename'], 'alternate.yaml')
        # But as far as the specs are concered, it is named 'original'
        self.assertEqual(pkg.name, 'original')
        self.assertDsl(pkg.assemble_link_dsl('target'),
            prefix=u'${ORIGINAL_DIR}',
            select=u'${ORIGINAL_DIR}/*/alternate/*')
        # the hook is the hook of the used alternate package
        self.assertEqual(len(pkg.hook_files), 1)
        assert pkg.hook_files[0].endswith(
            u'tests/test_stack/use_alternate_package/alternate.py'), pkg.hook_files

    def test_base_use(self):
        """Test ``base_original: {use: base_alternate}`` in the profile base"""
        # Due to the use:, the alternate package is actually loaded
        pkg = self.base_original
        self.assertEqual(pkg.parameters['filename'], 'base_alternate.yaml')
        # But as far as the specs are concered, it is named 'original'
        self.assertEqual(pkg.name, 'base_original')
        self.assertDsl(pkg.assemble_link_dsl('target'),
            prefix=u'${BASE_ORIGINAL_DIR}',
            select=u'${BASE_ORIGINAL_DIR}/*/base_alternate/*')
        # the hook is the hook of the used alternate package
        self.assertEqual(len(pkg.hook_files), 1)
        assert pkg.hook_files[0].endswith(
            u'tests/test_stack/use_alternate_package/base_alternate.py'), pkg.hook_files

    def assertFindFile(self, pkgname, filename, expected):
        actual = self.profile.find_package_file(pkgname, filename)
        if expected is None:
            assert actual is None
        else:
            assert actual.endswith(expected)

    def test_directory_use(self):
        """Test ``origdirectory: {use: altdirectory}`` for package-with-directory"""
        # Due to the use:, the altdirectory package is actually loaded
        pkg = self.origdirectory
        self.assertEqual(pkg.parameters['filename'], 'altdirectory.yaml')
        # But as far as the specs are concered, it is named 'origdirectory'
        self.assertEqual(pkg.name, 'origdirectory')
        self.assertDsl(pkg.assemble_link_dsl('target'),
            prefix=u'${ORIGDIRECTORY_DIR}',
            select=u'${ORIGDIRECTORY_DIR}/*/altdirectory/*')
        # the hook is the hook of the used alternate package
        self.assertEqual(len(pkg.hook_files), 1)
        assert pkg.hook_files[0].endswith(
            u'tests/test_stack/use_alternate_package/altdirectory/altdirectory.py'), \
            pkg.hook_files
        # File referenced in the build stage section
        build_stage = pkg.doc['build_stages'][0]
        self.assertEqual(build_stage['handler'], 'refer_to_file')
        self.assertEqual(build_stage['files'], ['alternate_file.txt'])
        self.assertFindFile('origdirectory', 'alternate_file.txt',
                            u'/altdirectory/alternate_file.txt')
        self.assertFindFile('origdirectory', 'original_file.txt', None)
        self.assertFindFile('altdirectory', 'original_file.txt', None)

    def test_directory_base_use(self):
        """Test ``base_origdirectory: {use: base_altdirectory}`` in the profile base"""
        # Due to the use:, the altdirectory package is actually loaded
        pkg = self.base_origdirectory
        self.assertEqual(pkg.parameters['filename'], 'base_altdirectory.yaml')
        # But as far as the specs are concered, it is named 'origdirectory'
        self.assertEqual(pkg.name, 'base_origdirectory')
        self.assertDsl(pkg.assemble_link_dsl('target'),
            prefix=u'${BASE_ORIGDIRECTORY_DIR}',
            select=u'${BASE_ORIGDIRECTORY_DIR}/*/base_altdirectory/*')
        # the hook is the hook of the used alternate package
        self.assertEqual(len(pkg.hook_files), 1)
        assert pkg.hook_files[0].endswith(
            u'tests/test_stack/use_alternate_package/base_altdirectory/base_altdirectory.py'), \
            pkg.hook_files
        # File referenced in the build stage section
        build_stage = pkg.doc['build_stages'][0]
        self.assertEqual(build_stage['handler'], 'refer_to_file')
        self.assertEqual(build_stage['files'], ['base_alternate_file.txt'])
        self.assertFindFile('base_origdirectory', 'base_alternate_file.txt',
                            u'/base_altdirectory/base_alternate_file.txt')
        self.assertFindFile('base_origdirectory', 'base_original_file.txt', None)
        self.assertFindFile('base_altdirectory', 'base_original_file.txt', None)
