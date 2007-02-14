# peppy Copyright (c) 2006-2007 Rob McMullen
# Licenced under the GPL; see http://www.flipturn.org/peppy for more info
"""
Python major mode.
"""

import os,struct
import keyword
from cStringIO import StringIO

import wx
import wx.stc as stc

from peppy import *
from peppy.menu import *
from peppy.major import *
from peppy.fundamental import FundamentalMode

from peppy.plugins.about import SetAbout

SetAbout('sample.dot','digraph G {Hello->World}')


class SampleDot(SelectAction):
    name = "&Open Sample Graphviz dot file"
    tooltip = "Open a sample Graphviz file"
    icon = wx.ART_FILE_OPEN

    def action(self, pos=-1):
        self.dprint("id=%x name=%s pos=%s" % (id(self),self.name,str(pos)))
        self.frame.open("about:sample.dot")

if wx.Platform == '__WXMSW__':
    faces = { 'times': 'Times New Roman',
              'mono' : 'Courier New',
              'helv' : 'Arial',
              'other': 'Comic Sans MS',
              'size' : 10,
              'size2': 8,
             }
else:
    faces = { 'times': 'Times',
              'mono' : 'Courier',
              'helv' : 'Helvetica',
              'other': 'new century schoolbook',
              'size' : 10,
              'size2': 8,
             }



class GraphvizMode(FundamentalMode):
    keyword='Graphviz'
    icon='icons/graphviz.ico'
    regex="\.dot$"
    lexer=stc.STC_LEX_CPP

    def getKeyWords(self):
        return [(0,"strict graph digraph graph node edge subgraph")]
    
    def styleSTC(self):
        self.format=os.linesep
        
        s=self.stc

        face1 = 'Arial'
        face2 = 'Times New Roman'
        face3 = 'Courier New'
        pb = 10

        # Show mixed tabs/spaces
        s.SetProperty("tab.timmy.whinge.level", "1")
        
        # Global default styles for all languages
        s.StyleSetSpec(stc.STC_STYLE_DEFAULT,     "face:%(mono)s,size:%(size)d" % faces)
        s.StyleClearAll()  # Reset all to be like the default

        # Global default styles for all languages
        s.StyleSetSpec(stc.STC_STYLE_DEFAULT,     "face:%(mono)s,size:%(size)d" % faces)
        s.StyleSetSpec(stc.STC_STYLE_LINENUMBER,  "back:#C0C0C0,face:%(mono)s,size:%(size2)d" % faces)
        s.StyleSetSpec(stc.STC_STYLE_CONTROLCHAR, "face:%(other)s" % faces)
        s.StyleSetSpec(stc.STC_STYLE_BRACELIGHT,  "fore:#FFFFFF,back:#0000FF,bold")
        s.StyleSetSpec(stc.STC_STYLE_BRACEBAD,    "fore:#000000,back:#FF0000,bold")

        # Python styles
        # Default 
        s.StyleSetSpec(stc.STC_P_DEFAULT, "fore:#000000,face:%(mono)s,size:%(size)d" % faces)
        # Comments
        s.StyleSetSpec(stc.STC_P_COMMENTLINE, "fore:#007F00,face:%(mono)s,size:%(size)d" % faces)
        # Number
        s.StyleSetSpec(stc.STC_P_NUMBER, "fore:#007F7F,size:%(size)d" % faces)
        # String
        s.StyleSetSpec(stc.STC_P_STRING, "fore:#7F007F,face:%(mono)s,size:%(size)d" % faces)
        # Single quoted string
        s.StyleSetSpec(stc.STC_P_CHARACTER, "fore:#7F007F,face:%(mono)s,size:%(size)d" % faces)
        # Keyword
        s.StyleSetSpec(stc.STC_P_WORD, "fore:#00007F,bold,size:%(size)d" % faces)
        # Triple quotes
        s.StyleSetSpec(stc.STC_P_TRIPLE, "fore:#7F0000,size:%(size)d" % faces)
        # Triple double quotes
        s.StyleSetSpec(stc.STC_P_TRIPLEDOUBLE, "fore:#7F0000,size:%(size)d" % faces)
        # Class name definition
        s.StyleSetSpec(stc.STC_P_CLASSNAME, "fore:#0000FF,bold,underline,size:%(size)d" % faces)
        # Function or method name definition
        s.StyleSetSpec(stc.STC_P_DEFNAME, "fore:#007F7F,bold,size:%(size)d" % faces)
        # Operators
        s.StyleSetSpec(stc.STC_P_OPERATOR, "bold,size:%(size)d" % faces)
        # Identifiers
        s.StyleSetSpec(stc.STC_P_IDENTIFIER, "fore:#000000,face:%(mono)s,size:%(size)d" % faces)
        # Comment-blocks
        s.StyleSetSpec(stc.STC_P_COMMENTBLOCK, "fore:#7F7F7F,face:%(mono)s,size:%(size)d" % faces)
        # End of line where string is not closed
        s.StyleSetSpec(stc.STC_P_STRINGEOL, "fore:#000000,face:%(mono)s,back:#E0C0E0,eol,size:%(size)d" % faces)



