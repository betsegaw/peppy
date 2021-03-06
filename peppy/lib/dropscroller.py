#-----------------------------------------------------------------------------
# Name:        dropscroller.py
# Purpose:     auto scrolling for a list that's being used as a drop target
#
# Author:      Rob McMullen
#
# Created:     2007
# RCS-ID:      $Id: $
# Copyright:   (c) 2007 Rob McMullen
# License:     wxPython
#-----------------------------------------------------------------------------
"""
Automatic scrolling mixin for a list control, including an indicator
showing where the items will be dropped.

It would be nice to have somethin similar for a tree control as well,
but I haven't tackled that yet.
"""
import sys, pickle

import wx

class ListDropScrollerMixin(object):
    """Automatic scrolling for ListCtrls for use when using drag and drop.

    This mixin is used to automatically scroll a list control when
    approaching the top or bottom edge of a list.  Currently, this
    only works for lists in report mode.

    Add this as a mixin in your list, and then call processListScroll
    in your DropTarget's OnDragOver method.  When the drop ends, call
    finishListScroll to clean up the resources (i.e. the wx.Timer)
    that the dropscroller uses and make sure that the insertion
    indicator is erased.

    The parameter interval is the delay time in milliseconds between
    list scroll steps.

    If indicator_width is negative, then the indicator will be the
    width of the list.  If positive, the width will be that number of
    pixels, and zero means to display no indicator.
    """
    def __init__(self, interval=200, width=-1):
        """Don't forget to call this mixin's init method in your List.

        Interval is in milliseconds.
        """
        self._auto_scroll_timer = None
        self._auto_scroll_interval = interval
        self._auto_scroll = 0
        self._auto_scroll_save_y = -1
        self._auto_scroll_save_width = width
        self._auto_scroll_last_state = 0
        self._auto_scroll_last_index = -1
        self._auto_scroll_indicator_line = True
        self.Bind(wx.EVT_TIMER, self.OnAutoScrollTimer)
        
    def clearAllSelected(self):
        """clear all selected items"""
        list_count = self.GetItemCount()
        for index in range(list_count):
            self.SetItemState(index, 0, wx.LIST_STATE_SELECTED)

    def _startAutoScrollTimer(self, direction = 0):
        """Set the direction of the next scroll, and start the
        interval timer if it's not already running.
        """
        if self._auto_scroll_timer == None:
            self._auto_scroll_timer = wx.Timer(self, wx.TIMER_ONE_SHOT)
            self._auto_scroll_timer.Start(self._auto_scroll_interval)
        self._auto_scroll = direction

    def _stopAutoScrollTimer(self):
        """Clean up the timer resources.
        """
        self._auto_scroll_timer = None
        self._auto_scroll = 0

    def _getAutoScrollDirection(self, index):
        """Determine the scroll step direction that the list should
        move, based on the index reported by HitTest.
        """
        first_displayed = self.GetTopItem()

        if first_displayed == index:
            # If the mouse is over the first index...
            if index > 0:
                # scroll the list up unless...
                return -1
            else:
                # we're already at the top.
                return 0
        elif index >= first_displayed + self.GetCountPerPage() - 1:
            # If the mouse is over the last visible item, but we're
            # not at the last physical item, scroll down.
            return 1
        # we're somewhere in the middle of the list.  Don't scroll
        return 0

    def getDropIndex(self, x, y, index=None, flags=None, insert=True):
        """Find the index to insert the new item, which could be
        before or after the index passed in.
        
        @return: if insert is true, return value is the index of the insert
        point (i.e.  the new data should be inserted at that point, pushing
        the existing data further down the list).  If insert is false, the
        return value is the item on which the drop happened, or -1 indicating
        an invalid drop.
        """
        if index is None:
            index, flags = self.HitTest((x, y))

        # Not clicked on an item
        if index == wx.NOT_FOUND:
            
            # If it's an empty list or below the last item
            if (flags & (wx.LIST_HITTEST_NOWHERE|wx.LIST_HITTEST_ABOVE|wx.LIST_HITTEST_BELOW)):
                
                # Append to the end of the list or return an invalid index
                if insert:
                    index = sys.maxint
                else:
                    index = self.GetItemCount() - 1
                #print "getDropIndex: append to end of list: index=%d" % index
            elif (self.GetItemCount() > 0):
                if y <= self.GetItemRect(0).y: # clicked just above first item
                    index = 0 # append to top of list
                    #print "getDropIndex: before first item: index=%d, y=%d, rect.y=%d" % (index, y, self.GetItemRect(0).y)
                elif insert:
                    index = self.GetItemCount() # append to end of list
                    #print "getDropIndex: after last item: index=%d" % index
                else:
                    index = self.GetItemCount() - 1
                    
        # Otherwise, we've clicked on an item.  If we're in insert mode, check
        # to see if the cursor is between items
        elif insert:
            # Get bounding rectangle for the item the user is dropping over.
            rect = self.GetItemRect(index)
            #print "getDropIndex: landed on %d, y=%d, rect=%s" % (index, y, rect)

            # NOTE: On all platforms, the y coordinate used by HitTest
            # is relative to the scrolled window.  There are platform
            # differences, however, because on GTK the top of the
            # vertical scrollbar stops below the header, while on MSW
            # the top of the vertical scrollbar is equal to the top of
            # the header.  The result is the y used in HitTest and the
            # y returned by GetItemRect are offset by a certain amount
            # on GTK.  The HitTest's y=0 in GTK corresponds to the top
            # of the first item, while y=0 on MSW is in the header.
            
            # From Robin Dunn: use GetMainWindow on the list to find
            # the actual window on which to draw
            if self != self.GetMainWindow():
                y += self.GetMainWindow().GetPositionTuple()[1]

            # If the user is dropping into the lower half of the rect,
            # we want to insert _after_ this item.
            if y >= (rect.y + rect.height/2):
                index = index + 1

        return index

    def processListScroll(self, x, y, line=True):
        """Main handler: call this with the x and y coordinates of the
        mouse cursor as determined from the OnDragOver callback.

        This method will determine which direction the list should be
        scrolled, and start the interval timer if necessary.
        """
        if self.GetItemCount() == 0:
            # don't show any lines if we don't have any items in the list
            return

        index, flags = self.HitTest((x, y))

        direction = self._getAutoScrollDirection(index)
        if direction == 0:
            self._stopAutoScrollTimer()
        else:
            self._startAutoScrollTimer(direction)
        self._auto_scroll_indicator_line = line
            
        drop_index = self.getDropIndex(x, y, index=index, flags=flags)
        if line:
            self._processLineIndicator(x, y, drop_index)
        else:
            self._processHighlightIndicator(drop_index)
    
    def _processLineIndicator(self, x, y, drop_index):
        count = self.GetItemCount()
        if drop_index >= count:
            index = min(count, drop_index)
            rect = self.GetItemRect(index - 1)
            y = rect.y + rect.height + 1
        else:
            rect = self.GetItemRect(drop_index)
            y = rect.y

        # From Robin Dunn: on GTK & MAC the list is implemented as
        # a subwindow, so have to use GetMainWindow on the list to
        # find the actual window on which to draw
        if self != self.GetMainWindow():
            y -= self.GetMainWindow().GetPositionTuple()[1]

        if self._auto_scroll_save_y == -1 or self._auto_scroll_save_y != y:
            #print "main window=%s, self=%s, pos=%s" % (self, self.GetMainWindow(), self.GetMainWindow().GetPositionTuple())
            if self._auto_scroll_save_width < 0:
                self._auto_scroll_save_width = rect.width
            dc = self._getIndicatorDC()
            self._eraseIndicator(dc)
            dc.DrawLine(0, y, self._auto_scroll_save_width, y)
            self._auto_scroll_save_y = y

    def _processHighlightIndicator(self, index):
        count = self.GetItemCount()
        if index >= count:
            index = count - 1
        if self._auto_scroll_last_index != index:
            selected = self.GetItemState(index, wx.LIST_STATE_SELECTED)
            if not selected:
                self.SetItemState(index, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
            if self._auto_scroll_last_index != -1:
                #self.SetItemState(self._auto_scroll_last_index, self._auto_scroll_last_state, wx.LIST_STATE_SELECTED)
                self.SetItemState(self._auto_scroll_last_index, 0, wx.LIST_STATE_SELECTED)
            self._auto_scroll_last_state = selected
            self._auto_scroll_last_index = index
    
    def finishListScroll(self):
        """Clean up timer resource and erase indicator.
        """
        self._stopAutoScrollTimer()
        self._eraseIndicator()
        self._auto_scroll_last_index = -1
        self._auto_scroll_last_state = 0
        
    def OnAutoScrollTimer(self, evt):
        """Timer event handler to scroll the list in the requested
        direction.
        """
        #print "_auto_scroll = %d, timer = %s" % (self._auto_scroll, self._auto_scroll_timer is not None)
        count = self.GetItemCount()
        if self._auto_scroll == 0:
            # clean up timer resource
            self._auto_scroll_timer = None
        elif count > 0:
            if self._auto_scroll_indicator_line:
                dc = self._getIndicatorDC()
                self._eraseIndicator(dc)
            if self._auto_scroll < 0:
                index = max(0, self.GetTopItem() + self._auto_scroll)
            else:
                index = min(self.GetTopItem() + self.GetCountPerPage(), count - 1)
            self.EnsureVisible(index)
            self._auto_scroll_timer.Start()
        evt.Skip()

    def _getIndicatorDC(self):
        dc = wx.ClientDC(self.GetMainWindow())
        dc.SetPen(wx.Pen(wx.WHITE, 3))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.SetLogicalFunction(wx.XOR)
        return dc

    def _eraseIndicator(self, dc=None):
        if self._auto_scroll_indicator_line:
            if dc is None:
                dc = self._getIndicatorDC()
            if self._auto_scroll_save_y >= 0:
                # erase the old line
                dc.DrawLine(0, self._auto_scroll_save_y,
                            self._auto_scroll_save_width, self._auto_scroll_save_y)
        self._auto_scroll_save_y = -1


class PickledDataObject(wx.CustomDataObject):
    """Sample custom data object storing indexes of the selected items"""
    def __init__(self):
        wx.CustomDataObject.__init__(self, "Pickled")

class PickledDropTarget(wx.PyDropTarget):
    """Custom drop target modified from the wxPython demo."""
    debug = False
    
    def __init__(self, window):
        wx.PyDropTarget.__init__(self)
        self.dv = window

        # specify the type of data we will accept
        self.data = PickledDataObject()
        self.SetDataObject(self.data)

    def cleanup(self):
        self.dv.finishListScroll()

    # some virtual methods that track the progress of the drag
    def OnEnter(self, x, y, d):
        if self.debug: print "OnEnter: %d, %d, %d\n" % (x, y, d)
        return d

    def OnLeave(self):
        if self.debug: print "OnLeave\n"
        self.cleanup()

    def OnDrop(self, x, y):
        if self.debug: print "OnDrop: %d %d\n" % (x, y)
        self.cleanup()
        return True

    def OnDragOver(self, x, y, d):
        top = self.dv.GetTopItem()
        if self.debug: print "OnDragOver: %d, %d, %d, top=%s" % (x, y, d, top)

        self.dv.processListScroll(x, y)

        # The value returned here tells the source what kind of visual
        # feedback to give.  For example, if wxDragCopy is returned then
        # only the copy cursor will be shown, even if the source allows
        # moves.  You can use the passed in (x,y) to determine what kind
        # of feedback to give.  In this case we return the suggested value
        # which is based on whether the Ctrl key is pressed.
        return d

    # Called when OnDrop returns True.  We need to get the data and
    # do something with it.
    def OnData(self, x, y, d):
        if self.debug: print "OnData: %d, %d, %d\n" % (x, y, d)

        self.cleanup()
        # copy the data from the drag source to our data object
        if self.GetData():
            # convert it back to a list of lines and give it to the viewer
            items = pickle.loads(self.data.GetData())
            self.dv.AddDroppedItems(x, y, items)

        # what is returned signals the source what to do
        # with the original data (move, copy, etc.)  In this
        # case we just return the suggested value given to us.
        return d


class ReorderableList(wx.ListCtrl, ListDropScrollerMixin):
    """Simple list control that provides a drop target and uses
    the new mixin for automatic scrolling.
    """
    def __init__(self, parent, items, col_title, size=(400,400)):
        wx.ListCtrl.__init__(self, parent, size=size, style=wx.LC_REPORT)
        self.debug = False

        # The mixin needs to be initialized
        ListDropScrollerMixin.__init__(self, interval=200)
        
        self.dropTarget=PickledDropTarget(self)
        self.SetDropTarget(self.dropTarget)
        self.Bind(wx.EVT_LIST_BEGIN_DRAG, self.OnStartDrag)
        
        self.create(col_title, items)

    def create(self, col_title, items):
        """Set up some test data."""
        self.clear(None)
        self.InsertColumn(0, col_title)
        for item in items:
            self.InsertStringItem(sys.maxint, item)
        self.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        width1 = self.GetColumnWidth(0)
        self.SetColumnWidth(0, wx.LIST_AUTOSIZE_USEHEADER)
        width2 = self.GetColumnWidth(0)
        if width1 > width2:
            self.SetColumnWidth(0, width1)

    def OnStartDrag(self, evt):
        index = evt.GetIndex()
        #print "beginning drag of item %d" % index

        # Create the data object containing all currently selected
        # items
        data = PickledDataObject()
        items = []
        index = self.GetFirstSelected()
        while index != -1:
            items.append(index)
            index = self.GetNextSelected(index)
        data.SetData(pickle.dumps(items,-1))

        # And finally, create the drop source and begin the drag
        # and drop opperation
        dropSource = wx.DropSource(self)
        dropSource.SetData(data)
        #print "Begining DragDrop\n"
        result = dropSource.DoDragDrop(wx.Drag_AllowMove)
        #print "DragDrop completed: %d\n" % result

    def AddDroppedItems(self, x, y, items):
        start_index = self.getDropIndex(x, y)
        if self.debug: print "At (%d,%d), index=%d, adding %s" % (x, y, start_index, items)

        list_count = self.GetItemCount()
        new_order = range(list_count)
        index = start_index
        for item in items:
            if item < start_index:
                start_index -= 1
            new_order.remove(item)
        if self.debug: print("inserting %s into %s at %d" % (str(items), str(new_order), start_index))
        new_order[start_index:start_index] = items
        if self.debug: print("orig list = %s" % str(range(list_count)))
        if self.debug: print(" new list = %s" % str(new_order))
        
        self.changeList(new_order, items)
    
    def deleteSelected(self):
        list_count = self.GetItemCount()
        new_order = range(list_count)
        index = self.GetFirstSelected()
        while index != -1:
            new_order.remove(index)
            index = self.GetNextSelected(index)
        if self.debug: print("orig list = %s" % str(range(list_count)))
        if self.debug: print(" new list = %s" % str(new_order))
        self.changeList(new_order)
    
    def changeList(self, new_order, make_selected=[]):
        """Reorder the list given the new list of indexes.
        
        The new list will be constructed by building up items based on the
        indexes specified in new_order as taken from the current list.  The
        ListCtrl contents is then replaced with the new list of items.  Items
        may also be deleted from the list by not including items in the
        new_order.
        
        @param new_order: list of indexes used to compose the new list
        
        @param make_selected: optional list showing indexes of original order
        that should be marked as selected in the new list.
        """
        saved = {}
        new_selection = []
        new_count = len(new_order)
        for i in range(new_count):
            new_i = new_order[i]
            if i != new_i:
                src = self.GetItem(i)
                if new_i in saved:
                    text = saved[new_i]
                else:
                    text = self.GetItem(new_i).GetText()
                
                # save the value that's about to be overwritten
                if i not in saved:
                    saved[i] = self.GetItem(i).GetText()
                if self.debug: print("setting %d to value from %d: %s" % (i, new_i, text))
                self.SetStringItem(i, 0, text)
                
                # save the new highlight position
                if new_i in make_selected:
                    new_selection.append(i)
            
            # Selection stays with the index even when the item text changes,
            # so remove the selection from all items for the moment
            self.SetItemState(i, 0, wx.LIST_STATE_SELECTED)
        
        # if the list size has been reduced, clean up any extra items
        list_count = self.GetItemCount()
        for i in range(new_count, list_count):
            self.DeleteItem(new_count)
        
        # Turn the selection back on for the new positions of the moved items
        for i in new_selection:
            self.SetItemState(i, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
    
    def clear(self, evt):
        self.DeleteAllItems()
    
    def getItems(self):
        list_count = self.GetItemCount()
        items = []
        for i in range(list_count):
            items.append(self.GetItem(i).GetText())
        return items


class ListReorderDialog(wx.Dialog):
    """Simple dialog to return a list of items that can be reordered by the user.
    """
    def __init__(self, parent, items, title="Reorder List", col_title="Items"):
        wx.Dialog.__init__(self, parent, -1, title,
                           size=(700, 500), pos=wx.DefaultPosition, 
                           style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)

        sizer = wx.BoxSizer(wx.VERTICAL)

        self.list = ReorderableList(self, items, col_title)
        sizer.Add(self.list, 1, wx.EXPAND)

        btnsizer = wx.StdDialogButtonSizer()
        
        btn = wx.Button(self, wx.ID_OK)
        btn.SetDefault()
        btnsizer.AddButton(btn)

        btn = wx.Button(self, wx.ID_CANCEL)
        btnsizer.AddButton(btn)
        btnsizer.Realize()

        sizer.Add(btnsizer, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.Layout()
        
        self.Bind(wx.EVT_CONTEXT_MENU, self.OnContextMenu)
        self.delete_id = wx.NewId()
        self.Bind(wx.EVT_MENU, self.OnDelete, id=self.delete_id)
    
    def OnContextMenu(self, evt):
        menu = wx.Menu()
        menu.Append(self.delete_id, "Delete Selected Items")
        if self.list.GetSelectedItemCount() == 0:
            menu.Enable(self.delete_id, False)
        self.PopupMenu(menu)
        menu.Destroy()
    
    def OnDelete(self, evt):
        self.list.deleteSelected()

    def getItems(self):
        return self.list.getItems()


if __name__ == '__main__':
    class TestList(wx.ListCtrl, ListDropScrollerMixin):
        """Simple list control that provides a drop target and uses
        the new mixin for automatic scrolling.
        """
        
        def __init__(self, parent, name, count=100):
            wx.ListCtrl.__init__(self, parent, style=wx.LC_REPORT)

            # The mixin needs to be initialized
            ListDropScrollerMixin.__init__(self, interval=200)
            
            self.dropTarget=PickledDropTarget(self)
            self.SetDropTarget(self.dropTarget)

            self.create(name, count)
            
            self.Bind(wx.EVT_LIST_BEGIN_DRAG, self.OnStartDrag)

        def create(self, name, count):
            """Set up some test data."""
            
            self.InsertColumn(0, "#")
            self.InsertColumn(1, "Title")
            for i in range(count):
                self.InsertStringItem(sys.maxint, str(i))
                self.SetStringItem(i, 1, "%s-%d" % (name, i))

        def OnStartDrag(self, evt):
            index = evt.GetIndex()
            print "beginning drag of item %d" % index

            # Create the data object containing all currently selected
            # items
            data = PickledDataObject()
            items = []
            index = self.GetFirstSelected()
            while index != -1:
                items.append((self.GetItem(index, 0).GetText(),
                              self.GetItem(index, 1).GetText()))
                index = self.GetNextSelected(index)
            data.SetData(pickle.dumps(items,-1))

            # And finally, create the drop source and begin the drag
            # and drop opperation
            dropSource = wx.DropSource(self)
            dropSource.SetData(data)
            print "Begining DragDrop\n"
            result = dropSource.DoDragDrop(wx.Drag_AllowMove)
            print "DragDrop completed: %d\n" % result

        def AddDroppedItems(self, x, y, items):
            index = self.getDropIndex(x, y)
            print "At (%d,%d), index=%d, adding %s" % (x, y, index, items)

            list_count = self.GetItemCount()
            for item in items:
                if index == -1:
                    index = 0
                index = self.InsertStringItem(index, item[0])
                self.SetStringItem(index, 1, item[1])
                index += 1
        
        def clear(self, evt):
            self.DeleteAllItems()

    class ListPanel(wx.SplitterWindow):
        def __init__(self, parent):
            wx.SplitterWindow.__init__(self, parent)

            self.list1 = TestList(self, "left", 100)
            self.list2 = TestList(self, "right", 10)
            self.SplitVertically(self.list1, self.list2)
            self.Layout()
    
    def showDialog(parent):
        dlg = ListReorderDialog(parent, [chr(i + 65) for i in range(26)])
        if dlg.ShowModal() == wx.ID_OK:
            items = dlg.getItems()
            print items
        dlg.Destroy()

    app   = wx.PySimpleApp()
    frame = wx.Frame(None, -1, title='List Drag Test', size=(400,500))
    frame.CreateStatusBar()
    
    panel = ListPanel(frame)
    label = wx.StaticText(frame, -1, "Drag items from a list to either list.\nThe lists will scroll when the cursor\nis near the first and last visible items")

    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(label, 0, wx.ALIGN_CENTRE|wx.ALL, 5)
    sizer.Add(panel, 1, wx.EXPAND | wx.ALL, 5)
    hsizer = wx.BoxSizer(wx.HORIZONTAL)
    btn1 = wx.Button(frame, -1, "Clear List 1")
    btn1.Bind(wx.EVT_BUTTON, panel.list1.clear)
    btn2 = wx.Button(frame, -1, "Clear List 2")
    btn2.Bind(wx.EVT_BUTTON, panel.list2.clear)
    hsizer.Add(btn1, 1, wx.EXPAND)
    hsizer.Add(btn2, 1, wx.EXPAND)
    sizer.Add(hsizer, 0, wx.EXPAND)
    
    frame.SetAutoLayout(1)
    frame.SetSizer(sizer)
    frame.Show(1)
    
    wx.CallAfter(showDialog, frame)
    
    app.MainLoop()
