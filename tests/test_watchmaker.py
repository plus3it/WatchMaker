# -*- coding: utf-8 -*-
"""Watchmaker main test module."""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals, with_statement)

import io
import os

import pytest
from six.moves import urllib

from watchmaker import Arguments, Client
from watchmaker.cli import LOG_LOCATIONS


def test_log_location_dict():
    """Tests the LOG_LOCATIONS dict."""
    # Test strings that are in the dict.
    location = LOG_LOCATIONS['linux']
    assert location == os.path.sep.join(('', 'var', 'log', 'watchmaker'))
    location = LOG_LOCATIONS['windows']
    assert location == os.path.sep.join((
        os.environ.get('SYSTEMDRIVE', 'C:'), 'Watchmaker', 'Logs'))


def test_default_argument_settings():
    """Tests the initial Arguments class default settings are correct."""
    args = Arguments()
    assert args.config_path is None
    assert args.log_dir is None
    assert not args.no_reboot
    assert args.log_level is None
    assert args.admin_groups is None
    assert args.admin_users is None
    assert args.computer_name is None
    assert args.environment is None
    assert args.salt_states is None
    assert args.s3_source is None
    assert args.ou_path is None
    assert args.extra_arguments == []


def test_argument_settings():
    """Tests the Arguments class with passed-in settings."""
    args = Arguments(config_path='here', log_dir='there',
                     no_reboot=True, log_level='info',
                     computer_name='test_computer', s3_source='aws',
                     arg1='forget', arg2='me', arg3='you',
                     extra_arguments=['arg1', 'forget', 'arg2', 'm3'])
    assert args.config_path == 'here'
    assert args.log_dir == 'there'
    assert args.no_reboot
    assert args.log_level == 'info'
    assert args.admin_groups is None
    assert args.admin_users is None
    assert args.computer_name == 'test_computer'
    assert args.environment is None
    assert args.salt_states is None
    assert args.s3_source == 'aws'
    assert args.ou_path is None
    assert args.extra_arguments == ['arg1', 'forget', 'arg2', 'm3']
    assert args.arg1 == 'forget'
    assert args.arg2 == 'me'
    assert args.arg3 == 'you'


def test_validating_urls():
    """Tests validating urls."""
    assert Client._validate_url('http://www.google.com') is True
    assert Client._validate_url('where.do.we.go') is False
    assert Client._validate_url('https://home.on.range') is True


class TestErrors:
    """Group of tests for catching errors."""

    def test_get_config_data_via_url_throws_error(self):
        """Tests error is raised if bad url is passed."""
        cli = Client(Arguments())
        with pytest.raises(urllib.error.URLError):
            cli.get_config_data(True, 'http://www.nothere.bad')


class MockTests:
    """Grou of tests utilizing some mock features."""

    def test_get_config_data_via_url(self, mocker):
        """Tests obtaining config yaml from url."""
        cli = Client(Arguments())
        mock_urlopen = mocker.patch('urllib.request.urlopen')
        mock_urlopen.return_value = io.StringIO('test')
        assert cli.get_config_data(True, 'http://www.nothere.bad') == 'test'

    def test_get_config_data_via_file(self, mocker):
        """Tests obtaining config yaml from file."""
        cli = Client(Arguments())
        mock_fh = mocker.patch('codecs.open')
        mock_fh.return_value = io.StringIO('test')
        assert cli.get_config_data(False, 'path_to_file') == 'test'


def test_initializing_client_with_defaults(caplog):
    """Tests initialization of Client with default arguments."""
    cli = Client(Arguments())
    assert cli.worker_args is not None
    assert (
        'User did not supply a config. Using the default config.'
        in caplog.text
    )
    assert 'User supplied config being used.' not in caplog.text
    assert cli.config_path == cli.default_config


def test_initializing_client_with_args(caplog, mocker):
    """Tests initialization og Client with passed in arguments."""
    default_cli = Client(Arguments())
    args = Arguments(config_path='here', log_dir='there',
                     no_reboot=True, log_level='info',
                     computer_name='test_computer', s3_source='aws',
                     arg1='forget', arg2='me', arg3='you',
                     extra_arguments=['arg1', 'forget', 'arg2', 'm3'])
    mocker.patch('os.path.exists')
    mocker.patch.object(
        Client,
        'get_config_data',
        return_value=default_cli.get_config_data(
            False,
            default_cli.default_config
        )
    )
    cli = Client(args)
    assert cli.worker_args is not None
    assert 'User supplied config being used.' in caplog.text
    assert cli.config_path == 'here'


def skip_cli_main_entry_point():
    """
    We can skip the test for cli's main.

    Use the comment (# pragma: no cover) so coverage.py will ignore them.
    prepare_logging() is tested in test_logger.py
    exception_hook() is tested in test_logger.py
    Parts of Arguments and Client are tested in this file
    """
    pass
