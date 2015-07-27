# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import sys
import os
import itertools
import subprocess
import which

from collections import defaultdict


TRY_SYNTAX_TMPL = """
try: -b %s -p %s -u %s -t none %s %s --try-test-paths %s
"""

class AutoTry(object):

    test_flavors = {
        'browser-chrome': {},
        'chrome': {},
        'devtools-chrome': {},
        'mochitest': {},
        'xpcshell' :{},
        'reftest': {
            "path": lambda x: os.path.join("tests", "reftest", "tests", x)
        },
        'crashtest': {
            "path": lambda x: os.path.join("tests", "reftest", "tests", x)
        },
        'web-platform-tests': {
            "path": lambda x: os.path.join("tests", x.split("testing" + os.path.sep)[1])
        }
    }

    def __init__(self, topsrcdir, resolver, mach_context):
        self.topsrcdir = topsrcdir
        self.resolver = resolver
        self.mach_context = mach_context

        if os.path.exists(os.path.join(self.topsrcdir, '.hg')):
            self._use_git = False
        else:
            self._use_git = True

    def paths_by_flavor(self, paths):
        paths_by_flavor = defaultdict(set)

        if not paths:
            return dict(paths_by_flavor)

        tests = list(self.resolver.resolve_tests(paths=paths,
                                                 cwd=self.mach_context.cwd))
        sorted_paths = list(sorted(paths, key=lambda x:-len(x)))
        for t in tests:
            if t['flavor'] in AutoTry.test_flavors:
                flavor = t['flavor']
                path_func = AutoTry.test_flavors[flavor].get("path", lambda x:x)
                if 'subsuite' in t and t['subsuite'] == 'devtools':
                    flavor = 'devtools-chrome'
                for path in sorted_paths:
                    if t['file_relpath'].startswith(path):
                        paths_by_flavor[flavor].add(path_func(path))

        return dict(paths_by_flavor)

    def remove_duplicates(self, paths_by_flavor, tests):
        rv = {}
        for item in paths_by_flavor:
            if item not in tests:
                rv[item] = paths_by_flavor[item].copy()
        return rv

    def calc_try_syntax(self, platforms, tests, builds, paths_by_flavor, tags, extra_args):
        #problem: if we specify a directory like foo/bar to reftests and there isn't
        #a reftest file in foo/bar but there is one in foo/bar/baz, the reftest harness
        #won't run the tests

        # Maps from flavors to the job names needed to run that flavour
        flavor_jobs = {
            'mochitest': ['mochitest-1', 'mochitest-e10s-1'],
            'xpcshell': ['xpcshell'],
            'chrome': ['mochitest-o'],
            'browser-chrome': ['mochitest-browser-chrome-1',
                               'mochitest-e10s-browser-chrome-1'],
            'devtools-chrome': ['mochitest-dt',
                                'mochitest-e10s-devtools-chrome'],
            'crashtest': ['crashtest', 'crashtest-e10s'],
            'reftest': ['reftest', 'reftest-e10s'],
            'web-platform-tests': ['web-platform-tests-1']
        }

        if tags:
            tags = ' '.join('--tag %s' % t for t in tags)
        else:
            tags = ''

        suites = set(tests)

        paths = set()
        for flavor, flavor_tests in paths_by_flavor.iteritems():
            if flavor not in suites:
                for job_name in flavor_jobs[flavor]:
                    for test in flavor_tests:
                        paths.add("%s:%s" % (flavor, test))
                    suites.add(job_name)
        paths = " ".join(sorted(paths))

        suites = ",".join(sorted(suites))

        if extra_args is None:
            extra_args = []
        extra_args = " ".join(extra_args)

        return TRY_SYNTAX_TMPL % (builds, platforms, suites, tags, extra_args, paths)

    def _run_git(self, *args):
        args = ['git'] + list(args)
        ret = subprocess.call(args)
        if ret:
            print('ERROR git command %s returned %s' %
                  (args, ret))
            sys.exit(1)

    def _git_push_to_try(self, msg):
        self._run_git('commit', '--allow-empty', '-m', msg)
        self._run_git('push', 'hg::ssh://hg.mozilla.org/try',
                      '+HEAD:refs/heads/branches/default/tip')
        self._run_git('reset', 'HEAD~')

    def push_to_try(self, msg, verbose):
        if not self._use_git:
            try:
                hg_args = ['hg', 'push-to-try', '-m', msg]
                subprocess.check_call(hg_args, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                print('ERROR hg command %s returned %s' % (hg_args, e.returncode))
                print('The "push-to-try" hg extension is required to push from '
                      'hg to try with the autotry command.\n\nIt can be installed '
                      'by running ./mach mercurial-setup')
                sys.exit(1)
        else:
            try:
                which.which('git-cinnabar')
                self._git_push_to_try(msg)
            except which.WhichError:
                print('ERROR git-cinnabar is required to push from git to try with'
                      'the autotry command.\n\nMore information can by found at '
                      'https://github.com/glandium/git-cinnabar')
                sys.exit(1)

    def find_uncommited_changes(self):
        if self._use_git:
            stat = subprocess.check_output(['git', 'status', '-z'])
            return any(len(entry.strip()) and entry.strip()[0] in ('A', 'M', 'D')
                       for entry in stat.split('\0'))
        else:
            stat = subprocess.check_output(['hg', 'status'])
            return any(len(entry.strip()) and entry.strip()[0] in ('A', 'M', 'R')
                       for entry in stat.splitlines())
