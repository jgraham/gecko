#!/usr/bin/env python
# ***** BEGIN LICENSE BLOCK *****
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
# ***** END LICENSE BLOCK *****

import argparse
import os
import re
from collections import defaultdict

try_config_options = [
    [["--try-message"],
     {"action": "store",
     "dest": "try_message",
     "default": None,
     "help": "try syntax string to select tests to run",
      }],
]

class TryToolsMixin(object):
    """Utility functions for an interface between try syntax and out test harnesses.
    Requires log and script mixins."""

    harness_extra_args = None
    try_test_paths = []

    def parse_extra_try_arguments(self, msg, known_try_arguments):
        """Given a commit message, parse to extract additional arguments to pass
        on to the test harness command line.

        Extracting arguments from a commit message taken directly from the try_parser.
        """
        all_try_args = None
        for line in msg.splitlines():
            if 'try: ' in line:
                # Autoland adds quotes to try strings that will confuse our
                # args later on.
                if line.startswith('"') and line.endswith('"'):
                    line = line[1:-1]
                # Allow spaces inside of [filter expressions]
                try_message = line.strip().split('try: ', 1)
                all_try_args = re.findall(r'(?:\[.*?\]|\S)+', try_message[1])
                break

        if not all_try_args:
            self.warning('Try syntax not found in buildbot config, unable to append '
                         'arguments from try.')
            return


        parser = argparse.ArgumentParser(
            description=('Parse an additional subset of arguments passed to try syntax'
                         ' and forward them to the underlying test harness command.'))

        label_dict = {}
        def label_from_val(val):
            if val in label_dict:
                return label_dict[val]
            return '--%s' % val.replace('_', '-')

        for label, opts in known_try_arguments.iteritems():
            if 'action' in opts and opts['action'] not in ('append', 'store',
                                                           'store_true', 'store_false'):
                self.fatal('Try syntax does not support passing custom or store_const '
                           'arguments to the harness process.')
            if 'dest' in opts:
                label_dict[opts['dest']] = label

            parser.add_argument(label, **opts)

        parser.add_argument('--try-test-paths', nargs='*')
        (args, _) = parser.parse_known_args(all_try_args)
        self.try_test_paths = self._group_test_paths(args.try_test_paths)
        del args.try_test_paths

        out_args = []
        # This is a pretty hacky way to echo arguments down to the harness.
        # Hopefully this can be improved once we have a configuration system
        # in tree for harnesses that relies less on a command line.
        for (arg, value) in vars(args).iteritems():
            if value:
                label = label_from_val(arg)
                if isinstance(value, bool):
                    # A store_true or store_false argument.
                    out_args.append(label)
                elif isinstance(value, list):
                    out_args.extend(['%s=%s' % (label, el) for el in value])
                else:
                    out_args.append('%s=%s' % (label, value))

        self.harness_extra_args = out_args

    def _group_test_paths(self, args):
        rv = defaultdict(list)

        if args is None:
            return rv

        for item in args:
            suite, path = item.split(":", 1)
            rv[suite].append(path)
        return rv

    def try_args(self, flavor):
        """Get arguments, test_list derived from try syntax to apply to a command"""
        # TODO: Detect and reject incompatible arguments
        args = self.harness_extra_args[:] if self.harness_extra_args else []
        tests = []

        if self.try_test_paths[flavor]:
            self.info('TinderboxPrint: Tests will be run from the following '
                      'files: %s.' % ','.join(self.try_test_paths[flavor]))
            args.extend(['--this-chunk=1', '--total-chunks=1'])
            tests = self.try_test_paths[flavor][:]

        if args or tests:
            self.info('TinderboxPrint: The following arguments were forwarded from mozharness '
                      'to the test command:\nTinderboxPrint: \t%s -- %s' %
                      (" ".join(args), " ".join(tests)))

        return args, tests
