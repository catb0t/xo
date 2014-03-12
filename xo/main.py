#!/usr/bin/env python3
#
# Urwid example lazy text editor suitable for tabbed and format=flowed text
#    Copyright (C) 2004-2009  Ian Ward
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: http://excess.org/urwid/

"""
Urwid example lazy text editor suitable for tabbed and flowing text

Features:
- custom list walker for lazily loading text file

Usage:
edit.py <filename>

"""
import os
import sys

import urwid
import pygments.util
from pygments.lexers import guess_lexer, guess_lexer_for_filename, get_lexer_by_name
from pygments.lexers.special import TextLexer
from pygments.styles.monokai import MonokaiStyle as S

from colortrans import rgb2short

class HighlightedEdit(urwid.Edit):

    def __init__(self, lexer=None, **kwargs):
        super().__init__(**kwargs)
        if lexer is None:
           lexer = guess_lexer(self.get_edit_text())
        self.lexer = lexer

    def get_text(self):
        etext = self.get_edit_text()
        tokens = self.lexer.get_tokens(etext)
        attrib = [(tok, len(s)) for tok, s in tokens]
        return etext, attrib

class LineWalker(urwid.ListWalker):
    """ListWalker-compatible class for lazily reading file contents."""
    
    def __init__(self, name):
        self.name = name
        self.file = f = open(name)
        try:
            self.lexer = guess_lexer_for_filename(name, f.readline())
        except TypeError:
            self.lexer = get_lexer_by_name(os.path.splitext(name)[1][1:])
        except pygments.util.ClassNotFound:
            self.lexer = TextLexer()
        f.seek(0)
        self.lines = []
        self.focus = 0
        self.clipboard = None
    
    def get_focus(self): 
        return self._get_at_pos(self.focus)
    
    def set_focus(self, focus):
        self.focus = focus
        self._modified()
    
    def get_next(self, start_from):
        return self._get_at_pos(start_from + 1)
    
    def get_prev(self, start_from):
        return self._get_at_pos(start_from - 1)

    def read_next_line(self):
        """Read another line from the file."""
        
        next_line = self.file.readline()
        
        if not next_line or next_line[-1:] != '\n':
            # no newline on last line of file
            self.file = None
        else:
            # trim newline characters
            next_line = next_line[:-1]

        expanded = next_line.expandtabs()
        
        edit = HighlightedEdit(caption="", edit_text=expanded, allow_tab=True,
                               lexer=self.lexer, wrap='clip')
        edit.set_edit_pos(0)
        edit.original_text = next_line
        self.lines.append(edit)

        return next_line
        
    
    def _get_at_pos(self, pos):
        """Return a widget for the line number passed."""
        
        if pos < 0:
            # line 0 is the start of the file, no more above
            return None, None
            
        if len(self.lines) > pos:
            # we have that line so return it
            return self.lines[pos], pos

        if self.file is None:
            # file is closed, so there are no more lines
            return None, None

        assert pos == len(self.lines), "out of order request?"

        self.read_next_line()
        
        return self.lines[-1], pos
    
    def split_focus(self):
        """Divide the focus edit widget at the cursor location."""
        
        focus = self.lines[self.focus]
        pos = focus.edit_pos
        edit = HighlightedEdit(caption="", edit_text=focus.edit_text[pos:],
                               allow_tab=True, lexer=self.lexer, wrap='clip')
        edit.original_text = ""
        focus.set_edit_text(focus.edit_text[:pos])
        edit.set_edit_pos(0)
        self.lines.insert(self.focus+1, edit)

    def combine_focus_with_prev(self):
        """Combine the focus edit widget with the one above."""

        above, ignore = self.get_prev(self.focus)
        if above is None:
            # already at the top
            return
        
        focus = self.lines[self.focus]
        above.set_edit_pos(len(above.edit_text))
        above.set_edit_text(above.edit_text + focus.edit_text)
        del self.lines[self.focus]
        self.focus -= 1

    def combine_focus_with_next(self):
        """Combine the focus edit widget with the one below."""

        below, ignore = self.get_next(self.focus)
        if below is None:
            # already at bottom
            return
        
        focus = self.lines[self.focus]
        focus.set_edit_text(focus.edit_text + below.edit_text)
        del self.lines[self.focus+1]

    def get_coords(self):
        """Returns the line / col position. These are 1-indexed."""
        focus = self.focus
        return focus + 1, self.lines[self.focus].edit_pos + 1

    #
    # Clipboard methods
    #
    def cut_to_clipboard(self):
        """Cuts the current line to the clipboard."""
        if self.clipboard is None:
           self.clipboard = []
        focus = self.focus
        self.clipboard.append(self.lines.pop(focus))
        if focus == len(self.lines):
           focus -= 1
        self.set_focus(focus)

    def paste_from_clipboard(self):
        """Insert lines from the clipboard at the current position."""
        cb = self.clipboard
        if cb is None:
            return
        for line in cb[::-1]:
            newline = HighlightedEdit(caption="", edit_text=line.get_edit_text(), 
                                      allow_tab=True, lexer=self.lexer, wrap='clip')
            newline.original_text = ""
            self.lines.insert(self.focus, newline)
        self.set_focus(self.focus + len(cb))

    def clear_clipboard(self):
        """Removes the existing clipboard, destroying all lines in the process."""
        self.clipboard = None

