# -*- coding: UTF-8 -*-
# Copyright (C) 2007 Rob McMullen <robm@users.sourceforge.net>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Import from the Standard Library
from datetime import datetime
from StringIO import StringIO

# Import from itools
from itools.uri import Path, Reference
from itools.vfs import READ, WRITE, APPEND, copy
from itools.vfs.base import BaseFS
from itools.vfs.registry import register_file_system

class MemDir(dict):
    """Base class used for nested dictionaries representing directories."""
    is_file = False

    def get_size(self):
        return 0

    def ls(self, indent=""):
        s = StringIO()
        #print self.keys()
        for key in self.keys():
            if self[key].is_file:
                #print "file: %s" % key
                s.write("%s%s\n" % (indent, key))
            else:
                #print "dir: %s" % key
                s.write("%s%s:\n" % (indent, key))
                contents = self[key].ls(indent + "  ")
                s.write(contents)
        return s.getvalue()

class MemFile(object):
    """Class representing stored files in the memory filesystem."""
    is_file = True

    def __init__(self, data):
        self.data = data

    def get_size(self):
        return len(self.data)

class TempFile(StringIO):
    """Temporary file-like object that stores itself in the filesystem
    when closed or deleted.
    """
    def __init__(self, folder, file_name, initial="", read_only=False):
        StringIO.__init__(self, initial)
        self.folder = folder
        self.file_name = file_name
        self._is_closed = False
        self._read_only = read_only

    def close(self):
        self._close()
        self._is_closed = True
        StringIO.close(self)

    def _close(self):
        if not self._read_only:
            #print "setting file %s to %s in %s" % (self.file_name, self.getvalue(), self.folder)
            self.folder[self.file_name] = MemFile(self.getvalue())

    def __del__(self):
        if not self._is_closed:
            self._close()

    def __enter__(self):
        # This is for use in 'with' statements; don't understand this
        # yet.
        return self

    def __exit__(self, type, value, traceback):
        # This is for use in 'with' statements; don't understand this
        # yet.
        pass

