"""
A simple stream constructor that constructs a Stream by evaluating
parameter substitutions from a dictionary parameters. Finds tokens of the form

\{\{([a-zA-Z_-][\w-]*)\}\}

and replaces {{var}} with the contents of gettattr(parameters, var) in
the new stream.
"""

import re
from StringIO import StringIO

class TemplatedStream(StringIO):
    """
    StringIO stream that expands template parameters of the form {{var}}
    """

    dbrace_re = re.compile(r'\{\{([a-zA-Z_][\w-]*)\}\}')
    
    def __init__(self, stream, parameters):
        """
        Create a TemplatedStream by populating variables from the
        parameters mapping.  Silently passes matching strings that
        do not have a corresponding key defined in parameters as empty strings.
        """

        StringIO.__init__(self)

        def dbrace_expand(match):
            if match.group(1) in parameters:
                # we may occassionally be handed non-string object in
                # parameters.  Just convert them to string, they will
                # be re-run through the YAML parser anyway.
                return str(parameters[match.group(1)])
            else:
                return ''
        
        for line in stream:
            self.write(self.dbrace_re.sub(dbrace_expand, line))

        self.seek(0)
        
