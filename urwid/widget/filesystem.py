# Copyright (C) 2026 Urwid developers
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
# Urwid web site: https://urwid.org/

"""Directory listing policy shared by path completion and the file chooser, and the path completer itself."""

from __future__ import annotations

import dataclasses
import enum
import errno
import fnmatch
import os
import re
import stat
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence

    from _typeshed import SupportsRichComparison

__all__ = ("DirectoryReader", "FileEntry", "FileKind", "PathCompleter")

_DIGITS: typing.Final = re.compile(r"(\d+)")
_SEPARATORS: typing.Final = os.sep + (os.altsep or "")
# a reparse point that names another file, as a Windows junction or symbolic link does (IsReparseTagNameSurrogate)
_NAME_SURROGATE: typing.Final = 0x20000000
# st_file_attributes exists on Windows only
_FILE_ATTRIBUTE_HIDDEN: typing.Final = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0)


class FileKind(enum.Flag):
    """Kind of a directory entry, named after the :mod:`stat` ``S_IS*`` tests.

    The kind of a symbolic link is the kind of its target.

    >>> FileKind.FIFO in FileKind.SPECIAL
    True
    >>> FileKind.DIRECTORY in FileKind.FILE | FileKind.DIRECTORY
    True
    """

    FILE = enum.auto()
    DIRECTORY = enum.auto()
    BLOCK_DEVICE = enum.auto()
    CHAR_DEVICE = enum.auto()
    FIFO = enum.auto()
    SOCKET = enum.auto()
    #: A symbolic link whose target cannot be resolved: it is missing, a loop, or not permitted.
    BROKEN_LINK = enum.auto()
    #: Not known: the target is outside the root directory, or its metadata cannot be read.
    UNKNOWN = enum.auto()
    SPECIAL = BLOCK_DEVICE | CHAR_DEVICE | FIFO | SOCKET
    ANY = FILE | DIRECTORY | SPECIAL | BROKEN_LINK | UNKNOWN


def _kind(mode: int) -> FileKind:
    """Return the kind of the file whose ``st_mode`` is *mode*."""
    for test, kind in (
        (stat.S_ISREG, FileKind.FILE),
        (stat.S_ISDIR, FileKind.DIRECTORY),
        (stat.S_ISBLK, FileKind.BLOCK_DEVICE),
        (stat.S_ISCHR, FileKind.CHAR_DEVICE),
        (stat.S_ISFIFO, FileKind.FIFO),
        (stat.S_ISSOCK, FileKind.SOCKET),
    ):
        if test(mode):
            return kind
    return FileKind.UNKNOWN


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class FileEntry:
    """One directory entry, or one path looked up by :meth:`DirectoryReader.entry`.

    Paths are strings as the operating system gave them, so a name that is not valid in the file system encoding
    holds surrogate escapes.
    """

    #: The last component of :attr:`path`.
    name: str
    #: The path as listed or as looked up, not resolved.
    path: str
    #: The resolved path, or ``None`` when it cannot be resolved; for a missing name, the resolved parent and the name.
    resolved: str | None
    #: The kind of the entry, of the target for a symbolic link.
    kind: FileKind
    #: Whether the name exists. A dangling symbolic link exists.
    #: With :attr:`error` set by a failure other than resolution, it is not known and reads ``True``.
    exists: bool = True
    is_symlink: bool = False
    #: The target of a symbolic link as stored in it, or ``None``.
    link_target: str | None = None
    #: Whether the name starts with a dot, or carries the hidden attribute on Windows.
    hidden: bool = False
    #: The size of the target in bytes, ``None`` when unknown.
    size: int | None = None
    #: The modification time of the target in seconds since the epoch, ``None`` when unknown.
    mtime: float | None = None
    #: The error that left the entry incomplete, such as a missing permission or a broken link.
    error: OSError | None = None
    #: Whether the path is outside the root directory of the reader, judged on :attr:`resolved`,
    #: or on the path resolved as far as it exists when it does not resolve.
    outside_root: bool = False

    @property
    def display_name(self) -> str:
        """The name with every character that cannot be printed, or that was not decodable, replaced by U+FFFD.

        >>> FileEntry("a" + chr(9) + "b", "x", None, FileKind.FILE).display_name == "a" + chr(0xFFFD) + "b"
        True
        """
        if self.name.isprintable():
            return self.name
        return "".join(char if char.isprintable() else "�" for char in self.name)

    @property
    def editable(self) -> bool:
        """Whether the name can be written into an :class:`~urwid.Edit` and read back unchanged."""
        return self.name.isprintable()


