# This code was extracted from the crecord extension

import os
import re
import sys
import fcntl
import struct
import termios
import signal
from cStringIO import StringIO

# This is required for ncurses to display non-ASCII characters in default user
# locale encoding correctly.  --immerrr
import locale
locale.setlocale(locale.LC_ALL, '')

def debug(stdscr):
    curses.nocbreak()
    stdscr.keypad(0)
    curses.echo()
    curses.endwin()
    import pdb; pdb.set_trace()

# os.name is one of: 'posix', 'nt', 'dos', 'os2', 'mac', or 'ce'
if os.name == 'posix':
    import curses
    import curses.ascii
else:
    # I have no idea if wcurses works...
    import wcurses as curses

try:
    curses
except NameError:
    raise Exception('the python curses/wcurses module is not available/installed')

from curses import textpad

class QuitException(Exception):
    pass

def from_local(string):
    if isinstance(string, unicode):
        return string.encode("utf8")
    else:
        return string.decode(sys.getdefaultencoding(), "strict").encode("ut8")

orig_stdout = sys.__stdout__ # used by gethw()

def gethw():
    """
    Magically get the current height and width of the window (without initscr)

    This is a rip-off of a rip-off - taken from the bpython code.  It is
    useful / necessary because otherwise curses.initscr() must be called,
    which can leave the terminal in a nasty state after exiting.

    """
    h, w = struct.unpack(
        "hhhh", fcntl.ioctl(orig_stdout, termios.TIOCGWINSZ, "\000"*8))[0:2]
    return h, w