class BitmapScroller(wx.ScrolledWindow):
    def __init__(self, parent):
        wx.ScrolledWindow.__init__(self, parent, -1)

        self.bmp = None
        
        self.Bind(wx.EVT_PAINT, self.OnPaint)

    def setBitmap(self, bmp):
        self.bmp = bmp
        if bmp is not None:
            self.SetVirtualSize((bmp.GetWidth(), bmp.GetHeight()))
        else:
            self.SetVirtualSize(10,10)
        self.SetScrollRate(1,1)

    def OnPaint(self, ev):
        if self.bmp is not None:
            dc=wx.BufferedPaintDC(self, self.bmp, wx.BUFFER_VIRTUAL_AREA)
        # Apparently the drawing actually happens when the dc goes out
        # of scope and is destroyed.  Dunno if I would have figured
        # that out on my own, so thankfully the python demo was
        # commented.

class GraphvizViewCtrl(wx.Panel):
    """Viewer that calls graphviz to generate an image.

    Call graphviz to generate an image and display it.
    """

    def __init__(self, parent, minor):
        wx.Panel.__init__(self, parent)
        self.minor = minor

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self.sizer)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.dotprogs = ['neato', 'dot', 'twopi', 'circo', 'fdp', 'nop']
        self.prog = wx.Choice(self, -1, (100, 50), choices = self.dotprogs)
        self.prog.SetSelection(0)
        buttons.Add(self.prog, 1, wx.EXPAND)
        
        self.regen = wx.Button(self, -1, "Regenerate")
        self.regen.Bind(wx.EVT_BUTTON, self.OnRegenerate)
        buttons.Add(self.regen, 1, wx.EXPAND)

        self.sizer.Add(buttons)

        self.preview = None
        self.bmp = None
        #self.drawing = wx.Window(self, -1)
        #self.drawing.Bind(wx.EVT_PAINT, self.OnPaint)
        self.drawing = BitmapScroller(self)
        self.sizer.Add(self.drawing, 1, wx.EXPAND)

        self.process = None
        self.Bind(wx.EVT_IDLE, self.OnIdle)
        self.Bind(wx.EVT_END_PROCESS, self.OnProcessEnded)

        self.Layout()

        self.Bind(wx.EVT_SIZE, self.OnSize)

    def __del__(self):
        if self.process is not None:
            self.process.Detach()
            self.process.CloseOutput()
            self.process = None

    def OnRegenerate(self, event):
        prog = os.path.normpath(os.path.join(self.minor.settings.path,self.prog.GetStringSelection()))
        dprint("using %s to run graphviz" % repr(prog))

        cmd = "%s -Tpng" % prog
        
        self.process = wx.Process(self)
        self.process.Redirect();
        pid = wx.Execute(cmd, wx.EXEC_ASYNC, self.process)
        if pid==0:
            self.minor.major.frame.SetStatusText("Couldn't run %s" % cmd)
        else:
            self.minor.major.frame.SetStatusText("Running %s with pid=%d" % (cmd, pid))
            self.regen.Enable(False)

            self.preview = StringIO()
            
            #print "text = %s" % self.minor.major.buffer.stc.GetText()
            text = self.minor.major.buffer.stc.GetText()
            size = len(text)
            fh = self.process.GetOutputStream()
            dprint("sending text size=%d to %s" % (size,fh))
            if size > 1000:
                for i in range(0,size,1000):
                    last = i+1000
                    if last>size:
                        last=size
                    dprint("sending text[%d:%d] to %s" % (i,last,fh))
                    fh.write(text[i:last])
                    dprint("last write = %s" % str(fh.LastWrite()))
            else:
                fh.write(self.minor.major.buffer.stc.GetText())
            self.process.CloseOutput()

    def readStream(self):
        stream = self.process.GetInputStream()

        if stream.CanRead():
            text = stream.read()
            self.preview.write(text)

    def OnIdle(self, evt):
        if self.process is not None:
            self.readStream()

    def OnProcessEnded(self, evt):
        dprint("here.")
        self.readStream()
        self.process.Destroy()
        self.process = None
        self.regen.Enable(True)
        self.createImage()
        self.Refresh()

    def createImage(self):
        dprint("using image, size=%s" % len(self.preview.getvalue()))
        if len(self.preview.getvalue())==0:
            self.minor.major.frame.SetStatusText("Error running graphviz!")
            return
        
