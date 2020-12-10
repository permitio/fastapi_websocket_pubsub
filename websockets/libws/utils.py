import datetime
import os
import re
import uuid
from datetime import timedelta
from random import SystemRandom, randrange

__author__ = 'OrW'


class RandomUtils(object):
    @staticmethod
    def gen_cookie_id():
        return os.urandom(16).encode('hex')

    @staticmethod
    def gen_uid():
        return uuid.uuid4().hex

    @staticmethod
    def gen_token(size=256):
        if size % 2 != 0:
            raise ValueError("Size in bits must be an even number.")
        return uuid.UUID(int=SystemRandom().getrandbits(size/2)).hex + \
            uuid.UUID(int=SystemRandom().getrandbits(size/2)).hex

    @staticmethod
    def random_datetime(start=None, end=None):
        """
        This function will return a random datetime between two datetime
        objects.
        If no range is provided - a last 24-hours range will be used
        :param datetime,None start: start date for range, now if None
        :param datetime,None end: end date for range, next 24-hours if None
        """
        # build range
        now = datetime.datetime.now()
        start = start or now
        end = end or now + timedelta(hours=24)
        delta = end - start
        int_delta = (delta.days * 24 * 60 * 60) + delta.seconds
        # Random time
        random_second = randrange(int_delta)
        # Return random date
        return start + timedelta(seconds=random_second)


gen_uid = RandomUtils.gen_uid
gen_token = RandomUtils.gen_token


class StringUtils(object):
    @staticmethod
    def convert_camelcase_to_underscore(name, lower=True):
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        res = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
        if lower:
            return res.lower()
        else:
            return res.upper()