class TreeSelector(object):
    def __init__(self, headerList):
        self.sectionList = headerList
        self.chunkList = []
        for header in headerList:
            self.chunkList.append(header)
            self.chunkList.extend(header.allChildren())

        # dictionary mapping (fgColor,bgColor) pairs to the corresponding curses
        # color-pair value.
        self.colorPairs = {}

        # maps custom nicknames of color-pairs to curses color-pair values
        self.colorPairNames = {}

        # the currently selected item (section header, item, or whatever)
        self.currentSelectedItem = self.sectionList[0]

        # updated when printing out display -- the 'lines' here are the
        # line positions *in the pad*, not on the screen.
        self.selectedItemStartLine = 0
        self.selectedItemEndLine = None

        # define indentation levels
        self.headerIndentNumChars = 0
        self.hunkIndentNumChars = 3
        self.hunkLineIndentNumChars = 6

        # the first line of the pad to print to the screen
        self.firstLineOfPadToPrint = 0

        # keeps track of the number of lines in the pad
        self.numPadLines = None

        # keep a running count of the number of lines printed to the pad
        # (used for determining when the selected item begins/ends)
        self.linesPrintedToPadSoFar = 0

        # the first line of the pad which is visible on the screen
        self.firstLineOfPadToPrint = 0

        # if the last 'toggle all' command caused all changes to be applied
        self.wasLastToggleAllApplied = True

        self.lastAction = 'init'

    def upArrowEvent(self):
        """
        Try to select the previous item to the current item that has the
        most-indented level.  For example, if a hunk is selected, try to select
        the last HunkLine of the hunk prior to the selected hunk.  Or, if
        the first HunkLine of a hunk is currently selected, then select the
        hunk itself.

        If the currently selected item is already at the top of the screen,
        scroll the screen down to show the new-selected item.

        """
        currentItem = self.currentSelectedItem

        nextItem = currentItem.prevItem(constrainLevel=False)

        if nextItem is None:
            # if no parent item (i.e. currentItem is the first header), then
            # no change...
            nextItem = currentItem

        self.currentSelectedItem = nextItem

    def upArrowShiftEvent(self):
        """
        Select (if possible) the previous item on the same level as the
        currently selected item.  Otherwise, select (if possible) the
        parent-item of the currently selected item.

        If the currently selected item is already at the top of the screen,
        scroll the screen down to show the new-selected item.

        """
        currentItem = self.currentSelectedItem
        nextItem = currentItem.prevItem()
        # if there's no previous item on this level, try choosing the parent
        if nextItem is None:
            nextItem = currentItem.parentItem()
        if nextItem is None:
            # if no parent item (i.e. currentItem is the first header), then
            # no change...
            nextItem = currentItem

        self.currentSelectedItem = nextItem

    def downArrowEvent(self):
        """
        Try to select the next item to the current item that has the
        most-indented level.  For example, if a hunk is selected, select
        the first HunkLine of the selected hunk.  Or, if the last HunkLine of
        a hunk is currently selected, then select the next hunk, if one exists,
        or if not, the next header if one exists.

        If the currently selected item is already at the bottom of the screen,
        scroll the screen up to show the new-selected item.

        """
        #self.startPrintLine += 1 #DEBUG
        currentItem = self.currentSelectedItem

        nextItem = currentItem.nextItem(constrainLevel=False)
        # if there's no next item, keep the selection as-is
        if nextItem is None:
            nextItem = currentItem

        self.currentSelectedItem = nextItem

    def downArrowShiftEvent(self):
        """
        If the cursor is already at the bottom chunk, scroll the screen up and
        move the cursor-position to the subsequent chunk.  Otherwise, only move
        the cursor position down one chunk.

        """
        # TODO: update docstring

        currentItem = self.currentSelectedItem
        nextItem = currentItem.nextItem()
        # if there's no previous item on this level, try choosing the parent's
        # nextItem.
        if nextItem is None:
            try:
                nextItem = currentItem.parentItem().nextItem()
            except AttributeError:
                # parentItem returned None, so nextItem() can't be called
                nextItem = None
        if nextItem is None:
            # if no next item on parent-level, then no change...
            nextItem = currentItem

        self.currentSelectedItem = nextItem

    def rightArrowEvent(self):
        """
        Select (if possible) the first of this item's child-items.

        """
        currentItem = self.currentSelectedItem
        nextItem = currentItem.firstChild()

        # turn off folding if we want to show a child-item
        if currentItem.folded:
            self.toggleFolded(currentItem)

        if nextItem is None:
            # if no next item on parent-level, then no change...
            nextItem = currentItem

        self.currentSelectedItem = nextItem

    def leftArrowEvent(self):
        """
        If the current item can be folded (i.e. it is an unfolded header or
        hunk), then fold it.  Otherwise try select (if possible) the parent
        of this item.

        """
        currentItem = self.currentSelectedItem

        # try to fold the item
        if currentItem.canFold():
            if not currentItem.folded:
                self.toggleFolded(item=currentItem)
                self.lastAction = 'visibility'
                return

        # if it can't be folded, try to select the parent item
        nextItem = currentItem.parentItem()

        if nextItem is None:
            # if no item on parent-level, then no change...
            nextItem = currentItem
            if not nextItem.folded:
                self.toggleFolded(item=nextItem)

        self.currentSelectedItem = nextItem

    def leftArrowShiftEvent(self):
        """
        Select the header of the current item (or fold current item if the
        current item is already a header).

        """
        currentItem = self.currentSelectedItem

        if currentItem.isFoldRoot():
            if not currentItem.folded:
                self.toggleFolded(item=currentItem)
                self.lastAction = 'visibility'
                return

        # select the parent item recursively until we're at a header
        while True:
            nextItem = currentItem.parentItem()
            if nextItem is None:
                break
            else:
                currentItem = nextItem

        self.currentSelectedItem = currentItem

    def updateScroll(self):
        "Scroll the screen to fully show the currently-selected"
        selStart = self.selectedItemStartLine
        selEnd = self.selectedItemEndLine
        #selNumLines = selEnd - selStart
        padStart = self.firstLineOfPadToPrint
        padEnd = padStart + self.yScreenSize - self.numStatusLines - 1
        # 'buffered' pad start/end values which scroll with a certain
        # top/bottom context margin
        padStartBuffered = padStart + 3
        padEndBuffered = padEnd - 3

        if selEnd > padEndBuffered:
            self.scrollLines(selEnd - padEndBuffered)
        elif selStart < padStartBuffered:
            # negative values scroll in pgup direction
            self.scrollLines(selStart - padStartBuffered)


    def scrollLines(self, numLines):
        "Scroll the screen up (down) by numLines when numLines >0 (<0)."
        self.firstLineOfPadToPrint += numLines
        if self.firstLineOfPadToPrint < 0:
            self.firstLineOfPadToPrint = 0
        if self.firstLineOfPadToPrint > self.numPadLines-1:
            self.firstLineOfPadToPrint = self.numPadLines-1

    def toggleApply(self, item=None, new_value=None):
        """
        Toggle the applied flag of the specified item.  If no item is specified,
        toggle the flag of the currently selected item.
        """

        if item is None:
            item = self.currentSelectedItem

        if new_value is None:
            new_value = not item.applied

        item.setApplied(new_value)

    def toggleAll(self):
        "Toggle the applied flag of all items."
        if self.wasLastToggleAllApplied: # then unapply them this time
            for item in self.sectionList:
                if item.applied:
                    self.toggleApply(item)
        else:
            for item in self.sectionList:
                if not item.applied:
                    self.toggleApply(item)
        self.wasLastToggleAllApplied = not self.wasLastToggleAllApplied

    def toggleFolded(self, item=None, foldParent=False):
        "Toggle folded flag of specified item (defaults to currently selected)"
        if item is None:
            item = self.currentSelectedItem

        parent = item.parentItem()
        if foldParent or (parent is None and item.neverUnfolded):
            if parent:
                self.currentSelectedItem = item = parent
            elif item.neverUnfolded:
                item.neverUnfolded = False

            # also fold any foldable children of the parent/current item
            if parent is None: # the original OR 'new' item
                for child in item.allChildren():
                    child.folded = not item.folded

        item.folded = not item.folded

    def getCheckboxString(self, item):
        if item.applied:
            if item.allChildren() and item.partial:
                return "[~]"
            else:
                return "[X]"
        else:
            return "[ ]"

    def getFoldedString(self, item):
        if item.folded and item.canFold():
            s = "**"
            if item.status():
                return s + item.status() + " "
        else:
            s = "  "
            if item.status():
                # add two more spaces for headers
                return s + "  "
        return s

    def getStatusPrefixString(self, item):
        """
        Create a string to prefix a line with which indicates whether 'item'
        is applied and/or folded.

        """
        return self.getCheckboxString(item) + self.getFoldedString(item)

    def alignString(self, inStr, window):
        """
        Add whitespace to the end of a string in order to make it fill
        the screen in the x direction.  The current cursor position is
        taken into account when making this calculation.  The string can span
        multiple lines.

        """
        y,xStart = window.getyx()
        width = self.xScreenSize
        # turn tabs into spaces
        inStr = inStr.expandtabs(4)

        try:
            strLen = len(unicode(from_local(inStr), code))
        except:
            # if text is not utf8, then assume an 8-bit single-byte encoding.
            strLen = len(inStr)

        numSpaces = (width - ((strLen + xStart) % width))
        my,mx = window.getmaxyx()
        if y == my - 1:
            numSpaces -= 1
        return inStr + " " * numSpaces

    def printItemHelper(self, item, ignoreFolding, recurseChildren, toWin=True):
        """
        Recursive method for printing out patch/header/hunk/hunk-line data to
        screen.  Also returns a string with all of the content of the displayed
        patch (not including coloring, etc.).

        If ignoreFolding is True, then folded items are printed out.

        If recurseChildren is False, then only print the item without its
        child items.

        """
        outbuf = StringIO()
        selected = (item is self.currentSelectedItem)
        if selected and recurseChildren:
            # assumes line numbering starting from line 0
            self.selectedItemStartLine = self.linesPrintedToPadSoFar
            selectedItemLines = self.getNumLinesDisplayed(item,
                                                        recurseChildren=False)
            self.selectedItemEndLine = (self.selectedItemStartLine +
                                        selectedItemLines - 1)

        parent = item.parentItem()
        visible = (ignoreFolding or not (parent and parent.folded))

        if not visible:
            return outbuf.getvalue()

        preprint = self.printersPre.get(item.__class__, None)
        if preprint:
            outbuf.write(preprint.__func__(self, item, selected,
                                           toWin=toWin, ignoreFolding=ignoreFolding))

        if recurseChildren:
            for kid in item.allChildren():
                outbuf.write(self.printItemHelper(kid, ignoreFolding, recurseChildren, toWin))

        postprint = self.printersPost.get(item.__class__, None)
        if postprint:
            outbuf.write(postprint.__func__(self, item,
                                            toWin=toWin, ignoreFolding=ignoreFolding))

        return outbuf.getvalue()

    def printItem(self, item=None, ignoreFolding=False, recurseChildren=True,
                  toWin=True):
        """
        Use printItem() to print the the specified item.
        If item is not specified, then print the entire patch.
        (hiding folded elements, etc. -- see printItemHelper() docstring)
        """
        if item is None:
            item = self.sectionList
        if recurseChildren:
            self.linesPrintedToPadSoFar = 0
        out = self.printItemHelper(item, ignoreFolding, recurseChildren, toWin=toWin)
        return out

    def printString(self, window, text, fgColor=None, bgColor=None, pair=None,
        pairName=None, attrList=None, toWin=True, align=True, showWhtSpc=False):
        """
        Print the string, text, with the specified colors and attributes, to
        the specified curses window object.

        The foreground and background colors are of the form
        curses.COLOR_XXXX, where XXXX is one of: [BLACK, BLUE, CYAN, GREEN,
        MAGENTA, RED, WHITE, YELLOW].  If pairName is provided, a color
        pair will be looked up in the self.colorPairNames dictionary.

        attrList is a list containing text attributes in the form of
        curses.A_XXXX, where XXXX can be: [BOLD, DIM, NORMAL, STANDOUT,
        UNDERLINE].

        If align == True, whitespace is added to the printed string such that
        the string stretches to the right border of the window.

        If showWhtSpc == True, trailing whitespace of a string is highlighted.

        """
        try:
            return self._printString(window, text, fgColor, bgColor, pair, pairName, attrList, toWin, align, showWhtSpc)
        except:
            return ''

    def _printString(self, window, text, fgColor=None, bgColor=None, pair=None,
        pairName=None, attrList=None, toWin=True, align=True, showWhtSpc=False):
        # preprocess the text, converting tabs to spaces
        text = text.expandtabs(4)
        # Strip \n, and convert control characters to ^[char] representation
        text = re.sub(r'[\x00-\x08\x0a-\x1f]',
                lambda m:'^'+chr(ord(m.group())+64), text.strip('\n'))

        if pair is not None:
            colorPair = pair
        elif pairName is not None:
            colorPair = self.colorPairNames[pairName]
        else:
            if fgColor is None:
                fgColor = -1
            if bgColor is None:
                bgColor = -1
            if self.colorPairs.has_key((fgColor,bgColor)):
                colorPair = self.colorPairs[(fgColor,bgColor)]
            else:
                colorPair = self.getColorPair(fgColor, bgColor)
        # add attributes if possible
        if attrList is None:
            attrList = []
        if colorPair < 256:
            # then it is safe to apply all attributes
            for textAttr in attrList:
                colorPair |= textAttr
        else:
            # just apply a select few (safe?) attributes
            for textAttr in (curses.A_UNDERLINE, curses.A_BOLD):
                if textAttr in attrList:
                    colorPair |= textAttr

        y,xStart = self.chunkpad.getyx()
        t = "" # variable for counting lines printed
        # if requested, show trailing whitespace
        if showWhtSpc:
            origLen = len(text)
            text = text.rstrip(' \n') # tabs have already been expanded
            strippedLen = len(text)
            numTrailingSpaces = origLen - strippedLen

        if toWin:
            window.addstr(text, colorPair)
        t += text

        if showWhtSpc:
                wsColorPair = colorPair | curses.A_REVERSE
                if toWin:
                    for i in range(numTrailingSpaces):
                        window.addch(curses.ACS_CKBOARD, wsColorPair)
                t += " " * numTrailingSpaces

        if align:
            if toWin:
                extraWhiteSpace = self.alignString("", window)
                window.addstr(extraWhiteSpace, colorPair)
            else:
                # need to use t, since the x position hasn't incremented
                extraWhiteSpace = self.alignString(t, window)
            t += extraWhiteSpace

        # is reset to 0 at the beginning of printItem()

        linesPrinted = (xStart + len(t)) / self.xScreenSize
        self.linesPrintedToPadSoFar += linesPrinted
        return t

    def printStatusLines(self):
        pass

    def updateScreen(self):
        self.statuswin.erase()
        self.chunkpad.erase()
        self.bottomstatuswin.erase()

        # print out the status lines at the top and bottom
        try:
            self.printStatusLines()
        except curses.error:
            pass

        # print out the patch in the remaining part of the window
        try:
            self.printItem()
            self.updateScroll()
            self.chunkpad.refresh(self.firstLineOfPadToPrint, 0,
                                  self.numTopStatusLines, 0,
                                  self.yScreenSize+1-self.numStatusLines,
                                  self.xScreenSize)
        except curses.error:
            pass

        # refresh([pminrow, pmincol, sminrow, smincol, smaxrow, smaxcol])
        self.statuswin.refresh()
        self.bottomstatuswin.refresh()

    def getNumLinesDisplayed(self, item=None, ignoreFolding=False,
                             recurseChildren=True):
        """
        Return the number of lines which would be displayed if the item were
        to be printed to the display.  The item will NOT be printed to the
        display (pad).
        If no item is given, assume the entire patch.
        If ignoreFolding is True, folded items will be unfolded when counting
        the number of lines.

        """
        # temporarily disable printing to windows by printString
        patchDisplayString = self.printItem(item, ignoreFolding,
                                            recurseChildren, toWin=False)
        numLines = len(patchDisplayString)/self.xScreenSize
        return numLines

    def sigwinchHandler(self, n, frame):
        "Handle window resizing"
        try:
            curses.endwin()
            self.yScreenSize, self.xScreenSize = gethw()
            self.statuswin.resize(self.numTopStatusLines,self.xScreenSize)
            self.bottomstatuswin.resize(self.numBottomStatusLines,self.xScreenSize)
            self.numPadLines = self.getNumLinesDisplayed(ignoreFolding=True) + 1
            self.chunkpad = curses.newpad(self.numPadLines, self.xScreenSize)
            # TODO: try to resize commit message window if possible
        except curses.error:
            pass

    def getColorPair(self, fgColor=None, bgColor=None, name=None,
                     attrList=None):
        """
        Get a curses color pair, adding it to self.colorPairs if it is not
        already defined.  An optional string, name, can be passed as a shortcut
        for referring to the color-pair.  By default, if no arguments are
        specified, the white foreground / black background color-pair is
        returned.

        It is expected that this function will be used exclusively for
        initializing color pairs, and NOT curses.init_pair().

        attrList is used to 'flavor' the returned color-pair.  This information
        is not stored in self.colorPairs.  It contains attribute values like
        curses.A_BOLD.

        """
        if (name is not None) and self.colorPairNames.has_key(name):
            # then get the associated color pair and return it
            colorPair = self.colorPairNames[name]
        else:
            if fgColor is None:
                fgColor = -1
            if bgColor is None:
                bgColor = -1
            if self.colorPairs.has_key((fgColor,bgColor)):
                colorPair = self.colorPairs[(fgColor,bgColor)]
            else:
                pairIndex = len(self.colorPairs) + 1
                curses.init_pair(pairIndex, fgColor, bgColor)
                colorPair = self.colorPairs[(fgColor, bgColor)] = (
                    curses.color_pair(pairIndex))
                if name is not None:
                    self.colorPairNames[name] = curses.color_pair(pairIndex)

        # add attributes if possible
        if attrList is None:
            attrList = []
        if colorPair < 256:
            # then it is safe to apply all attributes
            for textAttr in attrList:
                colorPair |= textAttr
        else:
            # just apply a select few (safe?) attributes
            for textAttrib in (curses.A_UNDERLINE, curses.A_BOLD):
                if textAttrib in attrList:
                    colorPair |= textAttrib
        return colorPair

    def initColorPair(self, *args, **kwargs):
        "Same as getColorPair."
        self.getColorPair(*args, **kwargs)

    def setup(self, opts):
        pass

    def finish(self, opts):
        pass

    def inline_edit(self, win, text, prompt = '', enter_submits=True):
        class MenuTextbox(textpad.Textbox):
            def __init__(self, win, insert_mode=False, enter_submits=True):
                textpad.Textbox.__init__(self, win, insert_mode)
                self.enter_submits = enter_submits
            def do_command(self, ch):
                if self.enter_submits and ch == curses.ascii.NL:
                    ch = curses.ascii.BEL
                return textpad.Textbox.do_command(self, ch)

        win.erase()
        try:
            win.addstr(prompt, curses.A_STANDOUT)
            win.addstr(text)
            result = MenuTextbox(win, insert_mode=True, enter_submits=enter_submits).edit()
        except curses.error:
            # Too much text for available space; switch to external editor
            result = self.edit(prompt + text)

        return result.replace(prompt, "")

    def edit(self, text):
        "Create a temporary editing window on the screen. Except that if DISPLAY is set, it will probably pop open a separate window."
        curses.raw()
        curses.def_prog_mode()
        curses.endwin()
        editedText = text #self.ui.edit(text, self.ui.username())
        curses.cbreak()
        self.stdscr.refresh()
        self.stdscr.keypad(1) # allow arrow-keys to continue to function
        return editedText

    def handleKey(self, keyPressed, opts):
        if keyPressed in ["k", "KEY_UP"]:
            self.lastAction = 'navigation'
            self.upArrowEvent()
        if keyPressed in ["K", "KEY_PPAGE"]:
            self.lastAction = 'navigation'
            self.upArrowShiftEvent()
        elif keyPressed in ["j", "KEY_DOWN"]:
            self.lastAction = 'navigation'
            self.downArrowEvent()
        elif keyPressed in ["J", "KEY_NPAGE"]:
            self.lastAction = 'navigation'
            self.downArrowShiftEvent()
        elif keyPressed in ["l", "KEY_RIGHT"]:
            self.lastAction = 'navigation'
            self.rightArrowEvent()
        elif keyPressed in ["h", "KEY_LEFT"]:
            self.lastAction = 'navigation'
            self.leftArrowEvent()
        elif keyPressed in ["H", "KEY_SLEFT"]:
            self.lastAction = 'navigation'
            self.leftArrowShiftEvent()
        elif keyPressed in ["q"]:
            raise QuitException
        elif keyPressed in [' ']:
            self.lastAction = 'selection'
            self.toggleApply()
        elif keyPressed in ['A']:
            self.lastAction = 'selection'
            self.toggleAll()
        elif keyPressed in ["f"]:
            self.lastAction = 'visibility'
            self.toggleFolded()
        elif keyPressed in ["F"]:
            self.lastAction = 'visibility'
            self.toggleFolded(foldParent=True)
        elif keyPressed in ["?"]:
            self.lastAction = 'help'
            self.helpWindow()

        return False

    def main(self, stdscr, opts):
        """
        Method to be wrapped by curses.wrapper() for selecting chunks.

        """
        signal.signal(signal.SIGWINCH, self.sigwinchHandler)
        self.stdscr = stdscr
        self.yScreenSize, self.xScreenSize = self.stdscr.getmaxyx()

        curses.start_color()
        curses.use_default_colors()

        # available colors: black, blue, cyan, green, magenta, white, yellow
        # init_pair(color_id, foreground_color, background_color)
        self.initColorPair(None, None, name="normal")
        self.initColorPair(curses.COLOR_WHITE, curses.COLOR_MAGENTA,
                           name="selected")
        self.initColorPair(curses.COLOR_RED, None, name="deletion")
        self.initColorPair(curses.COLOR_GREEN, None, name="addition")
        self.initColorPair(curses.COLOR_WHITE, curses.COLOR_BLUE, name="legend")
        # newwin([height, width,] begin_y, begin_x)
        self.statuswin = curses.newwin(self.numTopStatusLines,0,0,0)
        self.statuswin.keypad(1) # interpret arrow-key, etc. ESC sequences
        self.bottomstatuswin = curses.newwin(self.numBottomStatusLines,0,self.yScreenSize-self.numBottomStatusLines,0)

        # figure out how much space to allocate for the chunk-pad which is
        # used for displaying the patch

        # stupid hack to prevent getNumLinesDisplayed from failing
        self.chunkpad = curses.newpad(1,self.xScreenSize)

        # add 1 so to account for last line text reaching end of line
        self.numPadLines = self.getNumLinesDisplayed(ignoreFolding=True) + 1
        self.chunkpad = curses.newpad(self.numPadLines, self.xScreenSize)

        # initialize selecteItemEndLine (initial start-line is 0)
        self.selectedItemEndLine = self.getNumLinesDisplayed(
            self.currentSelectedItem, recurseChildren=False)

        self.setup(opts)

        while True:
            self.updateScreen()
            try:
                keyPressed = self.statuswin.getkey()
            except curses.error:
                keyPressed = "FOOBAR"

            if self.handleKey(keyPressed, opts):
                break

        curses.nocbreak()
        stdscr.keypad(0)
        curses.echo()
        curses.endwin()

        # Silly curses.wrapper does not propagate the return value
        opts['_returnValue'] = self.finish(opts)

def make_selector(cls):
    def selector(opts, headerList):
        sel = cls(headerList)
        curses.wrapper(sel.main, opts)
        return opts['_returnValue']
    return selector
