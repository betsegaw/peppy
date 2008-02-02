# peppy Copyright (c) 2006-2008 Rob McMullen
# Licenced under the GPLv2; see http://peppy.flipturn.org for more info
import os, shutil, time, new, re

import wx
import wx.stc
from wx.lib.pubsub import Publisher

from peppy.actions import *
from peppy.major import *
from peppy.lib.foldexplorer import *

from peppy.editra import *
from peppy.editra.stcmixin import *

class BraceHighlightMixin(object):
    """Brace highlighting mixin for STC

    Highlight matching braces or flag mismatched braces.  This is
    called during the EVT_STC_UPDATEUI event handler.

    Code taken from StyledTextCtrl_2 from the wxPython demo.  Should
    probably implement this as a dynamic method of the text control or
    the Major Mode, controllable by a setting.
    """
    def braceHighlight(self):
        # check for matching braces
        braceAtCaret = -1
        braceOpposite = -1
        braceStyle = None
        charBefore = None
        caretPos = self.GetCurrentPos()

        # check before
        if caretPos > 0:
            charBefore = self.GetCharAt(caretPos - 1)
            braceStyle = self.GetStyleAt(caretPos - 1)
            #dprint("before: char=%s style=%d" % (charBefore, braceStyle))

            if charBefore and chr(charBefore) in "[]{}()":
                braceAtCaret = caretPos - 1

        # check after
        if braceAtCaret < 0:
            charAfter = self.GetCharAt(caretPos)
            braceStyle = self.GetStyleAt(caretPos)
            #dprint("after: char=%s style=%d" % (charAfter, braceStyle))

            if charAfter and chr(charAfter) in "[]{}()":
                braceAtCaret = caretPos

        if braceAtCaret >= 0:
            braceOpposite = self.BraceMatch(braceAtCaret)

        if braceAtCaret != -1  and braceOpposite == -1:
            self.BraceBadLight(braceAtCaret)
        else:
            if braceStyle != self.GetStyleAt(braceOpposite):
                self.BraceBadLight(braceAtCaret)
            else:
                self.BraceHighlight(braceAtCaret, braceOpposite)
        


class StandardReturnMixin(object):
    """Mixin to indent the next line to the correct column
    
    This mixin provides L{electricReturn}, which operates when the return
    key is pressed.  At a minimum it should insert the appropriate line end
    character (cr, crlf, or lf depending on the current state of the STC), but
    provides the opportunity to indent the line as well.
    
    The default action is to simply copy the indent level of the previous line.
    """
    def findIndent(self, linenum):
        """Find proper indention of next line given a line number.

        This is designed to be overridden in subclasses.  Given the
        current line, figure out what the indention should be for the
        next line.
        """
        return self.GetLineIndentation(linenum)
        
    def electricReturn(self):
        """Add a newline and indent to the proper tab level.

        Indent to the level of the line above.
        """
        linesep = self.getLinesep()
        
        self.BeginUndoAction()
        # reindent current line (if necessary), then process the return
        #pos = self.reindentLine()
        
        linenum = self.GetCurrentLine()
        pos = self.GetCurrentPos()
        col = self.GetColumn(pos)
        linestart = self.PositionFromLine(linenum)
        line = self.GetLine(linenum)[:pos-linestart]
    
        #get info about the current line's indentation
        ind = self.GetLineIndentation(linenum)

        self.dprint("format = %s col=%d ind = %d" % (repr(linesep), col, ind)) 

        self.SetTargetStart(pos)
        self.SetTargetEnd(pos)
        if col <= ind:
            newline = linesep+self.GetIndentString(col)
        elif not pos:
            newline = linesep
        else:
            ind = self.findIndent(linenum + 1)
            newline = linesep+self.GetIndentString(ind)
        self.ReplaceTarget(newline)
        self.GotoPos(pos + len(newline))
        self.EndUndoAction()

