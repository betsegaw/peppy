# peppy Copyright (c) 2006-2007 Rob McMullen
# Licenced under the GPL; see http://www.flipturn.org/peppy for more info
import os, re, threading
from cStringIO import StringIO

import wx
import wx.aui
import wx.stc

from menu import *
from lib.iconstorage import *
from lib.controls import *
from lib.userparams import *

from stcinterface import *
from iofilter import *
from major import *
from debug import *

class BufferList(GlobalList):
    debuglevel = 0
    name = "Buffers"

    storage = []
    others = []

    @classmethod
    def addBuffer(self, buffer):
        BufferList.append(buffer)

    @classmethod
    def removeBuffer(self, buffer):
        BufferList.remove(buffer)

    @classmethod
    def findBufferByURL(self, url):
        if not isinstance(url, URLInfo):
            url = URLInfo(url)
        for buf in BufferList.storage:
            if buf.isURL(url):
                return buf
        return None

    @staticmethod
    def promptUnsaved(msg):
        unsaved=[]
        for buf in BufferList.storage:
            if buf.modified and not buf.permanent:
                unsaved.append(buf)
        if len(unsaved)>0:
            dlg = QuitDialog(wx.GetApp().GetTopWindow(), unsaved)
            retval=dlg.ShowModal()
            dlg.Destroy()
        else:
            retval=wx.ID_OK

        if retval==wx.ID_OK:
            Publisher().sendMessage('peppy.app.quit')
            
    def getItems(self):
        return [buf.name for buf in BufferList.storage]

    def action(self,state=None,index=0):
        assert self.dprint("top window to %d: %s" % (index,BufferList.storage[index]))
        self.frame.setBuffer(BufferList.storage[index])

Publisher.subscribe(BufferList.promptUnsaved, 'peppy.request.quit')

    

#### Buffers

class Buffer(debugmixin):
    count=0
    debuglevel=0

    filenames={}
    
    dummyframe = None
    
    @classmethod
    def initDummyFrame(cls):
        # the Buffer objects have an stc as the base, and they need a
        # frame in which to work.  So, we create a dummy frame here
        # that is never shown.
        Buffer.dummyframe=wx.Frame(None)
        Buffer.dummyframe.Show(False)

    @classmethod
    def loadPermanent(cls, url):
        buffer = cls(url)
        buffer.open()
        buffer.permanent = True
        BufferList.addBuffer(buffer)

    def __init__(self, url, defaultmode=None):
        if Buffer.dummyframe is None:
            Buffer.initDummyFrame()

        self.busy = False
        self.readonly = False
        self.defaultmode=defaultmode

        self.guessBinary=False
        self.guessLength=1024
        self.guessPercentage=10

        self.viewer=None
        self.viewers=[]

        self.modified=False
        self.permanent = False

        self.stc=None

        self.setURL(url)
        #self.open(url, stcparent)

    def __del__(self):
        dprint("cleaning up buffer %s" % self.url)

    def initSTC(self):
        self.stc.Bind(wx.stc.EVT_STC_CHANGE, self.OnChanged)

    def addViewer(self, mode):
        self.viewers.append(mode) # keep track of views
        assert self.dprint("views of %s: %s" % (self,self.viewers))

    def removeViewer(self,view):
        assert self.dprint("removing view %s of %s" % (view,self))
        if view in self.viewers:
            self.viewers.remove(view)
            if issubclass(view.stc.__class__, PeppySTC) and view.stc != self.stc:
                self.stc.removeSubordinate(view.stc)
        else:
            raise ValueError("Bug somewhere.  Major mode %s not found in Buffer %s" % (view,self))
        assert self.dprint("views remaining of %s: %s" % (self,self.viewers))

    def removeAllViewsAndDelete(self):
        # Have to make a copy of self.viewers, because when the viewer
        # closes itself, it removes itself from this list of viewers,
        # so unless you make a copy the for statement is operating on
        # a changing list.
        viewers=self.viewers[:]
        for viewer in viewers:
            assert self.dprint("count=%d" % len(self.viewers))
            assert self.dprint("removing view %s of %s" % (viewer,self))
            viewer.frame.tabs.closeTab(viewer)
        assert self.dprint("final count=%d" % len(self.viewers))

        if not self.permanent:
            BufferList.remove(self)
            # Need to destroy the base STC or self will never get garbage
            # collected
            self.stc.Destroy()
            dprint("removed buffer %s" % self.url)

    def setURL(self, url):
        if not url:
            url=URLInfo("file://untitled")
        elif not isinstance(url, URLInfo):
            url = URLInfo(url)
        self.url = url

    def isURL(self, url):
        if not isinstance(url, URLInfo):
            url = URLInfo(url)
        if url == self.url:
            return True
        return False

    def setName(self):
        basename=self.url.getBasename()
        if basename in self.filenames:
            count=self.filenames[basename]+1
            self.filenames[basename]=count
            self.displayname=basename+"<%d>"%count
        else:
            self.filenames[basename]=1
            self.displayname=basename
        self.name="Buffer #%d: %s" % (self.count,str(self.url))

        # Update UI because the filename associated with this buffer
        # may have changed and that needs to be reflected in the menu.
        BufferList.update()
        
    def getFilename(self):
        return self.url.path

    def cwd(self):
        if self.url.protocol == 'file':
            path = os.path.normpath(os.path.dirname(self.url.path))
        else:
            path = os.getcwd()
        return path
            
    def getTabName(self):
        if self.modified:
            return "*"+self.displayname
        return self.displayname

    def openGUIThreadStart(self):
        self.dprint("url: %s" % repr(self.url))
        if self.defaultmode is None:
            self.defaultmode = MajorModeMatcherDriver.match(self.url)
        self.dprint("mode=%s" % (str(self.defaultmode)))

        self.stc = self.defaultmode.stc_class(self.dummyframe)

    def openBackgroundThread(self, progress_message=None):
        self.stc.open(self.url, progress_message)

    def openGUIThreadSuccess(self):
        # Only increment count on successful buffer loads
        Buffer.count+=1
        
        self.setName()

        if isinstance(self.stc,PeppySTC):
            self.initSTC()

        self.modified = False
        self.readonly = self.url.readonly()
        self.stc.EmptyUndoBuffer()

        # Send a message to any interested plugins that a new buffer
        # has been successfully opened.
        Publisher().sendMessage('buffer.opened', self)

    def open(self):
        self.openGUIThreadStart()
        self.openBackgroundThread()
        self.openGUIThreadSuccess()

    def revert(self):
        # don't use the buffered reader: get a new file handle
        fh=self.url.getDirectReader()
        self.stc.ClearAll()
        self.stc.readFrom(fh)
        self.modified=False
        self.stc.EmptyUndoBuffer()
        wx.CallAfter(self.showModifiedAll)  
        
    def save(self, url=None):
        assert self.dprint("Buffer: saving buffer %s" % (self.url))
        try:
            if url is None:
                saveas=self.url
            else:
                saveas=URLInfo(url)
            fh=saveas.getWriter()
            self.stc.writeTo(fh)
            fh.close()
            self.stc.SetSavePoint()
            if url is not None and url!=self.url:
                self.setURL(saveas)
                self.setName()
            self.modified = False
            self.readonly = self.url.readonly()
            self.showModifiedAll()
        except:
            eprint("Failed writing to %s" % self.url)
            raise

    def showModifiedAll(self):
        for view in self.viewers:
            assert self.dprint("notifing: %s modified = %s" % (view, self.modified))
            view.showModified(self.modified)
        wx.GetApp().enableFrames()

    def setBusy(self, state):
        self.busy = state
        for view in self.viewers:
            assert self.dprint("notifing: %s busy = %s" % (view, self.busy))
            view.showBusy(self.busy)
        wx.GetApp().enableFrames()

    def OnChanged(self, evt):
        if self.stc.GetModify():
            assert self.dprint("modified!")
            changed=True
        else:
            assert self.dprint("clean!")
            changed=False
        if changed!=self.modified:
            self.modified=changed
            wx.CallAfter(self.showModifiedAll)