class EditDisplay(object):
    palette = [
        ('body','default', 'default'),
        ('foot','black', 'dark blue', 'bold'),
        ('key','black', 'dark magenta', 'underline'),
        ]
        
    footer_text = ('foot', [
        "xo    ",
        ('key', "^x"), " exit ",
        ('key', "^o"), " save ",
        "L:C"
        ])
    
    def __init__(self, name):
        self.save_name = name
        self.disp_name = os.path.split(name)[1]
        self.walker = LineWalker(name) 
        self.listbox = urwid.ListBox(self.walker)
        self.footer = urwid.AttrWrap(urwid.Text(self.footer_text), "foot")
        self.view = urwid.Frame(urwid.AttrWrap(self.listbox, 'body'),
            footer=self.footer)
        self.clipboard = None

        default = 'default'
        for tok, st in S.styles.items():
            if '#' not in st:
                st = ''
            st = st.split()
            st.sort()
            c = default if len(st) == 0 else 'h' + rgb2short(st[0][1:])[0]
            a = urwid.AttrSpec(c, default, colors=256)
            row = (tok, default, default, default, a.foreground, default)
            self.palette.append(row)

    def main(self):
        loop = urwid.MainLoop(self.view,
            handle_mouse=False,
            unhandled_input=self.unhandled_keypress)
        loop.screen.set_terminal_properties(256)
        loop.screen.register_palette(self.palette)
        self.loop = loop
        self.loop.run()

    def reset_footer(self, status="xo    "):
        ft = self.footer_text
        ft[1][0] = status
        ft[1][-1] = "{0}:{1[0]}:{1[1]}".format(self.disp_name, self.walker.get_coords())
        self.footer.w.set_text(ft)
    
    def unhandled_keypress(self, k):
        """Last resort for keypresses."""

        status = "xo    "
        if k == "ctrl o":
            self.save_file()
            status = "saved "
        elif k == "ctrl x":
            raise urwid.ExitMainLoop()
        elif k == "delete":
            # delete at end of line
            self.walker.combine_focus_with_next()
        elif k == "backspace":
            # backspace at beginning of line
            self.walker.combine_focus_with_prev()
        elif k == "enter":
            # start new line
            self.walker.split_focus()
            # move the cursor to the new line and reset pref_col
            self.loop.process_input(["down", "home"])
        elif k == "right":
            w, pos = self.walker.get_focus()
            w, pos = self.walker.get_next(pos)
            if w:
                self.listbox.set_focus(pos, 'above')
                self.loop.process_input(["home"])
        elif k == "left":
            w, pos = self.walker.get_focus()
            w, pos = self.walker.get_prev(pos)
            if w:
                self.listbox.set_focus(pos, 'below')
                self.loop.process_input(["end"])
        elif k == "ctrl k":
            self.walker.cut_to_clipboard()
        elif k == "ctrl u":
            self.walker.paste_from_clipboard()
        elif k == "ctrl t":
            self.walker.clear_clipboard()
        else:
            self.reset_footer()
            return
        self.reset_footer(status=status)
        return True
            

    def save_file(self):
        """Write the file out to disk."""
        
        l = []
        walk = self.walker
        for edit in walk.lines:
            # collect the text already stored in edit widgets
            if edit.original_text.expandtabs() == edit.edit_text:
                l.append(edit.original_text)
            else:
                l.append(edit.edit_text)
        
        # then the rest
        while walk.file is not None:
            l.append(walk.read_next_line())
            
        # write back to disk
        outfile = open(self.save_name, "w")
        
        prefix = ""
        for line in l:
            outfile.write(prefix + line)
            prefix = "\n"

def re_tab(s):
    """Return a tabbed string from an expanded one."""
    l = []
    p = 0
    for i in range(8, len(s), 8):
        if s[i-2:i] == "  ":
            # collapse two or more spaces into a tab
            l.append(s[p:i].rstrip() + "\t")
            p = i

    if p == 0:
        return s
    else:
        l.append(s[p:])
        return "".join(l)



def main():
    try:
        name = sys.argv[1]
        assert open(name, "a")
    except:
        sys.stderr.write(__doc__)
        return
    EditDisplay(name).main()
    

if __name__=="__main__": 
    main()
