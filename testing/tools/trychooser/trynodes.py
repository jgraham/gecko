import re
from treenode import TreeNode

paren_re = re.compile(r'^\((.*)\)$')

class TryOption(TreeNode):
    def makeChild(self, kid, depth):
        if isinstance(kid, dict):
            return TryOption(self, depth, kid['name'], kid['options'])
        else:
            return TryOption(self, depth, kid, None)

    def grabChildren(self, kids):
        if isinstance(kids, list):
            self.options = [ self.makeChild(kid, self.depth+1) for kid in kids ]
        elif kids is None:
            self.options = []
        else:
            self.options = [ self.makeChild(kids, self.depth+1) ]

    def __init__(self, parent, depth, name, kids):
        TreeNode.__init__(self, parent)
        m = paren_re.match(name)
        if m:
            self.name = m.group(1)
            self.nondefault = True
        else:
            self.name = name
            self.nondefault = False
        self.parent = parent
        self.depth = depth
        self.grabChildren(kids)

    def allChildren(self):
        return self.options

    def prettyStr(self):
        if self.nondefault:
            return "(%s)" % self.name
        else:
            return self.name

    def inheritApply(self):
        return not self.nondefault

class Category(TryOption):
    def __init__(self, myname, children):
        TryOption.__init__(self, None, 0, myname, children)
        self.folded = False

    def allChildren(self):
        return self.options

    def isFoldRoot(self):
        return True

class TreeRoot(list):
    def allChildren(self):
        return self

    def parentItem(self):
        return None

    pass
