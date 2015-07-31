import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from trychooser import question, generateTrySyntax, headers, data
from menu import make_selector
from try_selector import CursesTrySelector

class UI:
    def _readline(self, prompt=''):
        try:
            import readline
            readline.read_history_file
        except:
            pass
        line = raw_input(prompt)
        if os.linesep == '\r\n' and line and line[-1] == '\r':
            line = line[:-1]
        return line

    def prompt(self, msg, default="y"):
        r = self._readline(msg + ' ')
        return r if r else default

    def write(self, *args, **opts):
        for a in args:
            sys.stdout.write(a)

ui = None
menu = make_selector(CursesTrySelector)
syntaxGenerator = lambda h: generateTrySyntax(h, data['syntax'])
msg = menu({ "syntaxGenerator": syntaxGenerator }, headers, ui)

#ui = UI()
#question(ui, headers, data['questions'])
#msg = generateTrySyntax(headers, data['syntax'])

print "try: " + msg
