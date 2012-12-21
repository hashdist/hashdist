
class InvalidBuildSpecError(ValueError):
    pass


json_formatting_options = dict(indent=2, separators=(', ', ' : '),
                               sort_keys=True, allow_nan=False)
