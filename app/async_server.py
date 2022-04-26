import asyncore
import logging
import errno
import select
import socket
import time

from . import async_handler

"""
The code of polling functions below is adapted from 
https://github.com/m13253/python-asyncore-epoll/blob/master/asyncore_epoll.py
"""


def select_poller(timeout=0.0, map=None):
    """A poller which uses select(), available on most platforms."""
    if map is None:
        map = asyncore.socket_map
    if map:
        r = []
        w = []
        e = []
        for fd, obj in list(map.items()):
            is_r = obj.readable()
            is_w = obj.writable()
            if is_r:
                r.append(fd)
            # accepting sockets should not be writable
            if is_w and not obj.accepting:
                w.append(fd)
            if is_r or is_w:
                e.append(fd)
        if [] == r == w == e:
            time.sleep(timeout)
            return

        try:
            r, w, e = select.select(r, w, e, timeout)
        except select.error as err:
            if err.args[0] != errno.EINTR:
                raise
            else:
                return

        for fd in r:
            obj = map.get(fd)
            if obj is None:
                continue
            asyncore.read(obj)

        for fd in w:
            obj = map.get(fd)
            if obj is None:
                continue
            asyncore.write(obj)

        for fd in e:
            obj = map.get(fd)
            if obj is None:
                continue
            asyncore._exception(obj)


def poll_poller(timeout=0.0, map=None):
    """A poller which uses poll(), available on most UNIXen."""
    if map is None:
        map = asyncore.socket_map
    if timeout is not None:
        # timeout is in milliseconds
        timeout = int(timeout * 1000)
    pollster = select.poll()
    if map:
        for fd, obj in list(map.items()):
            flags = 0
            if obj.readable():
                flags |= select.POLLIN | select.POLLPRI
            # accepting sockets should not be writable
            if obj.writable() and not obj.accepting:
                flags |= select.POLLOUT
            if flags:
                pollster.register(fd, flags)
        try:
            r = pollster.poll(timeout)
        except select.error as err:
            if err.args[0] != errno.EINTR:
                raise
            r = []
        for fd, flags in r:
            obj = map.get(fd)
            if obj is None:
                continue
            asyncore.readwrite(obj, flags)


def epoll_poller(timeout=0.0, map=None):
    """A poller which uses epoll(), supported on Linux 2.5.44 and newer."""
    if map is None:
        map = asyncore.socket_map
    pollster = select.epoll()
    if map:
        for fd, obj in map.items():
            flags = 0
            if obj.readable():
                flags |= select.POLLIN | select.POLLPRI
            if obj.writable():
                flags |= select.POLLOUT
            if flags:
                # Only check for exceptions if object was either readable
                # or writable.
                flags |= select.POLLERR | select.POLLHUP | select.POLLNVAL
                pollster.register(fd, flags)
        try:
            r = pollster.poll(timeout)
        except select.error as err:
            if err.args[0] != errno.EINTR:
                raise
            r = []
        for fd, flags in r:
            obj = map.get(fd)
            if obj is None:
                continue
            asyncore.readwrite(obj, flags)


def loop(timeout=30.0, use_poll=False, map=None, count=None, poller=select_poller):
    if map is None:
        map = asyncore.socket_map
    # code which grants backward compatibility with "use_poll"
    # argument which should no longer be used in favor of
    # "poller"
    if use_poll and hasattr(select, "epoll"):
        logging.info("-------- Using epoll for the processing loop")
        poller = epoll_poller
    elif use_poll and hasattr(select, "poll"):
        logging.info("-------- Using poll for the processing loop")
        poller = poll_poller
    else:
        logging.info("-------- Using select for the processing loop")
        poller = select_poller

    if count is None:
        while map:
            poller(timeout, map)
    else:
        while map and count > 0:
            poller(timeout, map)
            count = count - 1


class AsyncHttp(asyncore.dispatcher):
    def __init__(self, port, root):
        asyncore.dispatcher.__init__(self)
        self.root = root
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.bind(("", port))
        self.listen(5)

    def handle_accept(self):
        try:
            client_so, addr = self.accept()
        except Exception as e:
            logging.error(e)
            raise

        logging.info("Accepted connection %s", client_so.fileno())
        return async_handler.AsyncHttpHandler(client_so, self.root)

    def serve_forever(self):
        try:
            loop(use_poll=True)
        except Exception as e:
            logging.error(e)