class DirectoryReader:
    """The file system policy that path completion and the file chooser share.

    It decides which directory may be read, and which of its entries are visible:

    - *root_dir* limits reading to that directory and below it, judged on resolved paths.
      Every check is made on the :func:`os.path.realpath` of a path, never on a lexically normalised one.
    - *show* is a :class:`FileKind` or a predicate called with each :class:`FileEntry`.
    - *patterns* are :mod:`fnmatch` patterns that a name other than a directory has to match one of.
    - Hidden entries are listed only with *show_hidden*.

    The root limit guarantees that a directory outside the root is never enumerated.
    It is not a sandbox: an accepted path can change before the application opens it.

    :meth:`scan` is the only method that enumerates and :meth:`entry` the only one that looks up one path,
    so a subclass for another file system overrides those two.
    """

    __slots__ = ("__weakref__", "_patterns", "_root", "_root_dir", "_show", "show_hidden")

    def __init__(
        self,
        *,
        root_dir: str | os.PathLike[str] | None = None,
        show: FileKind | Callable[[FileEntry], bool] = FileKind.ANY,
        patterns: Iterable[str] = (),
        show_hidden: bool = False,
    ) -> None:
        """Create the reader; nothing is read until a method is called.

        :param root_dir: the directory nothing outside of is read or offered, ``None`` for no limit
        :param show: kinds of entries listed, or a predicate called with each entry
        :param patterns: :mod:`fnmatch` patterns for names other than directories; empty lists every name
        :param show_hidden: list hidden entries
        """
        self._root_dir = None if root_dir is None else os.fspath(root_dir)
        self._root: str | None = None
        self._show = show
        self._patterns = tuple(patterns)
        #: Whether :meth:`read` lists hidden entries by default.
        self.show_hidden = show_hidden

    @property
    def root_dir(self) -> str | None:
        """The resolved root directory, or ``None`` without a limit; resolved on first use."""
        if self._root_dir is not None and self._root is None:
            self._root = os.path.realpath(self._root_dir)
        return self._root

    @property
    def show(self) -> FileKind | Callable[[FileEntry], bool]:
        """Kinds of entries listed, or the predicate called with each entry."""
        return self._show

    @property
    def patterns(self) -> tuple[str, ...]:
        """:mod:`fnmatch` patterns that a name other than a directory has to match."""
        return self._patterns

    def resolve(self, path: str | os.PathLike[str]) -> str:
        """Return the resolved form of the existing *path*.

        :raises OSError: the path does not exist, a symbolic link in it loops, a component cannot be read,
            or the path holds a NUL character.
        """
        if "\0" in os.fspath(path):
            raise OSError(errno.EINVAL, "embedded null character in path", os.fspath(path))
        return os.path.realpath(path, strict=True)

    def contains(self, resolved: str) -> bool:
        """Return whether the resolved path *resolved* is the root directory or below it; always true without a root.

        A path that cannot be compared with the root, such as one on another Windows drive, is outside.
        """
        if (root := self.root_dir) is None:
            return True
        try:
            common = os.path.commonpath((root, resolved))
        except ValueError:
            return False
        return os.path.normcase(common) == os.path.normcase(root)

    def matches(self, entry: FileEntry) -> bool:
        """Return whether *entry* passes *show* and, unless it is a directory, *patterns*."""
        if isinstance(self._show, FileKind):
            if entry.kind not in self._show:
                return False
        elif not self._show(entry):
            return False
        return entry.kind == FileKind.DIRECTORY or self.name_matches(entry.name)

    def name_matches(self, name: str) -> bool:
        """Return whether *name* matches one of *patterns*; always true without patterns."""
        return not self._patterns or any(fnmatch.fnmatch(name, pattern) for pattern in self._patterns)

    def _visible(self, entry: FileEntry, show_hidden: bool) -> bool:
        """Return whether :meth:`read` lists *entry*."""
        if entry.hidden and not show_hidden:
            return False
        # an entry outside the root has no known kind, and the chooser shows it dimmed
        return entry.outside_root or entry.kind == FileKind.DIRECTORY or self.matches(entry)

    def _target(self, name: str, path: str, lstat: os.stat_result, resolved: str | None) -> FileEntry:
        """Build the entry of the existing *path*, reading the target's metadata only inside the root.

        :param lstat: the metadata of the name itself
        :param resolved: the resolved path; ``None`` when resolution failed
        """
        is_symlink = stat.S_ISLNK(lstat.st_mode)
        link_target = None
        if is_symlink:
            try:
                link_target = os.readlink(path)
            except OSError:
                link_target = None
        hidden = name.startswith(".") or bool(getattr(lstat, "st_file_attributes", 0) & _FILE_ATTRIBUTE_HIDDEN)
        base = FileEntry(
            name,
            path,
            resolved,
            FileKind.BROKEN_LINK if is_symlink else FileKind.UNKNOWN,
            is_symlink=is_symlink,
            link_target=link_target,
            hidden=hidden,
        )
        if resolved is None:
            return base
        if not self.contains(resolved):
            return dataclasses.replace(base, kind=FileKind.UNKNOWN, outside_root=True)
        if is_symlink:
            try:
                target = os.stat(resolved)
            except OSError as exc:
                return dataclasses.replace(base, kind=FileKind.UNKNOWN, error=exc)
        else:
            target = lstat
        return dataclasses.replace(base, kind=_kind(target.st_mode), size=target.st_size, mtime=target.st_mtime)

    def _entry_of_existing(self, name: str, path: str, lstat: os.stat_result) -> FileEntry:
        """Resolve the existing *path* and build its entry, keeping a resolution failure as its error."""
        try:
            resolved = self.resolve(path)
        except OSError as exc:
            if self._outside(path):  # whether an outside target exists is not told
                return dataclasses.replace(
                    self._target(name, path, lstat, None), kind=FileKind.UNKNOWN, outside_root=True
                )
            return dataclasses.replace(self._target(name, path, lstat, None), error=exc)
        return self._target(name, path, lstat, resolved)

    def _outside(self, path: str) -> bool:
        """Return whether *path*, resolved as far as it exists, is outside the root.

        A path that does not resolve is judged this way, so that a refusal for a path outside the root never
        tells whether it exists or can be read.
        """
        return not self.contains(os.path.realpath(path))

    def scan(self, directory: str) -> Iterator[FileEntry]:
        """Enumerate the resolved *directory*, unfiltered and unsorted.

        Per entry, the name's own metadata is read first and a failure there is kept as the entry's error.
        A symbolic link is resolved before its target is read, and a target outside the root is not read at all.

        :raises OSError: the directory cannot be listed.
        """
        with os.scandir(directory) as entries:
            for dir_entry in entries:
                try:
                    lstat = dir_entry.stat(follow_symlinks=False)
                except OSError as exc:
                    yield FileEntry(dir_entry.name, dir_entry.path, None, FileKind.UNKNOWN, error=exc)
                    continue
                # a Windows junction is a directory to lstat, but it leads elsewhere like a link
                reparse_tag: int = getattr(lstat, "st_reparse_tag", 0)
                if stat.S_ISLNK(lstat.st_mode) or reparse_tag & _NAME_SURROGATE:
                    yield self._entry_of_existing(dir_entry.name, dir_entry.path, lstat)
                else:
                    # the directory is resolved and the name is no link, so the path is resolved as well
                    yield self._target(dir_entry.name, dir_entry.path, lstat, dir_entry.path)

    def read(self, directory: str | os.PathLike[str], *, show_hidden: bool | None = None) -> list[FileEntry]:
        """Return the visible entries of *directory*, unsorted.

        Directories pass *show* and *patterns*; entries outside the root pass them too, to be shown as such.

        :param directory: the directory to list, resolved first
        :param show_hidden: list hidden entries; ``None`` uses :attr:`show_hidden`
        :raises PermissionError: the resolved directory is outside the root; nothing is listed.
        :raises OSError: the directory cannot be resolved or listed.
        """
        resolved = self.resolve(directory)
        if not self.contains(resolved):
            raise PermissionError(errno.EACCES, "outside the root directory", os.fspath(directory))
        hidden = self.show_hidden if show_hidden is None else show_hidden
        return [entry for entry in self.scan(resolved) if self._visible(entry, hidden)]

    def entry(self, path: str | os.PathLike[str]) -> FileEntry:
        """Look up *path*; never raises.

        A name that does not exist gives ``exists=False``, with :attr:`FileEntry.resolved` set when its parent
        resolves. Any other failure is kept in :attr:`FileEntry.error`.
        :attr:`FileEntry.outside_root` is set on every path, also one that does not resolve.
        """
        path = os.fspath(path)
        stripped = path.rstrip(_SEPARATORS) or path
        name = os.path.basename(stripped) or stripped
        if "\0" in path:  # os.lstat() raises ValueError for it
            return FileEntry(
                name, path, None, FileKind.UNKNOWN, error=OSError(errno.EINVAL, "embedded null character in path", path)
            )
        try:
            lstat = os.lstat(path)
        except FileNotFoundError:
            try:
                resolved = os.path.join(self.resolve(os.path.dirname(stripped) or os.curdir), name)
            except OSError:
                return FileEntry(name, path, None, FileKind.UNKNOWN, exists=False, outside_root=self._outside(path))
            return FileEntry(
                name, path, resolved, FileKind.UNKNOWN, exists=False, outside_root=not self.contains(resolved)
            )
        except OSError as exc:
            return FileEntry(name, path, None, FileKind.UNKNOWN, error=exc, outside_root=self._outside(path))
        return self._entry_of_existing(name, path, lstat)

    @staticmethod
    def name_key(name: str) -> tuple[str | int, ...]:
        """Return the default sort key of *name*: case-folded, with runs of digits compared as numbers.

        >>> sorted(["file10", "File9", "file1"], key=DirectoryReader.name_key)
        ['file1', 'File9', 'file10']
        """
        return tuple(int(part) if index % 2 else part for index, part in enumerate(_DIGITS.split(name.casefold())))


