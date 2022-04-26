#!/usr/bin/env python2
# -*- coding: utf-8 -*-
from optparse import OptionParser
import logging
import multiprocessing as mp
import os
import app.async_server


def serve_http(port, root):
    logging.info("Worker with PID %s has started" % os.getpid())
    try:
        server = app.async_server.AsyncHttp(port, root)
        server.serve_forever()
    except Exception as e:
        logging.error(e)


if __name__ == "__main__":
    op = OptionParser()
    op.add_option("-w", "--workers", action="store", type="int", default=mp.cpu_count())
    op.add_option("-p", "--port", action="store", type="int", default=80)
    op.add_option("-r", "--root", action="store", default="./tests")
    (opts, args) = op.parse_args()
    logging.basicConfig(filename='wwwotus.log', level=logging.INFO, format='[%(process)d: %(asctime)s] %(levelname).1s %(message)s',
                        datefmt='%Y.%m.%d %H:%M:%S')
    pool = mp.Pool(processes=opts.workers)
    results = [pool.apply_async(serve_http, (opts.port, opts.root)) for _ in range(opts.workers)]
    while True:
        try:
            for r in results:
                r.wait(timeout=3)
        except KeyboardInterrupt:
            logging.info("Get exit command from keyboard. Trying to shutdown pool of workers...")
            pool.terminate()
            pool.join()
