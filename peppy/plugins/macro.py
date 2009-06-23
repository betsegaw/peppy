# peppy Copyright (c) 2006-2008 Rob McMullen
# Licenced under the GPLv2; see http://peppy.flipturn.org for more info
"""Simple macros created by recording actions

This plugin provides macro recording
"""

import os

import wx

from peppy.yapsy.plugins import *

from peppy.actions import *
from peppy.lib.multikey import *
from peppy.debug import *
import peppy.vfs as vfs


class CharEvent(FakeCharEvent):
    """Fake character event used by L{RecordKeyboardAction} when generating
    scripted copies of an action list.
    
    """
    def __init__(self, key, unicode, modifiers):
        self.id = -1
        self.event_object = None
        self.keycode = key
        self.unicode = unicode
        self.modifiers = modifiers
        self.is_quoted = True
    
    @classmethod
    def getScripted(cls, evt):
        """Returns a string that represents the python code to instantiate
        the object.
        
        Used when serializing a L{RecordedKeyboardAction} to a python string
        """
        return "%s(%d, %d, %d)" % (cls.__name__, evt.GetKeyCode(), evt.GetUnicodeKey(), evt.GetModifiers())


class RecordedKeyboardAction(RecordedAction):
    """Subclass of L{RecordedAction} for keyboard events.
    
    """
    def __init__(self, action, evt, multiplier):
        RecordedAction.__init__(self, action, multiplier)
        self.evt = FakeCharEvent(evt)
        
        # Hack to force SelfInsertCommand to process the character, because
        # normally it uses the evt.Skip() to force the EVT_CHAR handler to
        # insert the character.
        self.evt.is_quoted = True
    
    def __str__(self):
        return "%s: %dx%s" % (self.actioncls.__name__, self.multiplier, self.evt.GetKeyCode())
    
    def performAction(self, system_state):
        action = self.actioncls(system_state.frame, mode=system_state.mode)
        dprint(action.__class__.__name__)
        action.actionKeystroke(self.evt, self.multiplier)
    
    def getScripted(self):
        return "%s(frame, mode).actionKeystroke(%s, %d)" % (self.actioncls.__name__, CharEvent.getScripted(self.evt), self.multiplier)


class RecordedMenuAction(RecordedAction):
    """Subclass of L{RecordedAction} for menu events.
    
    """
    def __init__(self, action, index, multiplier):
        RecordedAction.__init__(self, action, multiplier)
        self.index = index
    
    def __str__(self):
        return "%s x%d, index=%s" % (self.actioncls.__name__, self.multiplier, self.index)
    
    def performAction(self, system_state):
        action = self.actioncls(system_state.frame, mode=system_state.mode)
        dprint(action.__class__.__name__)
        action.action(self.index, self.multiplier)
    
    def getScripted(self):
        return "%s(frame, mode).action(%d, %d)" % (self.index, self.multiplier)


