"""
Load common settings from a config file and / or command-line arguments.

Example:
    parser = argparse.ArgumentParser()
    config, args = settings.load_args(parser, ['sample_rate', 'chip_rate'])
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import logging
from collections import namedtuple

from thrifty import setting_parsers


# Setting definition
Definition = namedtuple('SettingDefinition', 'args parser default description')

DEFINITIONS = {
    'sample_rate': Definition(
        ['--sample-rate', '-s'],
        setting_parsers.metric_float,
        '2.2e6',
        "Sample rate (sps)"
    ),

    'chip_rate': Definition(
        ['--chip-rate', '-p'],
        setting_parsers.metric_float,
        '1.08e6',
        "Rate at which the code is being transmitted (bps)"
    ),

    'tuner.freq': Definition(
        ['--freq', '-f'],
        setting_parsers.metric_float,
        '433e6',
        "Tuner center frequency (Hz)"
    ),

    'tuner.gain': Definition(
        ['--gain', '-g'],
        float,
        '20',
        "Tuner gain (dB)"
    ),

    'block.size': Definition(
        ['--block-size', '-b'],
        int,
        '8192',
        "Length of fixed-sized blocks, which should be a power of two "
        "(samples)"
    ),

    'block.history': Definition(
        ['--history', '-h'],
        int,
        '2085',
        "The number of samples at the end of a block that should be repeated "
        "at the start of the next block (samples)"
    ),
}

DEFAULT_CONFIG_PATH = 'thrifty.cfg'
CONFIG_COMMENT_CHAR = '#'
CONFIG_DELIMITER = ':'
CONFIG_DEST = 'config'


class Error(Exception):
    """Base class for settings-related exceptions."""
    pass


class ConfigSyntaxError(Error):
    """Error raised when a config file's syntax is invalid."""
    def __init__(self, line_no, msg):
        Error.__init__(self)
        self.line_no = line_no
        self.msg = msg

    def __str__(self):
        return "line #%d: %s" % (self.line_no, self.msg)


class SettingKeyError(Error):
    """Error raised when a setting's definition does not exist."""
    def __init__(self, msg):
        Error.__init__(self)
        self.msg = msg

    def __str__(self):
        return repr(self.msg)


def add_argparse_arguments(parser, keys, definitions=None):
    """Generate argparse arguments for the settings with the given keys."""
    if definitions is None:
        definitions = DEFINITIONS
    for key in keys:
        if key not in definitions:
            raise SettingKeyError("Unknown key: {}".format(key))
        setting = definitions[key]
        if len(setting.args):
            parser.add_argument(*setting.args, dest=key,
                                type=str, default=setting.default,
                                help=setting.description)


def load(args=None, config_file=None, definitions=None):
    """Load settings from config file and/or command-line arguments.

    Returns the default values if neither config_file nor args are specified.

    If config_file is None and args contains the key 'config', the value of
    'config' will be used as the path of the config file. If the value of
    'config' is None, the default config file will be used.

    Parameters
    ----------
    args : dict-like object
        Argument strings that should override config values.
    config_file : file-like object
        Key-value config file to load settings from.
    definitions : dict
        Setting definitions (defaults to DEFINITIONS).

    Returns
    -------
    dict
        Map of setting keys to setting values.

    Raises
    ------
    IOError
        If the input file cannot be read.
    ConfigSyntaxError
        If the syntax of the config file is incorrect.
    SettingKeyError
        If a non-existing setting was specified in the config file or in args.
    ValueError
        If a string could not be converted to a settings value.
    """

    if definitions is None:
        definitions = DEFINITIONS

    # Default values
    strings = {key: setting.default
               for key, setting in definitions.iteritems()
               if setting.default is not None}

    # Load config
    if config_file is not None:
        config_settings = _parse_config(config_file)
        for key in config_settings:
            if key not in definitions:
                raise SettingKeyError("Unknown setting: {}".format(key))
        strings.update(config_settings)

    # Override values from arguments
    if args is not None:
        for key in args:
            if key not in definitions:
                raise SettingKeyError("Unknown setting: {}".format(key))
        strings.update(args)

    # Parse
    values = {k: definitions[k].parser(v) for k, v in strings.iteritems()}

    return values


def load_args(parser, keys, argv=None, definitions=None):
    """Convenience function for loading a subset of settings.

    Generate argparse arguments for the settings with the given keys, parse the
    arguments, load settings from config file specified by '--config' argument
    and parse settings.

    Parameters
    ----------
    parser : argparse.ArgumentParser object
    keys : list of strings
    argv : list of strings
        The command-line args (defaults to sys.argv).
    definitions : dict
        Setting definitions (defaults to DEFINITIONS).

    Returns
    -------
    settings : dict
        Map of the requested setting keys to setting values.
    extra_args : dict
        Any extra arguments that were added to the parser before this function
        got hold of it.
    """
    if definitions is None:
        definitions = DEFINITIONS
    if argv is None:
        argv = None

    parser.add_argument('-c', '--config', dest=CONFIG_DEST,
                        type=str, default=None,
                        help="Config file to load settings from "
                             "(default: {})".format(DEFAULT_CONFIG_PATH))
    add_argparse_arguments(parser, keys, definitions=definitions)
    if argv is None:
        args_namespace = parser.parse_args()
    else:
        args_namespace = parser.parse_args(argv)
    args = vars(args_namespace)

    # Load config file
    config_arg = args[CONFIG_DEST]
    if config_arg is None:
        try:
            config_file = open(DEFAULT_CONFIG_PATH)
            logging.info("Loaded default config file from %s",
                         DEFAULT_CONFIG_PATH)
        except IOError:
            # Do not throw IOError if the config file has not been
            # specified explicitly.
            pass
    else:
        config_file = open(config_arg)
        logging.info("Loaded config file from %s", config_arg)
    args.pop(CONFIG_DEST)

    key_args = {k: v for k, v in args.iteritems()
                if k in keys and v is not None}
    extra_args = {k: v for k, v in args.iteritems() if k not in keys}

    settings = load(key_args, config_file, definitions)
    subset = {k: v for k, v in settings.iteritems() if k in keys}

    return subset, extra_args


def _parse_config(config_file):
    """A simple key:value config file parser."""
    settings = {}
    for line_no, line in enumerate(config_file):
        if CONFIG_COMMENT_CHAR in line:
            line, _ = line.split(CONFIG_COMMENT_CHAR, 1)
        if len(line.strip()) == 0:
            continue
        if CONFIG_DELIMITER not in line:
            raise ConfigSyntaxError(line_no + 1, 'No delimiter found')
        key, value = line.split(CONFIG_DELIMITER, 1)
        settings[key.strip()] = value.strip()
    return settings