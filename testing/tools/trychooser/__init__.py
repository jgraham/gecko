#!/usr/bin/env python

import json
import re
import os
import sys
from collections import defaultdict

from menu import QuitException

try:
    from menu import make_selector
    from try_selector import CursesTrySelector
except Exception as e:
    print e
    pass # No curses menu for you

from trynodes import Category, TreeRoot

def load_data():
    with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "jobs.json")) as f:
        data = json.load(f)
    return data

def linkTree(siblings, prev = None):
    prevsib = None
    for node in siblings:
        if prevsib:
            prevsib.nextSib = node
        node.prevSib = prevsib
        prevsib = node
    if prevsib:
        prevsib.nextSib = None

    for node in siblings:
        node.prev = prev
        if prev:
            prev.next = node
        prev = linkTree(node.allChildren(), node)

    return prev

def treeOptionsFromCmdOptions(data, initial):
    rv = initial.copy()
    rv["configuration"] = []
    for code, config in [("d", "debug"),
                         ("o", "opt")]:
        if code in initial["configuration"]:
            rv["configuration"].append(config)

    for category in ["platforms", "tests"]:
        if category not in initial:
            continue

        if initial[category] == "all":
            rv[category] = ["all"]
            continue

        items = [item for item in data["jobs"] if category in item]
        assert len(items) == 1

        output_data = []
        makeTreeItem(items[0][category], output_data, [], initial[category])

        rv[category] = output_data

    return rv

def makeTreeItem(src_tree, output, prefixes, targets):
    for item in src_tree:
        if isinstance(item, dict):
            prefixes.append(item["name"])
            makeTreeItem(item["options"], output, prefixes, targets)
            prefixes.pop()
        elif item in targets:
            target = output
            for prefix in prefixes:
                for existing in output:
                    if hasattr(existing, "keys") and existing.keys()[0] == prefix:
                        target = existing.values()[0]
                        break
                else:
                    new = {prefix: []}
                    output.append(new)
                    target = new.values()[0]
            target.append(item)

# Convert the compressed, user-editable representation of initial settings to
# something easier to process.
#
# Input Examples:
#
# "platform": "linux"
#   - within platform, only 'linux' is selected, along with all suboptions of 'linux'
#     (if any)
# "platform": [ "linux", "windows" ]
#   - within platform, 'linux' and 'windows' are selected, and relevant suboptions.
# "platform": [ { "linux": "linux64" }, "windows" ]
#   - within platform, the 'linux64' suboption of 'linux', 'windows', and all
#     suboptions of 'windows'
# "platform": "all"
#   - all platform options are selected
#
# Output Examples, corresponding to the above input:
# { "platform": "linux" }
# { "platform": { "linux": "all", "windows": "all" } }
# { "platform": { "linux": "linux64", "windows": "all" } }
# { "platform": "all" }

def expandInitial(initial):
    if isinstance(initial, list):
        dicts = [ (expandInitial(e) if isinstance(e, dict) else {str(e):'all'})
                  for e in initial ]
        initial = {}
        for d in dicts: initial.update(d)
        return initial
    elif isinstance(initial, dict):
        return dict([ (str(i[0]), expandInitial(i[1])) for i in initial.items() ])
    else:
        return str(initial)

# initial is a parallel structure to data, though note that we're looking at
# the TryOption tree produced from data, not the original JSON structure.
#
def setInitial(tree, initial):
    all_kids_true = True
    all_kids_false = True
    for datum in tree.allChildren():
        nonLeafNode = datum.allChildren()
        datum.applied = False
        if initial == 'full':
            datum.applied = True
        elif initial == 'all' or initial == datum.name:
            datum.applied = not datum.nondefault
        elif isinstance(initial, dict) and initial.has_key(datum.name):
            datum.applied = True

        if datum.applied:
            all_kids_false = False
            if nonLeafNode:
                kid_initial = initial[datum.name] if isinstance(initial, dict) else 'all'
                alltrue, allfalse = setInitial(datum, kid_initial)
                datum.partial = (not alltrue and not allfalse)
                if allfalse:
                    datum.applied = False
        else:
            all_kids_true = False
            if nonLeafNode:
                setInitial(datum, [])

    return all_kids_true, all_kids_false

def dumpSelections(opt, indent=''):
    if opt.applied:
        print("%sX %s" % (indent, opt.name))
    else:
        print("%s  %s" % (indent, opt.name))
    for o in opt.allChildren():
        dumpSelections(o, indent + '  ')

def scanForDefaults(node):
    if node.applied:
        all = True
        alldefaults = True
        nondefaults = node.nondefault
        for kid in node.allChildren():
            kid_all, kid_alldefaults, kid_nondefaults = scanForDefaults(kid)
            all = all and kid_all
            alldefaults = alldefaults and kid_alldefaults
            nondefaults = nondefaults or kid_nondefaults
        return (all, alldefaults, nondefaults)
    else:
        return (False, node.nondefault, False)

def kidSyntax(syntax, item):
    if item.name in syntax:
        return syntax[item.name]
    if item.allChildren():
        return {}
    return { item.name: item.name } # leaf

def options(data, syntax):
    if not data.applied:
        return []

    all, alldefaults, nondefaults = scanForDefaults(data)

    if syntax != "*" and alldefaults:
        # All default options were selected, and the syntax doesn't say to just
        # enumerate each option individually
        if all and 'all' in syntax:
            # Currently unused
            return [syntax['all']]
        if not nondefaults and 'all-default' in syntax:
            # Special name for when you want all of the (default) options
            return [syntax['all-default']]
        if not isinstance(syntax, dict):
            # I don't think this is ever used?
            return [syntax]
        if data.name in syntax:
            return [syntax[data.name]]

    # If we make it here, it's the same as if syntax were '*' (i.e., we need to
    # list out all options individually)

    if not isinstance(syntax, dict):
        syntax = {}

    rv = []
    for kid in data.allChildren():
        opts = options(kid, kidSyntax(syntax, kid))
        rv.extend(item for item in opts if item)

    assert not any(isinstance(item, list) for item in rv)

    return rv

