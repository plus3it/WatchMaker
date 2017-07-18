# -*- coding: utf-8 -*-
"""Watchmaker module."""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals, with_statement)

import codecs
import collections
import datetime
import logging
import os
import platform
import subprocess

import pkg_resources
import setuptools
import yaml
from six.moves import urllib

from watchmaker import static
from watchmaker.exceptions import WatchmakerException
from watchmaker.managers.workers import (LinuxWorkersManager,
                                         WindowsWorkersManager)


def _extract_version(package_name):
    try:
        return pkg_resources.get_distribution(package_name).version
    except pkg_resources.DistributionNotFound:
        _conf = setuptools.config.read_configuration(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'setup.cfg'
            )
        )
        return _conf['metadata']['version']


__version__ = _extract_version('watchmaker')


class Arguments(dict):
    """
    Create an arguments object for the :class:`watchmaker.Client`.

    Args:
        config_path: (:obj:`str`)
            Path or URL to the Watchmaker configuration
            file. If ``None``, the default config.yaml file is used.
            (*Default*: ``None``)

        log_dir: (:obj:`str`)
            Path to a directory. If set, Watchmaker logs to a file named
            ``watchmaker.log`` in the specified directory. Both the directory
            and the file will be created if necessary. If the file already
            exists, Watchmaker appends to it rather than overwriting it. If
            this argument evaluates to ``False``, then logging to a file is
            disabled. Watchmaker will always output to stdout/stderr.
            Additionaly, Watchmaker workers may use this directory to keep
            other log files.
            (*Default*: ``None``)

        no_reboot: (:obj:`bool`)
            Switch to control whether to reboot the system upon a successful
            execution of :func:`watchmaker.Client.install`. When this parameter
            is set, Watchmaker will suppress the reboot. Watchmaker
            automatically suppresses the reboot if it encounters an error.
            (*Default*: ``False``)

        log_level: (:obj:`str`)
            Level to log at. Case-insensitive. Valid options include,
            from least to most verbose:

            - ``critical``
            - ``error``
            - ``warning``
            - ``info``
            - ``debug``

    .. important::

        For all **Keyword Arguments**, below, the default value of ``None``
        means Watchmaker will get the value from the configuration file. Be
        aware that ``None`` and ``'None'`` are two different values, with
        different meanings and effects.

    Keyword Arguments:
        admin_groups: (:obj:`str`)
            Set a salt grain that specifies the domain
            _groups_ that should have root privileges on Linux or admin
            privileges on Windows. Value must be a colon-separated string. On
            Linux, use the ``^`` to denote spaces in the group name.
            (*Default*: ``None``)

            .. code-block:: python

                admin_groups = "group1:group2"

                # (Linux only) The group names must be lowercased. Also, if
                # there are spaces in a group name, replace the spaces with a
                # '^'.
                admin_groups = "space^out"

                # (Windows only) No special capitalization nor syntax
                # requirements.
                admin_groups = "Space Out"

        admin_users: (:obj:`str`)
            Set a salt grain that specifies the domain
            _users_ that should have root privileges on Linux or admin
            privileges on Windows. Value must be a colon-separated string.
            (*Default*: ``None``)

            .. code-block:: python

                admin_users = "user1:user2"

        computer_name: (:obj:`str`)
            Set a salt grain that specifies the computername to apply to the
            system.
            (*Default*: ``None``)

        environment: (:obj:`str`)
            Set a salt grain that specifies the environment in which the system
            is being built. For example: ``dev``, ``test``, or ``prod``.
            (*Default*: ``None``)

        salt_states: (:obj:`str`)
            Comma-separated string of salt states to apply. A value of
            ``'None'`` (the string) will not apply any salt states. A value
            of ``'Highstate'`` will apply the salt highstate.
            (*Default*: ``None``)

        s3_source: (:obj:`bool`)
            Use S3 utilities to retrieve content instead of http/s utilities.
            For S3 utilities to work, ``boto3`` must be installed, and the
            system must have boto credentials configured that allow access to
            the S3 bucket.
            (*Default*: ``None``)

        ou_path: (:obj:`str`)
            Set a salt grain that specifies the full DN of the OU where the
            computer account will be created when joining a domain.
            (*Default*: ``None``)

            .. code-block:: python

                ou_path="OU=Super Cool App,DC=example,DC=com"

        extra_arguments: (:obj:`list`)
            A list of extra arguments to be merged into the worker
            configurations. The list must be formed as pairs of named arguments
            and values. Any leading hypens in the argument name are stripped.
            (*Default*: ``[]``)

            .. code-block:: python

                extra_arguments=['--arg1', 'value1', '--arg2', 'value2']

                # This list would be converted to the following dict and merged
                # into the parameters passed to the worker configurations:
                {'arg1': 'value1', 'arg2': 'value2'}
    """

    def __init__(
        self,
        config_path=None,
        log_dir=None,
        no_reboot=False,
        log_level=None,
        *args,
        **kwargs
    ):
        super(Arguments, self).__init__(*args, **kwargs)
        self.config_path = config_path
        self.log_dir = log_dir
        self.no_reboot = no_reboot
        self.log_level = log_level
        self.admin_groups = kwargs.pop('admin_groups', None)
        self.admin_users = kwargs.pop('admin_users', None)
        self.computer_name = kwargs.pop('computer_name', None)
        self.environment = kwargs.pop('environment', None)
        self.salt_states = kwargs.pop('salt_states', None)
        self.s3_source = kwargs.pop('s3_source', None)
        self.ou_path = kwargs.pop('ou_path', None)
        self.extra_arguments = kwargs.pop('extra_arguments', None) or []

    def __getattr__(self, attr):
        """Support attr-notation for getting dict contents."""
        return super(Arguments, self).__getitem__(attr)

    def __setattr__(self, attr, value):
        """Support attr-notation for setting dict contents."""
        super(Arguments, self).__setitem__(attr, value)