class MemFS(BaseFS):
    """Memory filesystem based on nested dictionaries.

    The mem: virtual filesystem represents a hierarchical filesystem
    entirely in memory using nested dictionaries as the storage
    mechanism.
    """

    # The rood of the filesystem
    root = MemDir()

    @staticmethod
    def _normalize_path(path):
        """Normalize the path to conform to the nested dict structure."""
        # FIXME: no interface in itools to set current working
        # directory?  Set '.' to '/'
        if path.startswith('.'):
            path = path[1:]

        # strip off leading '/'; root of / is implicit
        path = path.lstrip('/')
            
        while path.endswith('/'):
            path = path[:-1]
        #print "normalized: %s" % path
        return path

    @staticmethod
    def _find(path):
        """Find the item in the filesystem pointed to by the path

        path: string representing the pathname within the mem: filesystem
        
        returns: tuple of (parent_dict, item, name_in_parent).  If the
        path is valid, the returned item item can be a MemDir or a
        MemFile object.  If the path is invalid, item will be None.
        name_in_parent is the filename of the item stored in the
        parent_dict.
        """
        parent = None
        fs = MemFS.root
        #print fs

        path = MemFS._normalize_path(path)
        if not path:
            return parent, fs, path
        components = path.split('/')
        #print "components: %s" % components

        # Skip over the root level since it is implicit in the storage
        for comp in components:
            #print("path=%s comp=%s" % (path, comp))
            if fs.is_file:
                # if we've found a file but we've still got path
                # components left, return error
                return None, None, None
            if comp in fs:
                parent = fs
                fs = fs[comp]
            else:
                return parent, None, comp
        return parent, fs, comp

    @staticmethod
    def _makedirs(path):
        """Create nested dicts representing path.

        Create the hierarchy of nested dicts such that the entire path
        is represented in the filesystem.

        path: string representing the pathname
        """
        path = MemFS._normalize_path(path)
        if not path:
            return
        fs = MemFS.root
        components = path.split('/')
        for comp in components:
            if fs.is_file:
                raise OSError("[Errno 20] Not a directory: '%s'" % path)
            if comp in fs:
                fs = fs[comp]
            else:
                fs[comp] = MemDir()
                fs = fs[comp]
        if fs.is_file:
            raise OSError("[Errno 20] Not a directory: '%s'" % path)
        #print "filesystem: %s" % MemFS.root

    @staticmethod
    def exists(reference):
        path = str(reference.path)
        parent, item, name = MemFS._find(path)
        return item is not None

    @staticmethod
    def is_file(reference):
        path = str(reference.path)
        parent, item, name = MemFS._find(path)
        if item is not None:
            return item.is_file
        return False

    @classmethod
    def is_folder(cls, reference):
        path = str(reference.path)
        parent, item, name = MemFS._find(path)
        if item is not None:
            return not item.is_file
        return False

    @staticmethod
    def can_read(reference):
        return MemFS.is_file(reference)

    @staticmethod
    def can_write(reference):
        return MemFS.is_file(reference)

    @staticmethod
    def get_size(reference):
        path = str(reference.path)
        parent, item, name = MemFS._find(path)
        if item:
            return item.get_size()
        raise OSError("[Errno 2] No such file or directory: '%s'" % reference)


    @staticmethod
    def make_file(reference):
        #print reference
        folder_path = str(reference.path[:-1])
        file_path = str(reference.path)

        parent, item, dummy = MemFS._find(file_path)
        if parent is not None:
            if parent.is_file:
                raise OSError("[Errno 20] Not a directory: '%s'" % folder_path)
            if item is not None:
                raise OSError("[Errno 17] File exists: '%s'" % reference)
        else:
            #print "making folders: %s" % folder_path
            MemFS._makedirs(folder_path)
        
        file_name = reference.path.get_name()
        #print "folder=%s file=%s" % (folder_path, file_name)
        #print "filesystem: %s" % MemFS.root.ls()
        parent, folder, folder_name = MemFS._find(folder_path)
        if parent and parent.is_file:
            raise OSError("[Errno 20] Not a directory: '%s'" % folder_path)
        #print "file_name = %s" % file_name
        fh = TempFile(folder, file_name)
        return fh

    @staticmethod
    def make_folder(reference):
        path = str(reference.path)
        #print "folder=%s" % (path)
        #print "filesystem: %s" % MemFS.root.ls()
        MemFS._makedirs(path)

    @staticmethod
    def remove(reference):
        path = str(reference.path)

        parent, item, name = MemFS._find(path)
        #print "removing: %s, %s, %s" % (parent, item, name)
        if item is None:
            raise OSError("[Errno 2] No such file or directory: '%s'" % reference)
        if item.is_file:
            del parent[name]
        else:
            # we need to go up a level and remove the entire dict.
            folder_path = str(reference.path[:-1])
            grandparent, parent, grandparent_name = MemFS._find(folder_path)
            #print "removing directory: %s from %s, %s" % (parent, grandparent, name)
            del parent[name]

    @staticmethod
    def open(reference, mode=None):
        path = str(reference.path)
        parent, item, name = MemFS._find(path)
        if not parent:
            raise IOError("[Errno 20] Not a directory: '%s'" % reference)
        if not item:
            raise IOError("[Errno 2] No such file or directory: '%s'" % reference)

        file_name = reference.path[-1]

        if mode == WRITE:
            # write truncates
            fh = TempFile(parent, file_name, "")
        elif mode == APPEND:
            fh = TempFile(parent, file_name, item.data)
            fh.seek(item.get_size())
        elif mode is None:
            # Open for read/write, but don't position at end of file,
            # i.e. "r+b"
            fh = TempFile(parent, file_name, item.data)
        else:
            fh = TempFile(parent, file_name, item.data, True)
        return fh

    @staticmethod
    def move(source, target):
        # Fail if target exists and is a file
        tgtpath = str(target.path)
        parent, item, tgtname = MemFS._find(tgtpath)
        #print "move: %s, %s, %s" % (parent, item, tgtname)
        if item:
            if item.is_file:
                raise OSError("[Errno 20] Not a directory: '%s'" % target)
            dest = item
        else:
            # the target doesn't exist, so it must be the pathname of
            # the new item.
            tgtname = target.path[-1]
            #print "target=%s" % tgtname
            folder_path = str(target.path[:-1])
            MemFS._makedirs(folder_path)
            parent, dest, dummy = MemFS._find(folder_path)
        #print "dest=%s" % dest

        srcpath = str(source.path)
        srcdir, src, origname = MemFS._find(srcpath)
        if src:
            dest[tgtname] = src
            del srcdir[origname]
        else:
            raise OSError("[Errno 2] No such file or directory: '%s'" % source)

    ######################################################################
    # Folders only
    @classmethod
    def get_names(cls, reference):
        path = str(reference.path)
        parent, item, name = MemFS._find(path)
        if item.is_file:
            raise OSError("[Errno 20] Not a directory '%s'" % reference)
        #print item.keys()
        return item.keys()


register_file_system('mem', MemFS)