class BlankMode(MajorMode):
    """
    A temporary Major Mode to load another mode in the background
    """
    keyword = "about:blank"
    icon='icons/application.png'
    temporary = True
    allow_threaded_loading = False
    
    stc_class = NonResidentSTC

    @classmethod
    def verifyProtocol(cls, url):
        # Use the verifyProtocol to hijack the loading process and
        # immediately return the match if we're trying to load
        # about:blank
        if url.protocol == 'about' and url.path == 'blank':
            return True
        return False

    def createEditWindow(self,parent):
        win=wx.Window(parent, -1, pos=(9000,9000))
        text=self.buffer.stc.GetText()
        lines=wx.StaticText(win, -1, text, (10,10))
        lines.Wrap(500)
        self.stc = self.buffer.stc
        self.buffer.stc.is_permanent = True
        return win


class LoadingSTC(NonResidentSTC):
    def __init__(self, url, modecls):
        self.url = url
        self.modecls = modecls

    def GetText(self):
        return str(self.url)


class LoadingMode(BlankMode):
    """
    A temporary Major Mode to load another mode in the background
    """
    keyword = 'Loading...'
    
    stc_class = LoadingSTC

    def createPostHook(self):
        self.showBusy(True)
        wx.CallAfter(self.frame.openStart, self.stc.url, self.stc.modecls,
                     mode_to_replace=self)

class LoadingBuffer(debugmixin):
    def __init__(self, url, modecls):
        self.url = url
        self.stc = LoadingSTC(url, modecls)
        self.busy = True
        self.readonly = False
        self.modified = False
        self.defaultmode = LoadingMode

    def addViewer(self, mode):
        pass

    def removeViewer(self, mode):
        pass

    def removeAllViewsAndDelete(self):
        pass
    
    def save(self, url):
        pass

    def getTabName(self):
        return self.defaultmode.keyword


class BufferLoadThread(threading.Thread, debugmixin):
    """Background file loading thread.
    """
    def __init__(self, frame, buffer, mode_to_replace, progress=None):
        threading.Thread.__init__(self)
        
        self.frame = frame
        self.buffer = buffer
        self.mode_to_replace = mode_to_replace
        self.progress = progress

        self.start()

    def run(self):
        self.dprint("starting to load %s" % self.buffer.url)
        try:
            self.buffer.openBackgroundThread(self.progress.message)
            wx.CallAfter(self.frame.openSuccess, self.buffer,
                         self.mode_to_replace, self.progress)
            self.dprint("successfully loaded %s" % self.buffer.url)
        except Exception, e:
            import traceback
            traceback.print_exc()
            self.dprint("Exception: %s" % str(e))
            wx.CallAfter(self.frame.openFailure, self.buffer, str(e),
                         self.progress)