##        fh = open("test.png",'wb')
##        fh.write(self.preview.getvalue())
##        fh.close()
        fh = StringIO(self.preview.getvalue())
        img = wx.EmptyImage()
        if img.LoadStream(fh):
            self.bmp = wx.BitmapFromImage(img)
        else:
            self.bmp = None
            self.minor.major.frame.SetStatusText("Invalid image")
        self.drawing.setBitmap(self.bmp)

    def OnPaint(self, event):
        dc = wx.PaintDC(self.drawing)
        if self.bmp is not None:
            dc.DrawBitmap(self.bmp, 0, 0, True)
        else:
            size = self.drawing.GetClientSize()
            s = ("Size: %d x %d")%(size.x, size.y)
            dc.SetFont(wx.NORMAL_FONT)
            w, height = dc.GetTextExtent(s)
            height = height + 3
            dc.SetBrush(wx.WHITE_BRUSH)
            dc.SetPen(wx.WHITE_PEN)
            dc.DrawRectangle(0, 0, size.x, size.y)
            dc.SetPen(wx.LIGHT_GREY_PEN)
            dc.DrawLine(0, 0, size.x, size.y)
            dc.DrawLine(0, size.y, size.x, 0)
            dc.DrawText(s, (size.x-w)/2, ((size.y-(height*5))/2))

    def OnSize(self, event):
        self.Refresh()
        event.Skip()
        

class GraphvizViewMinorMode(MinorMode):
    keyword="GraphvizView"
    defaults={'path':'/usr/bin'}

    def createWindows(self, parent):
        if self.settings.path is None:
            self.settings.path = GraphvizViewMinorMode.defaults['path']
        self.sizerep=GraphvizViewCtrl(parent,self)
        paneinfo=self.getDefaultPaneInfo("Graphviz View")
        paneinfo.Right()
        self.major.addPane(self.sizerep,paneinfo)
        


class GraphvizPlugin(MajorModeMatcherBase,debugmixin):
    implements(IMajorModeMatcher)
    implements(IMinorModeProvider)
    implements(IMenuItemProvider)

    def scanEmacs(self,emacsmode,vars):
        if emacsmode in ['graphviz',GraphvizMode.keyword]:
            return MajorModeMatch(GraphvizMode,exact=True)
        return None

    def scanShell(self,bangpath):
        if bangpath.find('dot')>-1:
            return MajorModeMatch(GraphvizMode,exact=True)
        return None

    def scanFilename(self,filename):
        if filename.endswith('.dot'):
            return MajorModeMatch(GraphvizMode,exact=True)
        return None

    def getMinorModes(self):
        yield GraphvizViewMinorMode    
    
    default_menu=((None,None,Menu("Test").after("Minor Mode")),
                  (None,"Test",MenuItem(SampleDot)),
                  )
    def getMenuItems(self):
        for mode,menu,item in self.default_menu:
            yield (mode,menu,item)

