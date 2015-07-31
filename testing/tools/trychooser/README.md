*trychooser* provides a menu to select job choices and creates a TryChooser syntax. It is structured as an hg extension, but it should also work as a command-line program.

### Installation

To install, add this line to your .hgrc:

    [extensions]
    trychooser = path/to/trychooser/

### Running

To push to tryserver after filling out the menu, type:

    $ hg trychooser


### Questionnaire mode

If no curses-capable terminal is detected, trychooser will fall back to "questionnaire" mode, where it will ask a series of text questions. Force this mode with:

    $ hg trychooser -Q


### Command line

To just write the try syntax string from the command line:

    $ ./trychooser
      or
    $ hg trychooser -n


### Meta

Based on Paul Biggar's [hg extension](https://github.com/pbiggar/trychooser), which itself was based on Lukas Blakk's [web version](http://trychooser.pub.build.mozilla.org/) ([Code](http://hg.mozilla.org/build/tools/trychooser)).

See also the [TryChooser page](https://wiki.mozilla.org/ReleaseEngineering/TryChooser) on the Mozilla wiki.

Bugs and patches via [BitBucket issue tracker](https://bitbucket.org/sfink/trychooser/issues)