def tryDataFromTree(tree_data, syntax):
    rv = []
    for category in tree_data:
        cat_syntax = syntax[category.name]
        opts = (options(category, cat_syntax))
        rv.append((category.name, opts))
    return rv

def calculate_try_syntax(data):
    parts = []

    parts.append("-b")
    parts.extend(data["configuration"])

    parts.append("-p")
    parts.append(",".join(data["platforms"]))

    if data["tests"]:
        parts.append("-u")
        parts.append(",".join(data["tests"]))

    if data["tags"]:
        parts.append(' '.join('--tag %s' % t for t in data["tags"]))

    if data["extra_args"] is not None:
        parts.extend(data["extra_args"])

    if data["paths"]:
        parts.append("--try-test-paths %s" % " ".join(sorted(data["paths"])))

    return " ".join(parts)

def generateTrySyntax(tree_data, syntax, defaults):
    data = defaults.copy()
    data.update(tryDataFromTree(tree_data, syntax))
    return calculate_try_syntax(data)

def plural(single):
    if single.endswith("s") or single.endswith("x"):
        return single
    else:
        return single + "s"

def add_defaultness(s, item):
    if item.nondefault:
        return s + " (disabled by default)"
    else:
        return s

def question(ui, options, questions, indent = ""):
    pattern = questions.get("pattern", "Run %s")
    for option in options:
        name = option.name
        config = questions.get(name, {})
        if not isinstance(config, dict):
            prompts = config
            config = { }
        else:
            config.setdefault("pattern", pattern)
            if "prompts" in config:
                prompts = config["prompts"]
            else:
                numChildren = len(option.allChildren())
                if numChildren == 0:
                    prompts = pattern % (name, )
                elif numChildren <= 2:
                    question(ui, option.allChildren(), config, indent)
                    continue
                else:
                    prompts = [ "Run all default " + plural(name), "Run any " + plural(name) ]

        if isinstance(prompts, list):
            # Want all X?
            response = ui.prompt(indent + prompts[0] + "?", default='n')
            if response == 'y':
                option.setApplied(True)
            else:
                if len(prompts) > 1:
                    # Want any X?
                    response = ui.prompt(indent + prompts[1] + "?", default='n' if option.nondefault else 'y')
                    if response == 'y':
                        question(ui, option.allChildren(), config, indent + "  ")
                else:
                    question(ui, option.allChildren(), config, indent + "  ")
        else:
            p = add_defaultness(indent + prompts, option) + "?"
            response = ui.prompt(p, default='n' if option.nondefault else 'y')
            option.setApplied(response == 'y')

def suggest_results_bug(ui, repo):
    ui.write('Leave a comment in a bug on completion?\n')
    if ui.promptchoice('[Yn]', ['&Yes', '&no'], default=0):
      return None

    # Derive a suggested bug number in which to leave results (regex stolen from bzexport.py)
    bug_re = re.compile(r'''# bug followed by any sequence of numbers, or
                              # a standalone sequence of numbers
                         (
                           (?:
                             bug |
                             b= |
                             # a sequence of 5+ numbers preceded by whitespace
                             (?=\b\#?\d{5,}) |
                             # numbers at the very beginning
                             ^(?=\d)
                           )
                           (?:\s*\#?)(\d+)
                         )''', re.I | re.X)

    rev = repo.mq.applied[-1].name
    match = re.search(bug_re, repo[rev].description())
    s = 'Bug number'
    suggested = None
    if match:
        suggested = match.group(2)
        s += ' (%s)' % suggested
    ui.write('%s:\n' % s)
    bugnum = None
    while not bugnum:
      try:
        numstr = ui.prompt('', str(suggested))
        return int(numstr)
      except:
        ui.write('Invalid bug number\n')

def filterJobs(data, filterFunc, parents=[]):
    rv = []
    for item in data:
        if isinstance(item, dict):
            if "name" in item:
                parents.append(item["name"])
                filtered = filterJobs(item["options"], filterFunc, parents)
                parents.pop()
                if filtered:
                    rv.append({"name": item["name"],
                               "options": filtered})
            else:
                assert(len(item) == 1 and not parents)
                category = item.keys()[0]
                parents.append(category)
                filtered = filterJobs(item[category], filterFunc, parents)
                parents.pop()
                rv.append({category: filtered})
        else:
            if filterFunc(parents, item):
                rv.append(item)
    return rv

def main(job_filters=None, initial_choices=None):
    menu = make_selector(CursesTrySelector)

    data = load_data()
    if job_filters:
        data["jobs"] = filterJobs(data["jobs"], job_filters)

    headers = TreeRoot([ Category(pair.keys()[0], pair.values()[0]) for pair in data['jobs'] ])
    linkTree(headers)

    initial = data["initial"]
    if initial_choices:
        initial_choices = treeOptionsFromCmdOptions(data, initial_choices)
        for item in initial:
            if initial_choices[item]:
                initial[item] = initial_choices[item]

    setInitial(headers, expandInitial(initial))
    syntaxGenerator = lambda h: generateTrySyntax(h, data['syntax'], initial)
    return menu({"syntaxGenerator": syntaxGenerator}, headers)

if __name__ == "__main__":
    main()