class ReindentBase(object):
    """Base class for reindenting code.
    
    This class provides a base class for major modes that want to implement
    their own reindention code.  The L{reindentLine} method should use
    information about the major mode to indent the line to its correct
    column.  For instance, the L{PythonMode} uses the L{IDLEReindentMixin} to
    calculate the correct indent column of the python source code line.
    
    This operation is typically bound to the tab key, but regardless to the
    actual keypress to which it is bound is *only* called in response to a
    user keypress.
    """
    def reindentLine(self, linenum=None, dedent_only=False):
        """Reindent the specified line to the correct level.

        This method should be overridden in subclasses to provide the proper
        indention based on the type of text file.  The default implementation
        provided here will indent to the previous line.
        
        Return the new cursor position, in case the cursor has moved as a
        result of the indention.
        """
        if linenum is None:
            linenum = self.GetCurrentLine()
        if linenum == 0:
            # first line is always indented correctly
            return self.GetCurrentPos()
        
        linestart = self.PositionFromLine(linenum)

        # actual indention of current line
        indcol = self.GetLineIndentation(linenum) # columns
        pos = self.GetCurrentPos()
        indpos = self.GetLineIndentPosition(linenum) # absolute character position
        col = self.GetColumn(pos)
        self.dprint("linestart=%d indpos=%d pos=%d col=%d indcol=%d" % (linestart, indpos, pos, col, indcol))

        newind = self.getReindentColumn(linenum, linestart, pos, indpos, col, indcol)
        if newind is None:
            return pos
        if dedent_only and newind > indcol:
            return pos
            
        # the target to be replaced is the leading indention of the
        # current line
        indstr = self.GetIndentString(newind)
        self.dprint("linenum=%d indstr='%s'" % (linenum, indstr))
        self.SetTargetStart(linestart)
        self.SetTargetEnd(indpos)
        self.ReplaceTarget(indstr)

        # recalculate cursor position, because it may have moved if it
        # was within the target
        after = self.GetLineIndentPosition(linenum)
        self.dprint("after: indent=%d cursor=%d" % (after, self.GetCurrentPos()))
        if pos < linestart:
            return pos
        newpos = pos - indpos + after
        if newpos < linestart:
            # we were in the indent region, but the region was made smaller
            return after
        elif pos < indpos:
            # in the indent region
            return after
        return newpos

    def getReindentColumn(self, linenum, linestart, pos, indpos, col, indcol):
        """User hook to return the new indentation position.
        
        This routine should be overridden in subclasses to provide the correct
        indentation of the first not-blank character of the line.
        
        linenum: current line number
        linestart: position of character at column zero of line
        pos: position of cursor
        indpos: position of first non-blank character in line
        col: column number of cursor
        indcol: column number of first non-blank character
        
        return: the number of columns to indent, or None to leave as-is
        """
        return None


class StandardReindentMixin(ReindentBase):
    """Default implementation of a L{ReindentBase} for generic text files.
    
    This class provides a default implementation of line reindentation; it
    simply reindents the line to the indentation of the line above it.
    """
    def getReindentColumn(self, linenum, linestart, pos, indpos, col, indcol):
        # look at indention of previous line
        prevind, prevline = self.GetPrevLineIndentation(linenum)
        if (prevind < indcol and prevline < linenum-1) or prevline < linenum-2:
            # if there's blank lines before this and the previous
            # non-blank line is indented less than this one, ignore
            # it.  Make the user manually unindent lines.
            return None

        # previous line is not blank, so indent line to previous
        # line's level
        return prevind


class FoldingReindentMixin(object):
    """Experimental class to use STC Folding to reindent a line.
    
    Currently not supported.
    """
    def reindentLine(self, linenum=None, dedent_only=False):
        """Reindent the specified line to the correct level.

        Given a line, use Scintilla's built-in folding to determine
        the indention level of the current line.
        """
        if linenum is None:
            linenum = self.GetCurrentLine()
        linestart = self.PositionFromLine(linenum)

        # actual indention of current line
        ind = self.GetLineIndentation(linenum) # columns
        pos = self.GetLineIndentPosition(linenum) # absolute character position

        # folding says this should be the current indention
        fold = self.GetFoldLevel(linenum)&wx.stc.STC_FOLDLEVELNUMBERMASK - wx.stc.STC_FOLDLEVELBASE
        self.dprint("ind = %s (char num=%d), fold = %s" % (ind, pos, fold))
        self.SetTargetStart(linestart)
        self.SetTargetEnd(pos)
        self.ReplaceTarget(self.GetIndentString(fold))


