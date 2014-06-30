"""
Log Capture for Unit Tests
==========================

The :class:`log_capture` context manager servers as test fixture. The

EXAMPLES::

    >>> from hashdist.util.logger_fixtures import log_capture
    >>> with log_capture() as log:
    ...    log.warning('this is a warning')
    ...    log.error('something went wrong')
    >>> log.lines
    ('WARNING:this is a warning', 'ERROR:something went wrong')
    >>> log.messages
    ('this is a warning', 'something went wrong')

For unit test, you can use the assert methods to ensure that a log
record of given level and matching the regex was encountered.

    >>> log.assertLogged('^WARNING.*s is a w.*')
    >>> log.assertLogged('^ERROR.*something.*')
    >>> log.assertLogged('^ERROR.*s is a w.*')
    Traceback (most recent call last):
    ...
    AssertionError: no such log message
"""

import re
import logging
import logging.handlers


class TestHandler(logging.handlers.BufferingHandler):
    """
    Log handler that buffers indefinitely.
    """

    def __init__(self):
        logging.handlers.BufferingHandler.__init__(self, 0)

    def shouldFlush(self, *args):
        return False


class TestLoggerAdapter(logging.LoggerAdapter):
    """
    Adapter to enrich the test logger with unit test functionality.
    """

    def __init__(self, logger, test_handler):
        """
        Python constructor.

        You should never have to instantiate this class yourself, use
        the :class:`log_capture` context instead.

        Arguments:
        ----------

        logger : logging.Logger
            The underlying logger.

        test_handler: :class:`TestHandler`
            Handler for log messages
        """
        self._logger = logger
        self._handler = test_handler
        logging.LoggerAdapter.__init__(self, logger, {})

    def addFilter(self, filter):
        self._logger.addFilter(filter)

    def removeFilter(self, filter):
        self._logger.removeFilter(filter)

    def _format_buffered_log(self):
        fmt = self._handler.formatter
        return tuple(fmt.format(record) for record in self._handler.buffer)

    def _buffered_messages(self):
        return tuple(record.message for record in self._handler.buffer)

    def _save(self):
        self._lines = self._format_buffered_log()
        self._messages = self._buffered_messages()

    @property
    def lines(self):
        """
        Return the stored log lines

        Returns:
        --------

        A tuple of strings.  Within the scope of the context, this
        returns the log thus far. After the scope of the context, the
        entire log is returned.
        """
        try:
            return self._lines
        except AttributeError:
            return self._format_buffered_log()

    @property
    def messages(self):
        """
        Return the stored messages

        Returns:
        --------

        A tuple of strings. Within the scope of the context, this
        returns the log messages (without any decoration) thus
        far. After the scope of the context, all messages are
        returned.
        """
        try:
            return self._messages
        except AttributeError:
            return self._buffered_messages()


    def assertLogged(self, search_pattern):
        """
        Ensure that the gives pattern is in at least one log line.

        Arguments:
        ----------

        search_pattern : str
            The regex pattern to search.

        Returns:
        --------

        Nothing.

        Raises:
        -------

        ``AssertionError`` if the pattern is not found.
        """
        assert any(re.search(search_pattern, line) for line in self.lines), \
            'no such log message'


class log_capture(object):
    """
    Context manager to log to a memory buffer
    """

    def __init__(self, name=None):
        """
        Python constructor

        Arguments:
        ----------

        name : str
            The name of the logger.

        filename : str
            Filename to log to.
        """
        self.logger = logging.getLogger(name)
        self.handler = h = TestHandler()
        h.setLevel(logging.DEBUG)
        fmt = logging.Formatter('%(levelname)s:%(message)s')
        h.setFormatter(fmt)

    def __enter__(self):
        self.orig_handlers = self.logger.handlers
        self.logger.handlers = [self.handler]
        self.level = self.logger.level
        self.test = TestLoggerAdapter(self.logger, self.handler)
        return self.test

    def __exit__(self, exc_type, exc_value, traceback):
        self.test._save()
        self.logger.handlers = self.orig_handlers
        self.logger.level = self.level
