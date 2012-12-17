import os
import errno

def silent_makedirs(path):
    try:
        os.makedirs(path)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise
            