class GenericFoldHierarchyMixin(object):
    """Mixin for the scintilla fold processing.
    
    Scintilla's folding code is used to generate the function lists in some
    major modes.  Scintilla doesn't support code folding in all its supported
    languages, so major modes that aren't supported may mimic this interface to
    provide similar functionality.
    
    This mixin depends on the FoldExplorerMixin in peppy.lib.foldexplorer
    """
    def OnFoldChanged(self, evt):
        """Callback to process fold events.
        
        This callback is initiated from within the event handler of PeppySTC.
        The events could be used to optimize the fold algorithm, but
        currently this data is not used by anything.
        """
        stc_class_info = self.getSharedClassInfo(self.__class__)
        if 'fold_hierarchy' in stc_class_info:
            #dprint("changed fold at line=%d, pos=%d" % (evt.Line, evt.Position))
            stc_class_info['fold_changed'].append(evt.Line)
    
    def getFoldHierarchy(self):
        """Get the current fold hierarchy, returning the existing copy if there
        are no changes, or updating if necessary.
        """
        stc_class_info = self.getSharedClassInfo(self.__class__)
        if 'fold_hierarchy' not in stc_class_info or stc_class_info['fold_changed'] or self.GetLineCount() != stc_class_info['fold_line_count']:
            #dprint("Fold hierarchy has changed.  Updating.")
            self.updateFoldHierarchy()
        fold_hier = stc_class_info['fold_hierarchy']
        return fold_hier

    def updateFoldHierarchy(self):
        """Create the fold hierarchy using Stani's fold explorer algorithm.
        """
        # FIXME: Turn this into a threaded operation if it takes too long
        t = time.time()
        self.Colourise(0, self.GetTextLength())
        self.dprint("Finished colourise: %0.5f" % (time.time() - t))
        
        # Note that different views of the same buffer *using the same major
        # mode* will have the same fold hierarchy.  So, we use the stc's
        # getSharedClassInfo interface to store data common to all views of
        # this buffer that use this major mode.
        stc_class_info = self.getSharedClassInfo(self.__class__)
        stc_class_info['fold_hierarchy'] = self.computeFoldHierarchy()
        stc_class_info['fold_changed'] = []
        
        # Note: folding events aren't fired when only blank lines are inserted
        # or deleted, so we keep track of the line count as a secondary method
        # to indicate the folding needs to be recalculated
        stc_class_info['fold_line_count'] = self.GetLineCount()
        
        return stc_class_info['fold_hierarchy']


class ParagraphInfo(object):
    """Summary object about the currently selected paragraph.
    
    This object is built up as the paragraph mixin is searching through the
    file looking for the boundaries of the paragraph.  It is then used as
    input to the paragraph fill and other commands.
    """
    def __init__(self, stc, linenum):
        """Initialize the structure by specifying a line that belongs to the
        paragraph.
        """
        self.s = stc
        self.cursor_linenum = linenum
        line = self.s.GetLine(linenum)
        self.leader_pattern, line, self.trailer = self.s.splitCommentLine(line)
        
        # The line list is maintained in reverse when searching backward,
        # then is reversed before being added to the final list
        self._startlines = [line]
        self._endlines = []
        self._lines = []
        
        # set initial region start and end positions
        self.start = self.s.PositionFromLine(linenum)
        self.end = self.s.GetLineEndPosition(linenum)
        
    def addStartLine(self, linenum, line):
        """Add the line to the list and update the starting position"""
        self._startlines.append(line)
        self.start = self.s.PositionFromLine(linenum)
        
    def addEndLine(self, linenum, line):
        """Add the line to the list and update the starting position"""
        self._endlines.append(line)
        self.end = self.s.GetLineEndPosition(linenum)
        
    def getLines(self):
        """Get the list of lines in the paragraph"""
        if not self._lines:
            # The starting lines are stored in reverse order for easy appending
            self._startlines.reverse()
            self._lines.extend(self._startlines)
            self._lines.extend(self._endlines)
        return self._lines


