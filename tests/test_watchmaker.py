# -*- coding: utf-8 -*-
"""Watchmaker main test module."""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals, with_statement)

import os

from watchmaker.cli import LOG_LOCATIONS


def test_log_location_dict():
    """Tests the LOG_LOCATIONS dict."""
    # Test strings that are in the dict.
    location = LOG_LOCATIONS['linux']
    assert location == os.path.sep.join(('', 'var', 'log', 'watchmaker'))
    location = LOG_LOCATIONS['windows']
    assert location == os.path.sep.join((
        os.environ.get('SYSTEMDRIVE', 'C:'), 'Watchmaker', 'Logs'))


def skip_cli_main_entry_point():
    """
    We can skip the test for cli's main.

    Use the comment (# pragma: no cover) so coverage.py will ignore them.
    prepare_logging() is tested in test_logger.py
    exception_hook() is tested in test_logger.py
    Parts of Arguments and Client are tested in this file
    """
    pass
