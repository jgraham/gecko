import os

from menu import TreeSelector
from trynodes import TreeRoot, Category, TryOption

# os.name is one of: 'posix', 'nt', 'dos', 'os2', 'mac', or 'ce'
if os.name == 'posix':
    import curses
else:
    # I have no idea if wcurses works...
    import wcurses as curses

class CursesTrySelector(TreeSelector):
    def __init__(self, headerList):
        TreeSelector.__init__(self, TreeRoot(headerList))

        # poor-man's multiple dispatch
        self.printersPre = {
            Category: self.printCategory,
            TryOption: self.printTryOption
            }
        self.printersPost = {
            }

        self.numTopStatusLines = 2
        self.numBottomStatusLines = 3
        self.numStatusLines = self.numTopStatusLines + self.numBottomStatusLines
        self.trySyntaxOverride = None

    def setup(self, opts):
        self.syntaxGenerator = opts['syntaxGenerator']

    def finish(self, opts):
        return self.generateTrySyntax()

    def getCheckboxString(self, item):
        if not item.applied:
            return "[ ]"
        if not item.allChildren(): # leaf node
            return "[*]"
        if not item.partial:
            return "[*]"

        q = list(item.allChildren())
        while q:
            item = q.pop()
            if not item.applied and not item.nondefault:
                return "[/]"
            q += item.allChildren()
        return "[X]"

    def getFoldedString(self, item):
        s = ""
        if item.canFold():
            s += "++" if item.folded else "--"
            if item.status():
                return s + item.status() + " "
        else:
            s += "  "
            if item.status():
                # add two more spaces for headers
                return s + "  "
        return s

    def printCategory(self, me, selected=False, toWin=True,
                      ignoreFolding=False):
        '''includes start/end line indicator'''
        outStr = ""
        # where hunk is in list of siblings
        siblings = me.parentItem().allChildren() if me.parentItem() else self.sectionList
        myIndex = siblings.index(me)

        if myIndex != 0:
            # add separating line before headers
            outStr += self.printString(self.chunkpad, ' '*self.xScreenSize,
                                       toWin=toWin, align=False)

        colorPair = self.getColorPair(name=selected and "selected" or "normal",
                                      attrList=[curses.A_BOLD])

        # print out from-to line with checkbox
        checkBox = self.getStatusPrefixString(me)

        linePrefix = " " * self.hunkIndentNumChars + checkBox

        outStr += self.printString(self.chunkpad, linePrefix, toWin=toWin,
                                   align=False) # add uncolored checkbox/indent
        outStr += self.printString(self.chunkpad, me.name, pair=colorPair,
                                   toWin=toWin)

        return outStr

    def printTryOption(self, me, selected=False, toWin=True,
                      ignoreFolding=False):
        outStr = ""
        indentNumChars = self.hunkLineIndentNumChars
        checkBox = self.getStatusPrefixString(me)

        lineStr = me.prettyStr()

        # select color-pair based on whether line is an addition/removal
        colorPair = None
        if selected:
            colorPair = self.getColorPair(name="selected")
        else:
            colorPair = self.getColorPair(name="normal")

        linePrefix = " " * (me.depth * 2)
        linePrefix += " " * indentNumChars + checkBox
        outStr += self.printString(self.chunkpad, linePrefix, toWin=toWin,
                                   align=False) # add uncolored checkbox/indent
        outStr += self.printString(self.chunkpad, lineStr, pair=colorPair,
                                   toWin=toWin, showWhtSpc=True)
        return outStr

    def printStatusLines(self):
        self.printString(self.statuswin,
                    "SELECT JOBS: (j/k/up/dn/pgup/pgdn) move cursor; "
                    "(space/A) toggle build/all",
                    pairName="legend")
        self.printString(self.statuswin,
                    " (f)old/unfold; (c)ommit to selection; (q)uit; (?) help "
                    "| [X]=build selected ++=folded",
                    pairName="legend")

        bottom = "TRY SYNTAX = " + self.generateTrySyntax()
        self.printString(self.bottomstatuswin, bottom, pairName="legend")

        item = self.currentSelectedItem
        if self.lastAction != 'selection' and item.canFold():
            bottom = "Press f to " + ("show" if item.folded else "hide") + " children"
            bottom += ", space to " + ("deselect all children" if item.applied else "select defaults") + "\n"
            self.printString(self.bottomstatuswin, bottom, pairName="legend")

    def generateTrySyntax(self):
        if self.trySyntaxOverride:
            return self.trySyntaxOverride
        else:
            return "try: " + self.syntaxGenerator(self.sectionList)

    def confirmCommit(self):
        tryText = self.generateTrySyntax()
        confirmText = "Are you sure you want to commit the selected changes (e=edit) [Yne]? "

        confirmWin = curses.newwin(self.yScreenSize, 0, 0, 0)
        try:
            self.printString(confirmWin, tryText)
            self.printString(confirmWin, confirmText, pairName="selected")
        except curses.error:
            pass
        self.stdscr.refresh()
        confirmWin.refresh()
        try:
            response = chr(self.stdscr.getch())
        except ValueError:
            response = "n"
        if response.lower().startswith("e"):
            self.trySyntaxOverride = self.inline_edit(confirmWin, self.generateTrySyntax()).rstrip()
            return True
        elif response.lower().startswith("y"):
            return True
        else:
            return False

    def handleKey(self, keyPressed, opts):
        if keyPressed in ["c"]:
            if self.confirmCommit():
                return True
        elif keyPressed in ["e"]:
            self.trySyntaxOverride = self.inline_edit(self.bottomstatuswin, self.generateTrySyntax()).rstrip()
            return True
        else:
            return TreeSelector.handleKey(self, keyPressed, opts)

    def helpWindow(self):
        "Print a help window to the screen. Any keypress to exit."
        helpText = """            [press any key to return to the job display]

trychooser allows you to interactively choose which builds and tests you want.
The following are valid keystrokes:

                [SPACE] : (un-)select job
                          [/] - partly selected
                          [X] - all default options selected
                          [*] = all options selected
                      A : (un-)select all jobs
    Up/Down-arrow [k/j] : go to previous/next unfolded job
        PgUp/PgDn [K/J] : go to previous/next job of same type
 Right/Left-arrow [l/h] : go to child job / parent job
 Shift-Left-arrow   [H] : go to parent header / fold selected header
                      f : fold / unfold job, hiding/revealing its children
                      F : fold / unfold parent job and all of its ancestors
                      c : commit to current selection and push to try server
                      e : edit syntax string, then push to try server
                      q : quit without committing
                      ? : help (what you're currently reading)"""

        helpwin = curses.newwin(self.yScreenSize, 0, 0, 0)
        helpLines = helpText.split("\n")
        helpLines = helpLines + [" "]*(
            self.yScreenSize - self.numStatusLines - len(helpLines) - 1)
        try:
            for line in helpLines:
                self.printString(helpwin, line, pairName="legend")
        except curses.error:
            pass
        helpwin.refresh()
        try:
            helpwin.getkey()
        except curses.error:
            pass
