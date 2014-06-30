from time import sleep
from functools import wraps
import logging

# The retry function derives from a version by Jeff Laughlin Consulting
# LLC, which is available from https://gist.github.com/n1ywb/2570004
# under the following license:

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


def _default_retry(tries_remaining, exception, delay):
    msg = "Retrying in %s seconds, %d tries remaining" % \
          (delay, tries_remaining)
    logger = logging.getLogger()
    logger.info(msg)
    logger.info("Press Control-C to give up")

def retry(max_tries=3, delay=1, backoff=2, exceptions=(Exception,),
          hook_retry=_default_retry):
    """Function decorator implementing retrying logic.

    max_tries: Number of attempts to make before giving up
    delay: Factor of seconds to sleep in sleep = (delay * backoff * try number)
    backoff: Number to multiply delay after each failure
    exceptions: Iterable of exception classes; default (Exception,)
    hook_retry: Function with signature hook_retry(tries_remaining, exception);
                If specified, this function is called prior to each retry

    The decorated function will be retried up to max_tries times if it raises
    an exception.

    By default, catch instances of the Exception class and subclasses.
    This will recover after all but the most fatal errors. You may specify a
    custom tuple of exception classes with the 'exceptions' argument; the
    function will only be retried if it raises one of the specified
    exceptions.

    Additionally you may specify hook functions which will be called prior
    to retrying with the number of remaining tries and the exception instance;
    This is primarily intended to give the opportunity to
    log the failure. hook_retry is not called after failure if no
    retries remain.
    """

    def deco_retry(f):

        @wraps(f)
        def f_retry(*args, **kwargs):
            my_delay = delay
            tries = range(max_tries)
            tries.reverse()
            for tries_remaining in tries:
                try:
                   return f(*args, **kwargs)
                except exceptions as e:
                    if tries_remaining > 0:
                        if hook_retry is not None:
                            hook_retry(tries_remaining, e, my_delay)
                        sleep(my_delay)
                        my_delay = my_delay * backoff
                    else:
                        raise
                else:
                    break
            return f(*args, **kwargs)

        return f_retry

    return deco_retry
