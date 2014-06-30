"""
Utilities to setup the Python logger

EXAMPLES:

We first back up the doctesting configuration::

    >>> import logging
    >>> from hashdist.util.logger_setup import *
    >>> backup_config = LogConfigurationStore()

The root logger is used by default::

    >>> configure_logging('INFO')
    [INFO] configured logging: INFO
    >>> root = logging.getLogger()
    >>> root.name
    'root'
    >>> root.warning('this is a warning')
    [WARNING] this is a warning

The "build" logger is used to log the builder output. It does not add
any information to stdout::

    >>> build = logging.getLogger('build')
    >>> build.name
    'build'
    >>> build.warning('this is a warning')
    this is a warning

The "package" logger is used to log progress on packages. It is
supposed to be used with an additional ``pkg`` key which you have to
either pass manually or using an adapter::

    >>> pkg = logging.getLogger('package')
    >>> pkg.name
    'package'
    >>> pkg.warning('this is a warning', extra={'pkg':'foo'})
    [foo] this is a warning
    >>> log_foo = logging.LoggerAdapter(pkg, {'pkg':'foo'})
    >>> log_foo.warning('this is a warning')
    [foo] this is a warning

The null logger is only used in doctests and doesn't print anything::

    >>> null = logging.getLogger('null_logger')
    >>> null.error('this is an error')

Configuring a higher log level suppresses output as well, except for
the package logger which is part of the UI::

    >>> configure_logging('CRITICAL')
    >>> root.error('this is a general error')
    >>> build.error('this is a build error')
    >>> log_foo.error('this is a foo error')
    [foo] this is a foo error

For doctesting only, revert back to the nose logging handlers::

    >>> backup_config.restore()
"""

import logging
import os
from ansi_color import want_color, color, monochrome


class LogConfigurationStore(object):
    """
    Store the root logger configuration for doctesting purposes
    """

    def __init__(self):
        self._logger = logging.getLogger()
        self._orig_handlers = self._logger.handlers
        self._logger.handlers = []
        self._level = self._logger.level

    def restore(self):
        self._logger.handlers = self._orig_handlers
        self._logger.level = self._level



_ERROR_OCCURRED = False

def has_error_occurred():
    """
    Return whether an error occurred previously.
    """
    return _ERROR_OCCURRED


def set_log_level(level):
    """
    Set which log messages are displayed.

    This function adjusts various log levels to exclude messages with
    a lower priority than ``level``.

    Arguments:
    ----------

    level : string or int
        The desired log level as defined by the Python logging module
    """
    level_string_to_value = dict(
        CRITICAL=logging.CRITICAL, ERROR=logging.ERROR, WARNING=logging.WARNING, 
        INFO=logging.INFO, DEBUG=logging.DEBUG)
    try:
        level = level_string_to_value[level.upper()]
    except KeyError:
        raise ValueError('level must be integer or a valid log level string')
    except AttributeError:
        pass
    root = logging.getLogger()
    root.setLevel(level=level)
    build = logging.getLogger('build')
    build_handler = [h for h in build.handlers if h.name == 'build_handler'][0]
    build_handler.setLevel(level)


def configure_logging(config):
    """
    Configure the root logger

    While this function can, in principle, be called multiple times
    you are supposed to use it only once to set up logging at the
    beginning of your program.

    Arguments:
    ----------

    config : string or ``None``.
       One of
       * the Python log level constants ``'CRITICAL'``,
         ``'ERROR'``, ``'WARNING'``, ``'INFO'``, ``'DEBUG'``.
       * the name of a logging configuration YAML file. See
         ``logging_config.yaml`` for which loggers are required.
       * ``None``. In this case, a suitable default is set up.
    """
    default = os.path.join(os.path.dirname(__file__), 'logging_config.yaml')
    if config is None:
        _configure_logging_from_yaml(default)
    elif config.upper() in ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']:
        _configure_logging_from_yaml(default)
        set_log_level(config)
    else:
        _configure_logging_from_yaml(config)
    root = logging.getLogger()
    root.info('configured logging: %s', config)


