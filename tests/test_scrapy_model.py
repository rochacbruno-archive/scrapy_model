#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_scrapy_model
----------------------------------

Tests for `scrapy_model` module.
"""

import unittest

from example import TestFetcher, DummyModel


class TestScrapy_model(unittest.TestCase):

    def setUp(self):
        fetcher = TestFetcher(cache_fetch=True)
        fetcher.url = "http://en.m.wikipedia.org/wiki/Guido_van_Rossum"

        fetcher.mappings['name'] = {
            "css": ("#section_0::text")
        }

        fetcher.parse()
        self.fetcher = fetcher
        self.model = DummyModel()

    def test_fetched_correct_name(self):
        self.assertEquals(self.fetcher.name.value, u'Guido van Rossum')

    def test_name_in_data_is_the_same_in_fields(self):
        self.assertEquals(self.fetcher.name.value, self.fetcher._data.name)
if __name__ == '__main__':
    unittest.main()