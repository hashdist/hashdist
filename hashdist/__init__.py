from .spec.hook_api import *

import os
hashdist_dir = os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))
hashdist_share_dir = os.path.join(hashdist_dir, "share", "hashdist")