class ActionRecorder(AbstractActionRecorder, debugmixin):
    """Creates, maintains and plays back a list of actions recorded from the
    user's interaction with a major mode.
    
    """
    def __init__(self):
        self.recording = []
    
    def __str__(self):
        summary = ''
        count = 0
        for recorded_item in self.recording:
            if hasattr(recorded_item, 'text'):
                summary += recorded_item.text + " "
                if len(summary) > 50:
                    summary = summary[0:50] + "..."
            count += 1
        if len(summary) == 0:
            summary = "untitled"
        return summary.strip()
        
    def details(self):
        """Get a list of actions that have been recorded.
        
        Primarily used for debugging, there is no way to use this list to
        play back the list of actions.
        """
        lines = []
        for recorded_item in self.recording:
            lines.append(str(recorded_item))
        return "\n".join(lines)
        
    def recordKeystroke(self, action, evt, multiplier):
        if action.isRecordable():
            record = RecordedKeyboardAction(action, evt, multiplier)
            self.appendRecord(record)
    
    def recordMenu(self, action, index, multiplier):
        if action.isRecordable():
            record = RecordedMenuAction(action, index, multiplier)
            self.appendRecord(record)
    
    def appendRecord(self, record):
        """Utility method to add a recordable action to the current list
        
        This method checks for the coalescability of the record with the
        previous record, and it is merged if possible.
        
        @param record: L{RecordedAction} instance
        """
        dprint("adding %s" % record)
        if self.recording:
            last = self.recording[-1]
            if last.canCoalesceActions(record):
                self.recording.pop()
                record = last.coalesceActions(record)
                dprint("coalesced into %s" % record)
        self.recording.append(record)
    
    def getRecordedActions(self):
        return self.recording
    
    def playback(self, frame, mode, multiplier=1):
        mode.BeginUndoAction()
        state = MacroPlaybackState(frame, mode)
        dprint(state)
        SelectAction.debuglevel = 1
        while multiplier > 0:
            for recorded_action in self.getRecordedActions():
                recorded_action.performAction(state)
            multiplier -= 1
        SelectAction.debuglevel = 0
        mode.EndUndoAction()


class PythonScriptableMacro(object):
    """A list of serialized SelectAction commands used in playing back macros.
    
    This object contains python code in the form of text strings that
    provide a way to reproduce the effects of a previously recorded macro.
    Additionally, since they are in plain text, they may be carefully edited
    by the user to provide additional functionality that is not possible only
    using the record capability.
    
    The generated python script looks like the following:
    
    SelfInsertCommand(frame, mode).actionKeystroke(CharEvent(97, 97, 0), 1)
    BeginningTextOfLine(frame, mode).actionKeystroke(CharEvent(65, 65, 2), 1)
    SelfInsertCommand(frame, mode).actionKeystroke(CharEvent(98, 98, 0), 1)
    ElectricReturn(frame, mode).actionKeystroke(CharEvent(13, 13, 0), 1)
    
    where the actions are listed, one per line, by their python class name.
    The statements are C{exec}'d in in the global namespace, but have a
    constructed local namespace that includes C{frame} and C{mode} representing
    the current L{BufferFrame} and L{MajorMode} instance, respectively.
    """
    def __init__(self, recorder=None):
        """Converts the list of recorded actions into python string form.
        
        """
        if recorder:
            self.name = str(recorder)
            self.script = self.getScriptFromRecorder(recorder)
        else:
            self.name = "untitled"
            self.script = ""
    
    def __str__(self):
        return self.name
    
    def setName(self, name):
        """Changes the name of the macro to the supplied string.
        
        """
        self.name = name
    
    def getScriptFromRecorder(self, recorder):
        """Converts the list of recorded actions into a python script that can
        be executed by the L(playback) method.
        
        Calls the L{RecordAction.getScripted} method of each recorded action to
        generate the python script version of the action.
        
        @returns: a multi-line string, exec-able using the L{playback} method
        """
        script = ""
        lines = []
        for recorded_action in recorder.getRecordedActions():
            lines.append(recorded_action.getScripted())
        script += "\n".join(lines)
        return script
    
    def playback(self, frame, mode, multiplier=1):
        """Plays back the list of actions.
        
        Uses the current frame and mode as local variables for the python
        scripted version of the action list.
        """
        local = {'mode': mode,
                 'frame': frame,
                 }
        self.addActionsToLocal(local)
        #dprint(local)
        dprint(self.script)
        while multiplier > 0:
            exec self.script in globals(), local
            multiplier -= 1
    
    def addActionsToLocal(self, local):
        """Sets up the local environment for the exec call
        
        All the possible actions must be placed in the local environment for
        the call to exec.
        """
        actions = MacroAction.getAllKnownActions()
        for action in actions:
            local[action.__name__] = action
        actions = SelectAction.getAllKnownActions()
        for action in actions:
            local[action.__name__] = action



