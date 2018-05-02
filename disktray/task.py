#!/usr/bin/env python
#
# Cloudlet Infrastructure for Mobile Computing
#   - Task Assistance
#
#   Author: Zhuo Chen <zhuoc@cs.cmu.edu>
#
#   Copyright (C) 2011-2013 Carnegie Mellon University
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import collections
import os

import cv2
from logzero import logger

from disktray import config, util


class Task(object):
    def __init__(self):
        self.current_state = "start"
        # how many consecutive frames an object has appeared
        self._cumulative_object_counters = collections.defaultdict(int)

    def _check_dangling(self, objects):
        trays = []
        levers = []
        for i in xrange(objects.shape[0]):
            if int(objects[i, -1] + 0.1) == config.LABELS.index('tray'):
                trays.append(objects[i, :])
            if (int(objects[i, -1] + 0.1) == config.LABELS.index('lever')) or (int(objects[i, -1] + 0.1) ==
                                                                               config.LABELS.index('leverside')):
                levers.append(objects[i, :])

        assert len(trays) == 1
        assert len(levers) == 1
        tray = trays[0]
        lever = levers[0]

        tray_width = tray[2] - tray[0]
        tray_height = tray[3] - tray[1]

        # the lever needs to roughly below the tray
        lever_right_the_left_edge = (tray[0] - 0.1 * tray_width) < lever[0] < (tray[0] + 0.2 * tray_width)
        lever_below_the_bottom_edge = (tray[3] - 0.1 * tray_height) < lever[1] < (
                tray[3] + 0.1 * tray_height)
        lever_left_the_tray_center = lever[2] < (tray[0] + 0.4 * tray_width)
        logger.debug("tray is at: {}".format(tray))
        logger.debug("lever is at: {}".format(lever))
        logger.debug("lever_right_the_left_edge? {}".format(lever_right_the_left_edge))
        logger.debug("lever_below_the_bottom_edge? {}".format(lever_below_the_bottom_edge))
        logger.debug("lever_left_the_tray_center? {}".format(lever_left_the_tray_center))
        return lever_right_the_left_edge and lever_below_the_bottom_edge and lever_left_the_tray_center

    def _check_tray_vertical(self, objects):
        """Check the tray is vertical. There must be at least one tray in objects.

        :param objects:
        :return:
        """
        trays = util.get_sorted_objects_by_category(objects, 'tray')
        assert len(trays) > 0
        tray = trays[0]
        tray_width = tray[2] - tray[0]
        tray_height = tray[3] - tray[1]
        assert tray_width >= 0
        assert tray_height >= 0

        tray_height_width_ratio = tray_height / float(tray_width)
        is_vertical = bool(tray_height_width_ratio > 1.2)
        logger.debug("tray height: {}, tray width: {}, tray_height / tray_width: {}".format(tray_height, tray_width,
                                                                                            tray_height_width_ratio))
        logger.debug("tray is vertical? {}".format(is_vertical))
        return is_vertical

    @staticmethod
    def _set_instruction(result, speech, image_name, video_name):
        result['speech'] = speech
        image_path = os.path.join(config.IMAGE_PATH_PREFIX, image_name)
        result['image'] = cv2.imread(image_path) if image_path else None
        if config.VIDEO_GUIDANCE:
            result['video'] = config.VIDEO_URL_PREFIX + video_name

    def get_instruction(self, objects):
        """
        Get instructions for the next state
        :param objects: [[x1, y1, x2, y2, confidence, cls_idx]]
        :return:
        """
        result = {'status': "success"}

        # the start
        if self.current_state == "start":
            self._set_instruction(result, "Put the tray on the table.", "tray.jpg", "tray.mp4")
            self.current_state = "nothing"
            return result

        # when no object is detected
        if len(objects) == 0:
            self._cumulative_object_counters.clear()
            return result

        # get the count of detected objects
        current_object_counts = {}
        for idx, object_name in enumerate(config.LABELS):
            object_cnt = sum(objects[:, -1] == idx)
            current_object_counts[object_name] = object_cnt

        # update the cumulative counter as well
        for object_name in config.LABELS:
            if current_object_counts[object_name] > 0:
                self._cumulative_object_counters[object_name] += 1
            else:
                self._cumulative_object_counters[object_name] = 0

        if self.current_state == "nothing":
            if self._cumulative_object_counters['tray'] == 3:
                self._set_instruction(result, "Good job. Now show me the lever", "lever.jpg",
                                      "lever.mp4")
                self.current_state = "lever"
        elif self.current_state == "lever":
            if self._cumulative_object_counters['lever'] == 3:
                self._set_instruction(result, "Good job. Now assemble the lever onto tray. Show me the vertical view.",
                                      "dangling.jpg",
                                      "dangling.mp4")
                self.current_state = "dangling"
        elif self.current_state == "dangling":
            if current_object_counts['tray'] == 1 and self._check_tray_vertical(objects):
                if current_object_counts['lever'] == 1 or current_object_counts['leverside'] == 1:
                    if self._check_dangling(objects):
                        self._set_instruction(result, "Find the cap and show me the side view with pin holding up",
                                              "cap.jpg",
                                              "cap.mp4"
                                              )
                        self.current_state = "cap"
                    else:
                        self._set_instruction(result, "The lever is misplaced. Please make sure it is secure.",
                                              "dangling.jpg", "dangling.mp4")
        elif self.current_state == "cap":
            if current_object_counts['arc'] == 1 and current_object_counts['pin'] == 1:
                self._set_instruction(result, "Excellent. Now assemble the cap onto the tray. Start from left to "
                                              "right. Show "
                                              "me a vertical view when done", "assembled.jpg",
                                      "assembled.mp4")
                self.current_state = "assembled"
        elif self.current_state == "assembled":
            if current_object_counts['assembled'] == 1:
                self._set_instruction(result, "Awesome. Show me a close-up view to see if the pin is at right place.",
                                      "pin.jpg",
                                      "pin.mp4"
                                      )
                self.current_state = "pin"
        elif self.current_state == "pin":
            if self._cumulative_object_counters['pin'] == 2:
                self._set_instruction(result, "Please place the pin into the slot.", "pin.jpg",
                                      "pin.mp4")
            elif self._cumulative_object_counters['slotpin'] == 2:
                self._set_instruction(result, "Fabulous. Now close the lever.",
                                      "clamped.jpg", "clamped.mp4")
                self.current_state = "clamped"
        elif self.current_state == "clamped":
            clamped_objects = util.get_sorted_objects_by_category(objects, 'clamped')
            if len(clamped_objects) > 0 and clamped_objects[0][-2] > 0.9:
                self._set_instruction(result, "Finished! Congraduations!", "finshed.jpg",
                                      "finished.mp4")
                self.current_state = "finished"

        if not config.VIDEO_GUIDANCE:
            if 'video' in result:
                del result['video']
        return result
