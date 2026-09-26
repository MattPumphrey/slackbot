# -*- coding: utf-8 -*-

import os
import logging
import tempfile
import requests
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def download_file(url, fpath, token=''):
    logger.debug('starting to fetch %s', url)
    headers = {"Authorization": "Bearer "+token} if token else None
    r = requests.get(url, stream=True, headers=headers)
    with open(fpath, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024*64):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
                f.flush()
    logger.debug('fetch %s', fpath)
    return fpath


def to_utf8(s):
    """Normalize a string or iterable of strings. On Python 3, str is
    already utf-8 capable, so this just recurses into iterables.

    >>> to_utf8('a')
    'a'
    >>> to_utf8(['a', 'b', '\u4f60'])
    ['a', 'b', '\u4f60']
    """
    if isinstance(s, (list, tuple, set)):
        return [to_utf8(v) for v in s]
    return s


@contextmanager
def create_tmp_file(content=''):
    fd, name = tempfile.mkstemp()
    try:
        if content:
            os.write(fd, content)
        yield name
    finally:
        os.close(fd)
        os.remove(name)


