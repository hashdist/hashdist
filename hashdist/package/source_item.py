from ..source_cache import single_file_key

class SourceItem(object):
    def __init__(self, key, target):
        self.key = key
        self.target = target
        
    def get_spec(self):
        return {'key': self.key,
                'target': self.target}

    def get_secure_hash(self):
        return 'hashdist.package.source_item.SourceItem', self.key

class DownloadSourceCode(SourceItem):
    def __init__(self, url, key, target='.'):
        SourceItem.__init__(self, key, target)
        self.url = url

    def fetch_into(self, source_cache):
        source_cache.fetch_archive(self.url, self.key)
                        
class PutScript(SourceItem):
    def __init__(self, filename, contents, target='.'):
        key = single_file_key(filename, contents)
        SourceItem.__init__(self, key, target)
        self.filename = filename
        self.contents = contents

    def fetch_into(self, source_cache):
        source_cache.put(self.filename, self.contents)