class StandardParagraphMixin(object):
    """Locate the start and end of a paragraph, given a point within it."""
    def findParagraphStart(self, linenum, info):
        """Check to see if a previous line should be included in the
        paragraph match.
        
        Routine designed to be overridden by subclasses to evaluate
        if a line should be included in the list of lines that belong with
        the current paragraph.
        
        Add the line to the ParagraphInfo class using addStartLine if it
        belongs.
        
        Return True if findParagraph should continue searching; otherwise
        return False
        """
        leader, line, trailer = self.splitCommentLine(self.GetLine(linenum))
        self.dprint(line)
        if leader != info.leader_pattern or len(line.strip())==0:
            return False
        info.addStartLine(linenum, line)
        return True
    
    def findParagraphEnd(self, linenum, info):
        """Check to see if a following line should be included in the
        paragraph match.
        
        Routine designed to be overridden by subclasses to evaluate
        if a line should be included in the list of lines that belong with
        the current paragraph.
        
        Add the line to the ParagraphInfo class using addEndLine if it belongs.
        
        Return True if findParagraph should continue searching; otherwise
        return False
        """
        leader, line, trailer = self.splitCommentLine(self.GetLine(linenum))
        self.dprint(line)
        if leader != info.leader_pattern or len(line.strip())==0:
            return False
        info.addEndLine(linenum, line)
        return True
        
    def findParagraph(self, start, end=-1):
        if end == -1:
            end = start
        linenum = self.LineFromPosition(start)
        info = ParagraphInfo(self, linenum)
        
        # find the start of the paragraph by searching backwards till the
        # prefix changes or we find a line with only whitespace in it
        while linenum > 0:
            linenum -= 1
            if not self.findParagraphStart(linenum, info):
                break
        
        endlinenum = self.LineFromPosition(end)
        if endlinenum > info.cursor_linenum:
            # find all the lines in the middle, doing the best to strip off any
            # leading comment chars from the line
            linenum = info.cursor_linenum
            while linenum < endlinenum:
                linenum += 1
                leader, line, trailer = self.splitCommentLine(self.GetLine(linenum))
                info.addEndLine(linenum, line)
                
        # Now, find the end of the paragraph by searching forward until the
        # comment prefix changes or we find only white space
        lastlinenum = self.GetLineCount()
        self.dprint("start=%d count=%d end=%d" % (info.cursor_linenum, lastlinenum, endlinenum))
        while endlinenum < lastlinenum:
            endlinenum += 1
            if not self.findParagraphEnd(endlinenum, info):
                break
        return info


class FundamentalSTC(EditraSTCMixin, PeppySTC):
    """Subclass of PeppySTC providing the Editra mixin
    
    Needed for the Editra styling dialog.  FIXME: perhaps move the editra stuff
    right into PeppySTC?
    """
    def __init__(self, parent, *args, **kwargs):
        PeppySTC.__init__(self, parent, *args, **kwargs)
        EditraSTCMixin.__init__(self, wx.GetApp().fonts.getStyleFile())