class PathCompleter:
    """Text completer of a path for :class:`~urwid.Edit`, see :attr:`~urwid.Edit.text_completer`.

    It completes the path component around the cursor from the entries of its directory that *reader* lists.
    Relative text is taken from :attr:`base_dir`.
    Characters such as ``*`` are literal; a leading ``~`` is expanded for reading and kept as typed.

    One Tab gives, in this order:

    - nothing when no entry matches, so that Tab moves the focus;
    - the whole entry when one matches, with a separator after a directory;
    - the longest common start of the matches when it is longer than what was typed;
    - otherwise each match in turn, as a completion cycle.

    Entries outside the root and names that cannot be typed back are never offered.
    Only directories are offered before a further component, or with *only_directories*.
    """

    __slots__ = ("__weakref__", "_base_dir", "_only_directories", "_reader", "expanduser", "sort_key")

    def __init__(
        self,
        reader: DirectoryReader | None = None,
        *,
        base_dir: str | os.PathLike[str] | None = None,
        only_directories: bool = False,
        expanduser: bool = True,
        sort_key: Callable[[FileEntry], SupportsRichComparison] | None = None,
    ) -> None:
        """Create the completer.

        :param reader: the listing policy; ``None`` lists every entry without a root limit
        :param base_dir: the directory relative text is taken from; ``None`` is the working directory
        :param only_directories: offer directories only
        :param expanduser: expand a leading ``~`` for reading
        :param sort_key: ``sort_key(entry)`` ordering the matches; ``None`` orders by :meth:`DirectoryReader.name_key`
        """
        self._reader = DirectoryReader() if reader is None else reader
        self._base_dir = None if base_dir is None else os.fspath(base_dir)
        self._only_directories = only_directories
        #: Whether a leading ``~`` is expanded for reading.
        self.expanduser = expanduser
        #: ``sort_key(entry)`` ordering the matches, or ``None`` for :meth:`DirectoryReader.name_key`.
        self.sort_key = sort_key

    @property
    def reader(self) -> DirectoryReader:
        """The listing policy."""
        return self._reader

    @property
    def base_dir(self) -> str | None:
        """The directory relative text is taken from; ``None`` is the working directory."""
        return self._base_dir

    @base_dir.setter
    def base_dir(self, base_dir: str | os.PathLike[str] | None) -> None:
        self._base_dir = None if base_dir is None else os.fspath(base_dir)

    @property
    def only_directories(self) -> bool:
        """Whether only directories are offered."""
        return self._only_directories

    def _directory(self, typed: str) -> str:
        """Return the directory to read for the typed directory part *typed* of the text."""
        if self.expanduser and typed.startswith("~"):
            typed = os.path.expanduser(typed)
        base = os.curdir if self._base_dir is None else self._base_dir
        return os.path.join(base, typed) if typed else base

    def _candidates(self, directory: str, prefix: str, *, directories: bool) -> list[FileEntry]:
        """Return the sorted entries of *directory* that complete *prefix*, directories only with *directories*."""
        try:
            entries = self._reader.read(directory, show_hidden=True if prefix.startswith(".") else None)
        except OSError:
            return []
        folded = os.path.normcase(prefix)
        found = [
            entry
            for entry in entries
            if os.path.normcase(entry.name).startswith(folded)
            and not entry.outside_root
            and entry.editable
            and (entry.kind == FileKind.DIRECTORY or not directories)
        ]
        order = self.sort_key or (lambda entry: self._reader.name_key(entry.name))
        return sorted(found, key=lambda entry: (order(entry), entry.name))

    def __call__(self, text: str, pos: int) -> Sequence[tuple[str, int]]:
        """Return the completions of the component of *text* around *pos*, as ``(text, position)`` pairs."""
        start = max(text.rfind(sep, 0, pos) for sep in _SEPARATORS) + 1
        end = min((index for sep in _SEPARATORS if (index := text.find(sep, pos)) >= 0), default=len(text))
        prefix = text[start:pos]
        later = end < len(text)
        found = self._candidates(
            self._directory(text[:start]),
            prefix,
            directories=self._only_directories or later,
        )
        if not found:
            return []
        # the separator the text already uses, else the platform's own
        separator = text[start - 1] if start else os.sep

        def whole(entry: FileEntry) -> tuple[str, int]:
            """Return the text with the component replaced by *entry*, and the cursor after it."""
            component = entry.name
            cursor = start + len(component)
            if entry.kind == FileKind.DIRECTORY:
                if later:
                    cursor += 1  # after the separator that is already there
                else:
                    component += separator
                    cursor += 1
            return text[:start] + component + text[end:], cursor

        if len(found) == 1:
            return [whole(found[0])]
        # the common start of every name is the common start of the first and the last name in string order,
        # compared as the matching compares names and inserted as the first match spells it
        folded = [os.path.normcase(entry.name) for entry in found]
        first, last = min(folded), max(folded)
        common = next((index for index, (a, b) in enumerate(zip(first, last, strict=False)) if a != b), len(first))
        if common > len(prefix):
            inserted = found[0].name[len(prefix) : common]
            return [(text[:pos] + inserted + text[pos:], pos + len(inserted))]
        return [whole(entry) for entry in found]
