from ..formats.marked_yaml import ValidationError


class ProfileError(ValidationError):
    pass

class IllegalHookFileError(Exception):
    pass