class StartRecordingMacro(SelectAction):
    """Begin recording actions"""
    name = "Start Recording"
    key_bindings = {'default': "C-1", }
    default_menu = (("Tools/Macros", -800), 100)
    
    def action(self, index=-1, multiplier=1):
        self.frame.root_accel.startRecordingActions(ActionRecorder())


class StopRecordingMacro(SelectAction):
    """Stop recording actions"""
    name = "Stop Recording"
    key_bindings = {'default': "C-2", }
    default_menu = ("Tools/Macros", 110)
    
    @classmethod
    def isRecordable(cls):
        return False
    
    def action(self, index=-1, multiplier=1):
        if self.frame.root_accel.isRecordingActions():
            recorder = self.frame.root_accel.stopRecordingActions()
            dprint(recorder)
            RecentMacros.appendRecording(recorder)


class ReplayLastMacro(SelectAction):
    """Play back last macro that was recorded"""
    name = "Play Last Macro"
    key_bindings = {'default': "C-3", }
    default_menu = ("Tools/Macros", 120)
    
    def isEnabled(self):
        return RecentMacros.isEnabled()
    
    @classmethod
    def isRecordable(cls):
        return False
    
    def action(self, index=-1, multiplier=1):
        if self.frame.root_accel.isRecordingActions():
            recorder = self.frame.root_accel.stopRecordingActions()
            dprint(recorder)
            RecentMacros.appendRecording(recorder)
        macro = RecentMacros.getLastMacro()
        if macro:
            dprint("Playing back %s" % macro)
            wx.CallAfter(macro.playback, self.frame, self.mode, multiplier)
        else:
            dprint("No recorded macro.")
        


class RecentMacros(OnDemandGlobalListAction):
    """Play a macro from the list of recently created macros
    
    Maintains a list of the recent macros and runs the selected macro if chosen
    out of the submenu.
    
    Macros are stored as a list of L{PythonScriptableMacro}s in most-recent to
    least recent order.
    """
    name = "Recent Macros"
    default_menu = ("Tools/Macros", -200)
    inline = False
    
    storage = []
    
    @classmethod
    def isEnabled(cls):
        return bool(cls.storage)
    
    @classmethod
    def appendRecording(cls, recorder):
        """Convert the recording from a L{ActionRecorder} into a
        L{PythonScriptableMacro} and add it to the list of recent macros.
        
        """
        macro = PythonScriptableMacro(recorder)
        MacroFS.addMacro(macro)
        cls.storage[0:0] = (macro.name, )
        cls.trimStorage(MacroPlugin.classprefs.list_length)
        cls.calcHash()
    
    @classmethod
    def setStorage(cls, array):
        cls.storage = array
        cls.trimStorage(MacroPlugin.classprefs.list_length)
        cls.calcHash()
        
    @classmethod
    def getLastMacro(cls):
        """Return the most recently added macro
        
        @returns L{PythonScriptableMacro} instance, or None if no macro has yet
        been added.
        """
        if cls.storage:
            name = cls.storage[0]
            return MacroFS.getMacro(name)
        return None
    
    def action(self, index=-1, multiplier=1):
        name = self.storage[index]
        macro = MacroFS.getMacro(name)
        assert self.dprint("replaying macro %s" % macro)
        wx.CallAfter(macro.playback, self.frame, self.mode, 1)