def _configure_logging_from_yaml(filename):
    """
    Load logger configuration from YAML

    Arguments:
    ----------

    filename : str
        The name of the YAML file
    """
    from hashdist.deps import yaml
    with open(filename, 'r') as f:
        config_dict = yaml.load(f)
    if not want_color():
        fmt = config_dict['formatters']
        for key, value in fmt.items():
            fmt[key]['format'] = monochrome(value['format'])
    from hashdist.deps.py26_dictconfig import dictConfig
    #try:
    #    from logging.config import dictConfig
    #except ImportError:
    #    # Python 2.6
    #    from hashdist.deps.py26_dictconfig import dictConfig
    try:
        dictConfig(config_dict)
    except Exception as err:
        # The CLI will intercept the exception and try to log it, but
        # if there is no logger there will be no output
        print('Configuring the logger encountered an exception: ' + str(err))
        raise err


class log_to_file(object):
    """
    Context manager to log to file

    This can be used to add file output temporarily to any logger. Any
    log events of level ``DEBUG`` and higher are logged to the file.
    """
    def __init__(self, name, filename):
        """
        Python constructor

        Arguments:
        ----------

        name : str
            The name of the logger.

        filename : str
            Filename to log to.
        """
        self.filename = filename
        self.logger = logging.getLogger(name)
        self.handler = h = logging.FileHandler(filename)
        h.setFormatter(self.get_formatter())

    def get_formatter(self):
        return logging.Formatter(
            fmt='%(asctime)s - %(levelname)s: [%(name)s:%(module)s] %(message)s',
            datefmt='%Y/%m/%d %H:%M:%S')

    def __enter__(self):
        self.logger.addHandler(self.handler)

    def __exit__(self, exc_type, exc_value, traceback):
        self.handler.flush()
        self.handler.close()
        self.logger.removeHandler(self.handler)



class suppress_log_info(object):
    """
    Context manager to suppress INFO log lines

    This context manager suppresses logging of INFO lines unless the
    actual level is DEBUG, in which case nothing is suppressed.

    EXAMPLES::

        >>> from hashdist.util.logger_setup import *
        >>> backup_config = LogConfigurationStore()
        >>> configure_logging('INFO')
        [INFO] configured logging: INFO

        >>> import logging
        >>> logging.info('first')
        [INFO] first

        >>> with suppress_log_info():
        ...     logging.info('second')

        >>> configure_logging('DEBUG')
        [INFO] configured logging: DEBUG
        >>> with suppress_log_info():
        ...     logging.info('second')
        [INFO] second

        >>> backup_config.restore()
    """

    def __init__(self, name=None):
        """
        Python constructor

        Arguments:
        ----------

        name : str or ``None``
            The name of the logger. If not specified, the root logger.
        """
        self.name = name
        self.logger = logging.getLogger(name)

    def __enter__(self):
        self.level = self.logger.level
        if self.level > logging.DEBUG:
            self.logger.setLevel(logging.WARNING)

    def __exit__(self, exc_type, exc_value, traceback):
        self.logger.setLevel(self.level)



class sublevel_added(object):
    """
    Context manager to temporarily extend the log level

    So instead of ``INFO``, the level name can be printed as
    ``INFO:sublevel``.

    .. todo::

        This is currently only used in the "hit logpipe" subcommand
        that seems to be nowhere used. We might want to remove both.

    EXAMPLES::

        >>> from hashdist.util.logger_setup import *
        >>> backup_config = LogConfigurationStore()
        >>> configure_logging('INFO')
        [INFO] configured logging: INFO

        >>> import logging
        >>> logger = logging.getLogger()
        >>> logger.info('first')
        [INFO] first

        >>> with sublevel_added(logger, 'foo'):
        ...     logger.info('second')
        [INFO:foo] second

        >>> logger.info('third')
        [INFO] third

        >>> backup_config.restore()
    """

    class SubLevelFilter(logging.Filter):
        """
        Log filter to add a sublevel to the log level
        """

        def __init__(self, sublevel):
            self.sublevel = sublevel

        def filter(self, record):
            record.levelname = record.levelname + ':' + self.sublevel
            return True

    def __init__(self, logger, sublevel):
        """
        Python constructor

        Arguments:
        ----------

        logger : logging.Logger
            The logger to affect

        sublevel : string or ``None``
            The sublevel name. If ``None``, nothing is changed.
        """
        self.logger = logger
        self.filter = sublevel_added.SubLevelFilter(sublevel) \
                      if sublevel is not None else None

    def __enter__(self):
        if self.filter:
            self.logger.addFilter(self.filter)

    def __exit__(self, exc_type, exc_value, traceback):
        if self.filter:
            self.logger.removeFilter(self.filter)
