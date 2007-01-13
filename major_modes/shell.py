import os,re

import wx
import wx.stc as stc
import wx.lib.newevent

from cStringIO import StringIO

from trac.core import *
from plugin import *
from debug import *
from major_modes.fundamental import FundamentalMode
from stcinterface import MySTC
from menudev import FrameAction

class ShellPipePlugin(Interface):
    """
    Interface for shells that take a line of input and return a response.
    """

    def supportedShells():
        """
        Return a list of shells that this interface supports, e.g. a
        bash shell should return ['bash'] or python should return
        ['python'].
        """
        
    def getPipe(filename):
        """
        Return a file-like object that is the interface to the shell.
        Typically this will act like a pipe to an object: stuff that
        is written to this file handle will get sent through the pipe
        to the shell, and when data is available it can be read from
        this object.
        """

class ShellProtocol(ProtocolPluginBase,debugmixin):
    implements(ProtocolPlugin)
    
    shells=ExtensionPoint(ShellPipePlugin)

    def supportedProtocols(self):
        return ['shell']
    
    def getReader(self,urlinfo):
        self.dprint("getReader: trying to open %s" % urlinfo.path)
        for shell in self.shells:
            if urlinfo.path in shell.supportedShells():
                fh=shell.getPipe(urlinfo.path)
                return fh
        raise IOError

    def getWriter(self,urlinfo):
        return self.getReader(urlinfo)

    def getSTC(self,parent):
        return ShellSTC(parent)
    


# This creates a new Event class and a EVT binder function used when
# new shell when new data is available to be read.
(ShellUpdateEvent, EVT_SHELL_UPDATE) = wx.lib.newevent.NewEvent()


class ShellSTC(MySTC):
    debuglevel=1

    def __init__(self, parent, ID=-1):
        MySTC.__init__(self,parent,ID)
        self.pipe=None
        self.waiting=False
        self.promptPosEnd=0
        self.filter=1
        self.more=0

    def openPostHook(self,filter):
        self.dprint("in ShellSTC")
        self.pipe=filter.fh
        self.pipe.setNotifyWindow(self)
        self.Bind(EVT_SHELL_UPDATE,self.OnReadable)
        
        length=self.GetTextLength()
        self.SetCurrentPos(length)
        self.AddText('\n')
        self.prompt()

    def prompt(self):
        if self.filter:
            skip = False
            if self.more:
                prompt = self.pipe.ps2
            else:
                prompt = self.pipe.ps1
            pos = self.GetCurLine()[1]
            if pos > 0:
                self.AddText('\n')
            if not self.more:
                self.promptPosEnd = self.GetCurrentPos()
            if not skip:
                self.AddText(prompt)
        if not self.more:
            self.promptPosEnd = self.GetCurrentPos()
            # Keep the undo feature from undoing previous responses.
            self.EmptyUndoBuffer()

    def send(self,cmd):
        self.pipe.write(cmd)
        self.waiting=True

    def OnReadable(self,evt=None):
        text=self.pipe.read()
        if len(text)>0:
            text=text.rstrip('\n\r')
            self.AddText(text)
            self.AddText('\n')
            self.prompt()
            self.waiting=False
            # Send ShellUpdate event to viewer STCs to tell them to
            # update their cursor positions.
            self.sendEvents(ShellUpdateEvent)

    def process(self,viewer):
        startpos = self.promptPosEnd
        endpos = self.GetTextLength()
        
        tosend = self.GetTextRange(startpos, endpos) + '\n'
        
        self.SetCurrentPos(endpos)
        self.AddText('\n')
        self.promptPosEnd = endpos + 1
        self.SetCurrentPos(self.promptPosEnd)
        self.send(tosend)
        

    def OnModified(self, evt):
        MySTC.OnModified(self,evt)


class ProcessShellLine(FrameAction):
    name = "Process a shell command"
    tooltip = "Process a shell command."
    keyboard = 'RET'

    def action(self, state=None, pos=-1):
        self.dprint("id=%x name=%s pos=%s" % (id(self),self.name,str(pos)))
        viewer=self.frame.getCurrentViewer()
        if viewer:
            viewer.buffer.stc.process(viewer)

class ShellMode(FundamentalMode):
    debuglevel=0
    
    icon='icons/application_xp_terminal.png'
    regex="shell:.*$"

    defaultsettings={
        'keyboard_actions':[
            ProcessShellLine,
            ]
        }
    
    def openPostHook(self):
        self.dprint("In shell.")
        self.stc.Bind(stc.EVT_STC_MODIFIED, self.OnUpdate)

        #Use an event listener to update the cursor position when the
        #underlying shell has changed.
        self.stc.Bind(EVT_SHELL_UPDATE, self.OnUpdateCursorPos)
        self.OnUpdateCursorPos()

    def OnUpdateCursorPos(self,evt=None):
        self.stc.GotoPos(self.buffer.stc.GetCurrentPos())
        self.stc.EnsureCaretVisible()
        self.stc.ScrollToColumn(0)

    def OnUpdate(self,evt=None):
        self.dprint("Updated!")
        


class ShellPlugin(MajorModeMatcherBase,debugmixin):
    implements(IMajorModeMatcher)
    
    def scanFilename(self,filename):
        match=re.search(ShellMode.regex,filename)
        if match:
            return MajorModeMatch(ShellMode,exact=True)
        return None
