class TreeNode(object):
    def __init__(self, parent):
        self.next = None
        self.prev = None
        self.folded = True
        self.applied = True
        self.partial = False
        self.parent = parent
        self.neverUnfolded = True

    def allChildren(self):
        return []

    def firstChild(self):
        kids = self.allChildren()
        return kids[0] if kids else None

    def prettyStr(self):
        return self.name

    def nextItem(self, constrainLevel = True):
        if constrainLevel or self.folded:
            if self.nextSib:
                return self.nextSib
            parent = self.parentItem()
            while parent and not parent.nextSib:
                parent = parent.parentItem()
            return parent.nextSib if parent else None
        else:
            return self.next

    def prevItem(self, constrainLevel = True):
        if constrainLevel:
            return self.prevSib
        else:
            if not self.prevSib:
                return self.prev
            if self.prevSib.folded:
                return self.prevSib
            prev = self.prev
            while prev.parentItem() and prev.parentItem().folded:
                prev = prev.parentItem()
            return prev

    def parentItem(self):
        return self.parent

    def special(self):
        return False

    def canFold(self):
        return len(self.allChildren()) > 0

    def isFoldRoot(self):
        return False

    def applyRecursively(self, fun, *args):
        if not fun(self, *args):
            return
        for node in self.allChildren():
            node.applyRecursively(fun, *args)

    def status(self):
        return None

    def inheritApply(self):
        return True

    def setDescendantsApplied(self, applied):
        '''
        Set the 'applied' field to the given value, and recurse through all
        descendants (but stopping wherever inheritApply returns False). Also
        update the 'partial' field of all descendants.
        '''
        self.applied = applied
        self.partial = False
        for kid in self.allChildren():
            if not applied:
                kid.setDescendantsApplied(False)
            else:
                if kid.inheritApply():
                    kid.setDescendantsApplied(True)
                    if kid.partial:
                        self.partial = True
                else:
                    self.partial = True

    def setApplied(self, value):
        self.setDescendantsApplied(value)
        self.updateAncestors()

    def updateAncestors(self):
        '''
        Set the applied and partial fields of all ancestors. The fields of self
        and all descendants must already be correct.
        '''
        node = self.parentItem()
        while node:
            kids_applied = [ kid.applied for kid in node.allChildren() ]
            if True in kids_applied:
                node.applied = True
                kids_partial = [ kid.partial for kid in node.allChildren() ]
                node.partial = (False in kids_applied) or (True in kids_partial)
            else:
                node.applied = False
                node.partial = False

            node = node.parentItem()

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