class FundamentalMode(BraceHighlightMixin, StandardReturnMixin,
                     StandardReindentMixin, StandardParagraphMixin,
                     GenericFoldHierarchyMixin, FoldExplorerMixin,
                     EditraSTCMixin, PeppySTC, MajorMode):
    """Major mode for editing generic text files.
    
    This is the most generic major mode used for editing text files.  This uses
    a L{PeppySTC} as the editing window, and is linked to a L{Buffer} object
    that in turn is linked to the backend storage of a L{PeppyBaseSTC}.
    
    All major modes that are edit text using an STC should be subclasses of
    this mode.  Major modes that provide editing windows that aren't an STC
    (like the HexEdit view or an image viewer) will not be subclasses of
    this mode; rather, they will be subclasses of L{MajorMode} and will only
    use an STC as the backend storage within the L{Buffer} attribute that is
    associated with every major mode.
    
    The STC uses the Editra system for styling text and fonts; it is based
    on matching the filename or extension with values from its database.
    Documentation on the Editra interface is forthcoming.
    
    C{FundamentalMode} is a subclass of L{PeppySTC}, so all of the STC methods
    are availble here for user interfacing.  In addition, some mixins are
    used, like the L{BraceHighlightMixin} to provide language customizable
    brace highlighting, and the L{StandardParagraphMixin} used to determine
    the start and end of a paragraph based on the major mode.
    
    Two mixins in particular will need attention when subclassing
    FundamentalMode for new types of text files: L{StandardReturnMixin} and
    L{StandardReindentMixin}.  The L{StandardReturnMixin} provides handling
    for the return key and indenting the following line to the correct tab
    stop.  The L{StandardReindentMixin} is used to indent a line to its proper
    column based on the language supported by the major mode.  FundamentalMode
    subclasses should override both of these classes and provide them as
    mixins in order to customize the major mode.
    
    Because the L{FundamentalMode} serves as the base class for all
    text editing modes, there are many defaults specified in the
    L{default_classprefs} class attribute.  These defaults are based on
    the L{ClassPrefs} metaclass that associates keywords with values and
    serializes them to the peppy configuration file.  ClassPrefs are a
    transparent way to handle the application preferences, and you'll find
    them used all over peppy.  But, as their name suggests, ClassPrefs belong
    to the class, not the instance, so this is not for instance variable
    storage.  See the L{ClassPrefs} documentation for more information.
    """
    debuglevel = 0
    
    keyword = 'Fundamental'
    
    #: If the editra file_type (defined as the LANG_* keywords in the editra source file peppy/editra/synglob.py) doesn't match the class attribute 'keyword', specify the editra file type here.  In other words, None here means that the editra file_type *does* match the keyword
    editra_synonym = None

    #: Default comment characters in case the Editra styling database doesn't have any information about the mode
    start_line_comment = ''
    end_line_comment = ''

    #: Default class preferences that relate to all instances of this major mode
    default_classprefs = (
        StrParam('editra_style_sheet', '', 'Mode specific filename in the config directory containing\nEditra style sheet information.  Used to override\ndefault styles with custom styles for this mode.'),
        BoolParam('use_tab_characters', False,
                  'True: insert tab characters when tab is pressed\nFalse: insert the equivalent number of spaces instead.'),
        IntParam('tab_size', 4, 'Number of spaces in each tab'),
        IndexChoiceParam('tab_highlight_style',
                         ['ignore', 'inconsistent', 'mixed', 'spaces are bad', 'tabs are bad'],
                         4, 'Highlight bad intentation'),
        BoolParam('line_numbers', True, 'Show line numbers in the margin?'),
        IntParam('line_number_margin_width', 40, 'Margin width in pixels'),
        BoolParam('symbols', False, 'Show symbols margin'),
        IntParam('symbols_margin_width', 16, 'Symbols margin width in pixels'),
        BoolParam('folding', False, 'Show the code folding margin?'),
        IntParam('folding_margin_width', 16, 'Code folding margin width in pixels'),
        BoolParam('wrapping', False, 'True: use line wrapping\nFalse: show horizontal scrollbars'),
        BoolParam('word_wrap', False, 'True: wrap lines at word boundries\nFalse: wrap at right margin'),
        BoolParam('backspace_unindents', True),
        BoolParam('indentation_guides', True, 'Show indentation guides at multiples of the tab_size'),
        IntParam('highlight_column', 30, 'Column at which to highlight the indention guide.\nNote: uses the BRACELIGHT color to highlight'),
        IntParam('edge_column', 80, 'Column at which to show the edge (i.e. long line) indicator'),
        KeyedIndexChoiceParam('edge_indicator',
                              [(wx.stc.STC_EDGE_NONE, 'none'),
                               (wx.stc.STC_EDGE_LINE, 'line'),
                               (wx.stc.STC_EDGE_BACKGROUND, 'background'),
                               ], 'line', help='Long line indication mode'),
        IntParam('caret_blink_rate', 0, help='Blink rate in milliseconds\nor 0 to stop blinking'),
        IntParam('caret_width', 2, help='Caret width in pixels'),
        BoolParam('caret_line_highlight', False, help='Highlight the line containing the cursor?'),
        BoolParam('view_eol', False, 'Show line-ending cr/lf characters?'),
        )
    
    def __init__(self, parent, wrapper, buffer, frame):
        """Create the STC and apply styling settings.

        Everything that subclasses from FundamentalMode will use an
        STC instance for displaying the user interaction window.
        """
        MajorMode.__init__(self, parent, wrapper, buffer, frame)
        start = time.time()
        self.dprint("starting PeppySTC at %0.5fs" % start)
        PeppySTC.__init__(self, parent, refstc=self.buffer.stc)
        self.dprint("PeppySTC done in %0.5fs" % (time.time() - start))
        EditraSTCMixin.__init__(self, wx.GetApp().fonts.getStyleFile())
        self.dprint("EditraSTCMixin done in %0.5fs" % (time.time() - start))
        self.applySettings()
        self.dprint("applySettings done in %0.5fs" % (time.time() - start))

    @classmethod
    def verifyEditraType(cls, ext, file_type):
        cls.dprint("ext=%s file_type=%s" % (ext, file_type))
        if file_type is None:
            # Not recognized at all by Editra.
            return False
        
        # file_type is a human readable string given in peppy.editra.synglob.py
        # If file_type is the same as the major mode keyword or an alias,
        # mark this as a specific match.
        if file_type == cls.keyword or file_type == cls.editra_synonym:
            cls.dprint("Specific match of %s" % file_type)
            return ext
        
        # Otherwise, if the file type is recognized but not specific to this
        # mode, mark it as generic.
        cls.dprint("generic match of %s" % file_type)
        return "generic"
    
    @classmethod
    def verifyMimetype(cls, mimetype):
        """Verify that the mimetype is text/plain.
        
        The class attribute mimetype is not used so that subclasses that extend
        Fundamental but forget to declare a MIME type won't also get added to
        the list of modes that handle text/plain.
        
        This default implementation will call L{MajorMode.verifyMimetype} if not
        overridden by the subclass.
        """
        # check for the class here so that subclasses don't automatically also
        # get associated with text/plain
        if cls == FundamentalMode:
            return mimetype == 'text/plain'
        else:
            return MajorMode.verifyMimetype(mimetype)
    
    def createStatusIcons(self):
        linesep = self.getLinesep()
        if linesep == '\r\n':
            self.statusbar.addIcon("icons/windows.png", "DOS/Windows line endings")
        elif linesep == '\r':
            self.statusbar.addIcon("icons/apple.png", "Old-style Apple line endings")
        else:
            self.statusbar.addIcon("icons/tux.png", "Unix line endings")

    def applySettings(self):
        start = time.time()
        self.dprint("starting applySettings at %0.5fs" % start)
        self.applyDefaultSettings()
        #dprint("applyDefaultSettings done in %0.5fs" % (time.time() - start))
        
        ext, file_type = MajorModeMatcherDriver.getEditraType(self.buffer.url)
        self.dprint("ext=%s file_type=%s" % (ext, file_type))
        if file_type == 'generic' or file_type is None:
            if self.editra_synonym is not None:
                file_type = self.editra_synonym
            elif self.keyword is not 'Fundamental':
                file_type = self.keyword
            else:
                file_type = ext
        self.editra_lang = file_type
        self.dprint("ext=%s file_type=%s" % (ext, file_type))
        self.SetStyleFont(wx.GetApp().fonts.classprefs.primary_editing_font)
        self.SetStyleFont(wx.GetApp().fonts.classprefs.secondary_editing_font, False)
        self.ConfigureLexer(self.editra_lang)
        self.dprint("styleSTC (if True) done in %0.5fs" % (time.time() - start))
        self.has_stc_styling = True
        self.dprint("applySettings returning in %0.5fs" % (time.time() - start))
    
    def applyDefaultSettings(self):
        # turn off symbol margin
        if self.classprefs.symbols:
            self.SetMarginWidth(1, self.classprefs.symbols_margin_width)
        else:
            self.SetMarginWidth(1, 0)

        # turn off folding margin
        if self.classprefs.folding:
            self.SetMarginWidth(2, self.classprefs.folding_margin_width)
        else:
            self.SetMarginWidth(2, 0)

        self.SetProperty("fold", "1")
        self.SetBackSpaceUnIndents(self.classprefs.backspace_unindents)
        self.SetIndentationGuides(self.classprefs.indentation_guides)
        self.SetHighlightGuide(self.classprefs.highlight_column)

        self.setWordWrap()
        self.setLineNumbers()
        self.setFolding()
        self.setTabStyle()
        self.setEdgeStyle()
        self.setCaretStyle()
        self.setViewEOL()

    def setWordWrap(self, enable=None, style=None):
        if enable is not None:
            self.classprefs.wrapping = enable
        if style is not None:
            self.classprefs.word_wrap = style
        if self.classprefs.wrapping:
            if self.classprefs.word_wrap:
                self.SetWrapMode(wx.stc.STC_WRAP_WORD)
            else:
                self.SetWrapMode(wx.stc.STC_WRAP_CHAR)
            self.SetWrapVisualFlags(wx.stc.STC_WRAPVISUALFLAG_END)
        else:
            self.SetWrapMode(wx.stc.STC_WRAP_NONE)

    def setLineNumbers(self,enable=None):
        if enable is not None:
            self.classprefs.line_numbers=enable
        if self.classprefs.line_numbers:
            self.SetMarginType(0, wx.stc.STC_MARGIN_NUMBER)
            self.SetMarginWidth(0,  self.classprefs.line_number_margin_width)
        else:
            self.SetMarginWidth(0,0)

    def setFolding(self,enable=None):
        if enable is not None:
            self.classprefs.folding=enable
        if self.classprefs.folding:
            self.SetMarginType(2, wx.stc.STC_MARGIN_SYMBOL)
            self.SetMarginMask(2, wx.stc.STC_MASK_FOLDERS)
            self.SetMarginSensitive(2, True)
            self.SetMarginWidth(2, self.classprefs.folding_margin_width)
            # Marker definitions from PyPE
            self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDEREND,     wx.stc.STC_MARK_BOXPLUSCONNECTED,  "white", "black")
            self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDEROPENMID, wx.stc.STC_MARK_BOXMINUSCONNECTED, "white", "black")
            self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDERMIDTAIL, wx.stc.STC_MARK_TCORNER,  "white", "black")
            self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDERTAIL,    wx.stc.STC_MARK_LCORNER,  "white", "black")
            self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDERSUB,     wx.stc.STC_MARK_VLINE,    "white", "black")
            self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDER,        wx.stc.STC_MARK_BOXPLUS,  "white", "black")
            self.MarkerDefine(wx.stc.STC_MARKNUM_FOLDEROPEN,    wx.stc.STC_MARK_BOXMINUS, "white", "black")
            self.Bind(wx.stc.EVT_STC_MARGINCLICK, self.onMarginClick)
        else:
            self.SetMarginWidth(2, 0)
            self.Unbind(wx.stc.EVT_STC_MARGINCLICK)

    def setTabStyle(self):
        self.SetIndent(self.classprefs.tab_size)
        self.SetProperty('tab.timmy.whinge.level', str(self.classprefs.tab_highlight_style))
        self.SetUseTabs(self.classprefs.use_tab_characters)

    def setEdgeStyle(self):
        self.SetEdgeMode(self.classprefs.edge_indicator)
        if self.classprefs.edge_indicator == wx.stc.STC_EDGE_NONE:
            self.SetEdgeColumn(0)
        else:
            self.SetEdgeColumn(self.classprefs.edge_column)

    def setCaretStyle(self):
        self.SetCaretPeriod(self.classprefs.caret_blink_rate)
        self.SetCaretLineVisible(self.classprefs.caret_line_highlight)
        self.SetCaretWidth(self.classprefs.caret_width)

    def setViewEOL(self, enable=None):
        if enable is not None:
            self.classprefs.view_eol = enable
        self.SetViewEOL(self.classprefs.view_eol)

    def onMarginClick(self, evt):
        # fold and unfold as needed
        if evt.GetMargin() == 2:
            if evt.GetShift() and evt.GetControl():
                self.FoldAll()
            else:
                lineClicked = self.LineFromPosition(evt.GetPosition())
                if self.GetFoldLevel(lineClicked) & wx.stc.STC_FOLDLEVELHEADERFLAG:
                    if evt.GetShift():
                        self.SetFoldExpanded(lineClicked, True)
                        self.Expand(lineClicked, True, True, 1)
                    elif evt.GetControl():
                        if self.GetFoldExpanded(lineClicked):
                            self.SetFoldExpanded(lineClicked, False)
                            self.Expand(lineClicked, False, True, 0)
                        else:
                            self.SetFoldExpanded(lineClicked, True)
                            self.Expand(lineClicked, True, True, 100)
                    else:
                        self.ToggleFold(lineClicked)

    def OnUpdateUI(self, evt):
        """Specific OnUpdateUI callback for those modes that use an actual
        STC for their edit window.
        
        Adds things like fold level and style display.
        """
        self.braceHighlight()
        assert self.dprint("OnUpdateUI for view %s, frame %s" % (self.keyword,self.frame))
        linenum = self.GetCurrentLine()
        pos = self.GetCurrentPos()
        col = self.GetColumn(pos)
        self.frame.SetStatusText("L%d C%d F%d S%d %d" % (linenum+self.classprefs.line_number_offset,
            col+self.classprefs.column_number_offset,
            self.GetFoldLevel(linenum)&wx.stc.STC_FOLDLEVELNUMBERMASK - wx.stc.STC_FOLDLEVELBASE,
            self.GetStyleAt(pos), pos),1)
        self.idle_update_menu = True
        self.OnUpdateUIHook(evt)
        if evt is not None:
            evt.Skip()

    def showInitialPosition(self, url):
        if url.fragment:
            line = int(url.fragment)
            line -= self.classprefs.line_number_offset
            self.GotoLine(line)
            self.EnsureVisible(line)
