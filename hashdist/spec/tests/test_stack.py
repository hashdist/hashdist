import unittest
import os
from os.path import join as pjoin
from .. import profile
from .. import package
from hashdist.hdist_logging import null_logger


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

    def test_use(self):
        """Test ``original: {use: alternate}`` in the profile"""
        # Due to the use:, the alternate package is actually loaded
        self.assertEqual(self.original.parameters['filename'], 'alternate.yaml')
        # But as far as the specs are concered, it is named 'original'
        self.assertEqual(self.original.name, 'original')
        dsl = self.original.assemble_link_dsl('target')
        self.assertEqual(dsl[0]['prefix'], u'${ORIGINAL_DIR}')
        self.assertEqual(dsl[0]['select'], u'${ORIGINAL_DIR}/*/alternate/*')

    def test_base_use(self):
        """Test ``original: {use: alternate}`` in the profile base"""
        # Due to the use:, the alternate package is actually loaded
        self.assertEqual(self.base_original.parameters['filename'], 'base_alternate.yaml')
        # But as far as the specs are concered, it is named 'original'
        self.assertEqual(self.base_original.name, 'base_original')
        dsl = self.base_original.assemble_link_dsl('target')
        self.assertEqual(dsl[0]['prefix'], u'${BASE_ORIGINAL_DIR}')
        self.assertEqual(dsl[0]['select'], u'${BASE_ORIGINAL_DIR}/*/base_alternate/*')