class MacroSaveData(object):
    """Data transfer object to serialize the state of the macro system"""
    
    version = 1
    
    def __init__(self):
        self.macros = MacroFS.macros
        self.recent = RecentMacros.storage
    
    @classmethod
    def load(cls, url):
        import cPickle as pickle
        
        # Note: because plugins are loaded using the execfile command, pickle
        # can't find classes that are in the global namespace.  Have to supply
        # PythonScriptableMacro into the builtin namespace to get around this.
        import __builtin__
        __builtin__.PythonScriptableMacro = PythonScriptableMacro
        
        if not vfs.exists(url):
            return
        
        fh = vfs.open(url)
        bytes = fh.read()
        fh.close()
        if bytes:
            version, data = pickle.loads(bytes)
            if version == 1:
                cls.unpackVersion1(data)
            else:
                raise RuntimeError("Unknown version of MacroSaveData in %s" % url)
    
    @classmethod
    def unpackVersion1(self, data):
        macros, recent = data
        MacroFS.macros.update(macros)
        dprint(MacroFS.macros)
        RecentMacros.setStorage(recent)
    
    @classmethod
    def save(cls, url):
        import cPickle as pickle
        
        # See above for the note about the builtin namespace
        import __builtin__
        __builtin__.PythonScriptableMacro = PythonScriptableMacro
        
        data = cls.packVersion1()
        pickled = pickle.dumps(data)
        fh = vfs.open_write(url)
        fh.write(pickled)
        fh.close()
    
    @classmethod
    def packVersion1(cls):
        data = (cls.version, (MacroFS.macros, RecentMacros.storage))
        dprint(data)
        return data


class MacroFS(vfs.BaseFS):
    """Filesystem to recognize "macro:macro_name" URLs
    
    This simple filesystem allows URLs in the form of "macro:macro_name", and
    provides the mapping from the macro name to the L{PythonScriptableMacro}
    instance.
    
    On disk, this is serialized as a pickle object of the macro class attribute.
    """
    macros = {}
    
    @classmethod
    def addMacro(cls, macro):
        name = cls.getUniqueName(macro)
        macro.setName(name)
        cls.macros[name] = macro
    
    @classmethod
    def getUniqueName(cls, macro):
        basename = macro.name
        name = basename
        count = 0
        while name in cls.macros:
            count += 1
            name = basename + "<%d>" % count
        return name
    
    @classmethod
    def getMacro(cls, name):
        return cls.macros[name]
    
    @classmethod
    def _get(cls, reference):
        name = str(reference.path)
        if name in cls.macros:
            return cls.macros[name]
        return ""
    
    @classmethod
    def exists(cls, reference):
        return bool(cls._get(reference))

    @classmethod
    def is_file(cls, reference):
        return bool(cls._get(reference))

    @classmethod
    def is_folder(cls, reference):
        return False

    @classmethod
    def can_read(cls, reference):
        return bool(cls._get(reference))

    @classmethod
    def can_write(cls, reference):
        return False

    @classmethod
    def get_size(cls, reference):
        return len(cls._get(reference))

    @classmethod
    def open(cls, reference, mode=None):
        text = cls._get(reference)
        if text:
            fh = StringIO(text)
            #dprint(fh.getvalue())
            return fh
        return None


class MacroPlugin(IPeppyPlugin):
    """Plugin providing the macro recording capability
    """
    default_classprefs = (
        StrParam('macro_file', 'macros.dat', 'File name in main peppy configuration directory used to store macro definitions'),
        IntParam('list_length', 3, 'Number of macros to save in the Recent Macros list'),
        )

    def activateHook(self):
        vfs.register_file_system('macro', MacroFS)

    def initialActivation(self):
        pathname = wx.GetApp().getConfigFilePath(self.classprefs.macro_file)
        macro_url = vfs.normalize(pathname)
        try:
            MacroSaveData.load(macro_url)
        except:
            dprint("Failed loading macro data to %s" % macro_url)
            import traceback
            traceback.print_exc()

    def requestedShutdown(self):
        pathname = wx.GetApp().getConfigFilePath(self.classprefs.macro_file)
        macro_url = vfs.normalize(pathname)
        try:
            MacroSaveData.save(macro_url)
        except:
            dprint("Failed saving macro data to %s" % macro_url)
            import traceback
            traceback.print_exc()
            pass

    def deactivateHook(self):
        vfs.deregister_file_system('macro')
        
    def getActions(self):
        return [
            StartRecordingMacro, StopRecordingMacro, ReplayLastMacro,
            
            RecentMacros,
            ]
