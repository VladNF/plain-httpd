import asynchat
import datetime
import logging
import mimetypes
import os
import types
from urllib import parse


class BaseHttpHandler(object):
    """
    Base class for handling http requests. Basically, it provides generic functionality
    for main headers, checking url for escapings, query strings and url-encoded symbols
    """

    def __init__(self, url, root="./"):
        self.url = os.path.realpath(os.path.join(root, parse.unquote(url)))
        self.root = os.path.join(os.path.realpath(root), "")
        self.code = 200
        self.error = ""
        self.qs = ""

    def base_headers_lines(self):
        yield "Date: %s\r\n" % datetime.datetime.now()
        yield "Server: Plain HTTP Server 2019.0.1\r\n"
        yield "Connection: close\r\n"

    def specific_headers_lines(self):
        yield b""

    def payload_object(self):
        if self.code != 200:
            yield self.error
        else:
            yield b""

    def in_root(self, path):
        path = os.path.realpath(path)
        return os.path.commonprefix([path, self.root]) == self.root

    def verify_request(self):
        if self.code != 200:
            return False

        # query strings removal
        if "?" in self.url:
            self.url, self.qs = self.url.split("?", 1)

        # escaping the path is forbidden
        if not self.in_root(self.url):
            self.code = 403
            self.error = "Forbidden"

        return self.code == 200

    def response_lines(self):
        self.verify_request()
        yield "HTTP/1.0 %s OK\r\n" % self.code
        yield self.base_headers_lines()
        yield self.specific_headers_lines()
        yield "\r\n"
        yield self.payload_object()
        yield None  # indicate to finish response


class GetRequestHandler(BaseHttpHandler):
    """
    GET request handler. Sends files with FileProducer object
    """

    def verify_request(self):
        if not super(GetRequestHandler, self).verify_request():
            return False

        if os.path.isdir(self.url):
            self.url = os.path.join(self.url, "index.html")

        if not os.path.exists(self.url):
            self.code = 404
            self.error = "File %s not found \r\n" % self.url

        return self.code == 200

    def specific_headers_lines(self):
        if self.code != 200:
            yield "Content-Type: text/plain\r\n"
            return

        type, encoding = mimetypes.guess_type(self.url)
        size = os.path.getsize(self.url)
        yield "Content-Length: %s\r\n" % size
        yield "Content-Type: %s\r\n" % type

    def payload_object(self):
        return FileProducer(self.url) if self.code == 200 else self.error


class HeadRequestHandler(GetRequestHandler):
    def payload_object(self):
        yield ""


class AsyncHttpHandler(asynchat.async_chat):
    def __init__(self, client_so=None, root="./"):
        asynchat.async_chat.__init__(self, client_so)
        self.root = root
        self.data = []
        self.got_headers = False
        self.set_terminator(b"\r\n\r\n")

    def collect_incoming_data(self, data):
        if not self.got_headers:
            self.data.append(data)

    def found_terminator(self):
        self.got_headers = True
        header_data = b"".join(self.data)
        header_text = header_data.decode("latin-1")
        header_lines = header_text.splitlines()
        request = header_lines[0].split()
        verb = request[0]
        url = request[1][1:]
        logging.info("Request: %s" % header_lines[0])
        self.process_request(verb, url)

    def push_text(self, text):
        logging.info("Response: %s" % text.strip("\r\n"))
        self.push(text.encode("latin-1"))

    def push_bytes(self, byte_text):
        logging.info("Response: %s" % byte_text.strip(b"\r\n"))
        self.push(byte_text)

    def write_response(self, response_lines):
        for o in response_lines:
            if o is None:
                continue
            elif isinstance(o, str):
                self.push_text(o)
            elif isinstance(o, bytes):
                self.push_bytes(o)
            elif isinstance(o, types.GeneratorType):
                self.write_response(o)
            elif hasattr(o, "more"):
                self.push_with_producer(o)
            else:
                raise ValueError()

    def process_request(self, verb, url):
        if verb == "GET":
            self.push_with_producer(
                GeneratorProducer(
                    self, GetRequestHandler(url, self.root).response_lines()
                )
            )
        elif verb == "HEAD":
            self.push_with_producer(
                GeneratorProducer(
                    self, HeadRequestHandler(url, self.root).response_lines()
                )
            )
        else:
            self.send_error(405, "%s method is not implemented" % verb)
            self.close_when_done()

    def send_error(self, code, message):
        err_handler = BaseHttpHandler("")
        err_handler.code = code
        err_handler.error = message
        self.write_response(err_handler.response_lines())


class GeneratorProducer(object):
    def __init__(self, chat, generator):
        self.chat = chat
        self.generator = generator

    def more(self):
        try:
            o = self.get_next()
            return o
        except Exception as e:
            logging.error(e)
            return None

    def get_next(self):
        try:
            o = next(self.generator)
            while True:
                if o is None:
                    self.chat.producer_fifo.append(None)
                    return None
                elif isinstance(o, str):
                    return o.encode("latin-1")
                elif isinstance(o, types.GeneratorType):
                    self.chat.producer_fifo.append(GeneratorProducer(self.chat, o))
                    self.chat.producer_fifo.append(
                        GeneratorProducer(self.chat, self.generator)
                    )
                    return None
                elif hasattr(o, "more"):
                    self.chat.producer_fifo.append(o)
                    return None
                elif o == b"":
                    continue
                else:
                    raise ValueError()
        except StopIteration:
            return None


class FileProducer(object):
    def __init__(self, filename, buf_size=512):
        self.f = open(filename, "rb")
        self.buf_size = buf_size

    def more(self):
        data = self.f.read(self.buf_size)
        if not data:
            self.f.close()

        return data