class Client(object):
    """
    Prepare a system for setup and installation.

    Keyword Arguments:
        arguments: (:obj:`Arguments`)
            A dictionary of arguments. See :class:`watchmaker.Arguments`.
    """

    def __init__(self, arguments):
        self.log = logging.getLogger(
            '{0}.{1}'.format(__name__, self.__class__.__name__)
        )
        # Pop extra_arguments now so we can log it separately
        extra_arguments = arguments.pop('extra_arguments', [])

        header = ' WATCHMAKER RUN '
        header = header.rjust((40 + len(header) // 2), '#').ljust(80, '#')
        self.log.info(header)
        self.log.debug('Watchmaker Version: %s', __version__)
        self.log.debug('Parameters: %s', arguments)
        self.log.debug('Extra Parameters: %s', extra_arguments)

        # Pop remaining arguments used by watchmaker.Client itself
        self.default_config = os.path.join(static.__path__[0], 'config.yaml')
        self.no_reboot = arguments.pop('no_reboot', False)
        self.config_path = arguments.pop('config_path')
        self.log_dir = arguments.pop('log_dir')
        self.log_level = arguments.pop('log_level')

        # Get the system params
        self.system = platform.system().lower()
        self._set_system_params()

        self.log.debug('System Type: %s', self.system)
        self.log.debug('System Parameters: %s', self.system_params)

        # All remaining arguments are worker_args
        worker_args = arguments

        # Convert extra_arguments to a dict and merge it with worker_args.
        # Leading hypens are removed, and other hyphens are converted to
        # underscores
        worker_args.update(dict(
            (k.lstrip('-').replace('-', '_'), v) for k, v in zip(
                *[iter(extra_arguments)] * 2)
        ))
        # Set self.worker_args, removing `None` values from worker_args
        self.worker_args = dict(
            (k, v) for k, v in worker_args.items() if v is not None
        )

        self.config = self._get_config()

    @staticmethod
    def _validate_url(url):
        return urllib.parse.urlparse(url).scheme in ['http', 'https']

    def get_config_data(self, is_url, path):
        """Read in config yaml from file or url."""
        if is_url:
            try:
                data = urllib.request.urlopen(path).read()
            except urllib.error.URLError:
                msg = (
                    'The URL used to get the user config.yaml file did not '
                    'work! Please make sure your config is available.'
                )
                self.log.critical(msg)
                raise
        else:
            with codecs.open(path, encoding="utf-8") as fh_:
                data = fh_.read()
        return data

    def _get_config(self):
        """
        Read and validate configuration data for installation.

        Returns:
            :obj:`collections.OrderedDict`: Returns the data from the the YAML
            configuration file, scoped to the value of ``self.system`` and
            merged with the value of the ``"All"`` key.

        """
        if not self.config_path:
            self.log.warning(
                'User did not supply a config. Using the default config.'
            )
            self.config_path = self.default_config
        else:
            self.log.info('User supplied config being used.')

        # Get the raw config data
        data = ''
        if self._validate_url(self.config_path):
            data = self.get_config_data(True, self.config_path)
        elif self.config_path and not os.path.exists(self.config_path):
            msg = (
                'User supplied config {0} does not exist. Please '
                'double-check your config path or use the default config '
                'path.'.format(self.config_path)
            )
            self.log.critical(msg)
            raise WatchmakerException(msg)
        else:
            data = self.get_config_data(False, self.config_path)

        config_full = yaml.safe_load(data)
        try:
            config_all = config_full.get('all', [])
            config_system = config_full.get(self.system, [])
        except AttributeError:
            msg = 'Malformed config file. Must be a dictionary.'
            self.log.critical(msg)
            raise

        # If both config and config_system are empty, raise
        if not config_system and not config_all:
            msg = 'Malformed config file. No workers for this system.'
            self.log.critical(msg)
            raise WatchmakerException(msg)

        # Merge the config data, preserving the listed order of workers
        config = collections.OrderedDict()
        for worker in config_system + config_all:
            try:
                # worker is a single-key dict, where the key is the name of the
                # worker and the value is the worker parameters. we need to
                # test if the worker is already in the config, but a dict is
                # is not hashable so cannot be tested directly with
                # `if worker not in config`. this bit of ugliness extracts the
                # key and its value so we can use them directly.
                worker_name, worker_config = list(worker.items())[0]
                if worker_name not in config:
                    # Add worker to config
                    config[worker_name] = {'config': worker_config}
                    self.log.debug('%s config: %s', worker_name, worker_config)
                else:
                    # Worker present in both config_system and config_all
                    config[worker_name]['config'].update(worker_config)
                    self.log.debug(
                        '%s extra config: %s',
                        worker_name, worker_config
                    )
                    # Need to (re)merge cli worker args so they override
                    config[worker_name]['__merged'] = False
                if not config[worker_name].get('__merged'):
                    # Merge worker_args into config params
                    config[worker_name]['config'].update(self.worker_args)
                    config[worker_name]['__merged'] = True
            except Exception:
                msg = (
                    'Failed to merge worker config; worker={0}'
                    .format(worker)
                )
                self.log.critical(msg)
                raise

        self.log.debug(
            'Command-line arguments merged into worker configs: %s',
            self.worker_args
        )

        return config

    def _get_linux_system_params(self):
        """Set ``self.system_params`` attribute for Linux systems."""
        params = {}
        params['prepdir'] = os.path.join(
            '{0}'.format(self.system_drive), 'usr', 'tmp', 'watchmaker')
        params['readyfile'] = os.path.join(
            '{0}'.format(self.system_drive), 'var', 'run', 'system-is-ready')
        params['logdir'] = os.path.join(
            '{0}'.format(self.system_drive), 'var', 'log')
        params['workingdir'] = os.path.join(
            '{0}'.format(params['prepdir']), 'workingfiles')
        params['restart'] = 'shutdown -r +1 &'
        return params

    def _get_windows_system_params(self):
        """Set ``self.system_params`` attribute for Windows systems."""
        params = {}
        # os.path.join does not produce path as expected when first string
        # ends in colon; so using a join on the sep character.
        params['prepdir'] = os.path.sep.join([self.system_drive, 'Watchmaker'])
        params['readyfile'] = os.path.join(
            '{0}'.format(params['prepdir']), 'system-is-ready')
        params['logdir'] = os.path.join(
            '{0}'.format(params['prepdir']), 'Logs')
        params['workingdir'] = os.path.join(
            '{0}'.format(params['prepdir']), 'WorkingFiles')
        params['shutdown_path'] = os.path.join(
            '{0}'.format(os.environ['SYSTEMROOT']), 'system32', 'shutdown.exe')
        params['restart'] = params["shutdown_path"] + \
            ' /r /t 30 /d p:2:4 /c ' + \
            '"Watchmaker complete. Rebooting computer."'
        return params

    def _set_system_params(self):
        """Set OS-specific attributes."""
        if 'linux' in self.system:
            self.system_drive = '/'
            self.workers_manager = LinuxWorkersManager
            self.system_params = self._get_linux_system_params()
        elif 'windows' in self.system:
            self.system_drive = os.environ['SYSTEMDRIVE']
            self.workers_manager = WindowsWorkersManager
            self.system_params = self._get_windows_system_params()
        else:
            msg = 'System, {0}, is not recognized?'.format(self.system)
            self.log.critical(msg)
            raise WatchmakerException(msg)
        if self.log_dir:
            self.system_params['logdir'] = self.log_dir

    def install(self):
        """
        Execute the watchmaker workers against the system.

        Upon successful execution, the system will be properly provisioned,
        according to the defined configuration and workers.
        """
        self.log.info('Start time: %s', datetime.datetime.now())
        self.log.info('Workers to execute: %s', self.config.keys())

        # Create watchmaker directories
        try:
            os.makedirs(self.system_params['workingdir'])
        except OSError:
            if not os.path.exists(self.system_params['workingdir']):
                msg = (
                    'Unable to create directory - {0}'
                    .format(self.system_params['workingdir'])
                )
                self.log.critical(msg)
                raise

        workers_manager = self.workers_manager(
            system_params=self.system_params,
            workers=self.config
        )

        try:
            workers_manager.worker_cadence()
        except Exception:
            msg = 'Execution of the workers cadence has failed.'
            self.log.critical(msg)
            raise

        if self.no_reboot:
            self.log.info(
                'Detected `no-reboot` switch. System will not be '
                'rebooted.'
            )
        else:
            self.log.info(
                'Reboot scheduled. System will reboot after the script '
                'exits.'
            )
            subprocess.call(self.system_params['restart'], shell=True)
        self.log.info('Stop time: %s', datetime.datetime.now())
