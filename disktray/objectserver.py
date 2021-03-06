#!/usr/bin/env python2
# Copyright (C) 2018 Carnegie Mellon University. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Object Detection Server."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import select
import socket
import struct
import sys
import threading
import time
import traceback

import cv2
import gabriel

from disktray import caffedetect
from disktray import config
from disktray import zhuocv as zc

config.setup(is_streaming=True)

LOG = gabriel.logging.getLogger(__name__)
LOG_TAG = "Disktray: "

display_list = config.DISPLAY_LIST


class IkeaProcessing(threading.Thread):
    def __init__(self):
        self.stop = threading.Event()
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.server.bind(("", config.TASK_SERVER_PORT))
        self.server.listen(10)  # actually we are only expecting one connection...

        threading.Thread.__init__(self, target=self.run)

    def run(self):
        input_list = [self.server]
        output_list = []
        error_list = []

        LOG.info(LOG_TAG + "DiskTray object processing thread started")
        try:
            while (not self.stop.wait(0.001)):
                inputready, outputready, exceptready = \
                    select.select(input_list, output_list, error_list, 0.001)
                for s in inputready:
                    if s == self.server:
                        LOG.debug(LOG_TAG + "client connected")
                        client, address = self.server.accept()
                        input_list.append(client)
                        output_list.append(client)
                        error_list.append(client)
                    else:
                        self._receive(s)
        except Exception as e:
            LOG.warning(LOG_TAG + traceback.format_exc())
            LOG.warning(LOG_TAG + "%s" % str(e))
            LOG.warning(LOG_TAG + "handler raises exception")
            LOG.warning(LOG_TAG + "Server is disconnected unexpectedly")
        LOG.debug(LOG_TAG + "DiskTray object processing thread terminated")

    @staticmethod
    def _recv_all(socket, recv_size):
        data = ''
        while len(data) < recv_size:
            tmp_data = socket.recv(recv_size - len(data))
            if tmp_data == None or len(tmp_data) == 0:
                raise Exception("Socket is closed")
            data += tmp_data
        return data

    def _receive(self, sock):
        try:
            img_size = struct.unpack("!I", self._recv_all(sock, 4))[0]
            img = self._recv_all(sock, img_size)
        except Exception as e:
            return
        cv_img = zc.raw2cv_image(img)
        return_data = self._handle_img(cv_img)

        packet = struct.pack("!I%ds" % len(return_data), len(return_data), return_data)
        sock.sendall(packet)

    def _handle_img(self, img):
        # preprocessing of input image
        resize_ratio = 1
        if max(img.shape) > config.IMAGE_MAX_WH:
            resize_ratio = float(config.IMAGE_MAX_WH) / max(img.shape[0], img.shape[1])
            img = cv2.resize(img, (0, 0), fx=resize_ratio, fy=resize_ratio, interpolation=cv2.INTER_AREA)
        # get current state
        rtn_msg, state = caffedetect.process(img, confidence_threshold=config.CONFIDENCE_THRESHOLD,
                                             nms_threshold=config.NMS_THRESHOLD, resize_ratio=resize_ratio,
                                             display_list=display_list)
        if state is None:
            return "None"

        return state

    def terminate(self):
        self.stop.set()


def main():
    # a thread to receive incoming images
    ikea_processing = IkeaProcessing()
    ikea_processing.start()
    ikea_processing.isDaemon = True

    try:
        while True:
            time.sleep(1)
    except Exception as e:
        pass
    except KeyboardInterrupt as e:
        sys.stdout.write("user exits\n")
    finally:
        if ikea_processing is not None:
            ikea_processing.terminate()


if __name__ == "__main__":
    main()
