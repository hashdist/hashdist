import os
from distutils.core import setup

short_desc="Functional software management for deployment and reproducibility"

try:
    fname='README.rst'
    long_desc = open(os.path.join(os.path.dirname(__file__), fname)).read()
except:
    long_desc=short_desc

setup(
    name = "hashdist",
    version = "0.3",
    author = "HashDist Developers",
    author_email = "hashdist@googlegroups.com",
    description = (short_desc),
    license = "BSD",
    keywords = "package management openscience hpc",
    url = "http://hashdist.github.io/",
    scripts=['bin/hit', 'bin/hit-check-libs'],
    packages=[
          'hashdist',
          'hashdist.cli',
          'hashdist.cli.test',
          'hashdist.core',
          'hashdist.core.test',
          'hashdist.deps',
          'hashdist.deps.distlib',
          'hashdist.deps.jsonschema',
          'hashdist.deps.yaml',
          'hashdist.formats',
          'hashdist.formats.tests',
          'hashdist.host',
          'hashdist.host.test',
          'hashdist.spec',
          'hashdist.spec.tests',
          'hashdist.test',
          'hashdist.util',
          ],
    package_data={
        "hashdist.formats": ["config.example.yaml"],
        "hashdist.deps.jsonschema": ["schemas/*.json"],
        "hashdist.util": ["logging_config.yaml"],
        },
    long_description=short_desc,
    classifiers=[
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Science/Research",
    "Topic :: Utilities",
    "License :: OSI Approved :: BSD License",
    ],
)
