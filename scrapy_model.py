# coding: utf-8

__all__ = ['BaseFetcherModel', 'CSSField', 'XPathField', 'RedisCache']

import json
import logging
import requests
from collections import Sequence
from redis import Redis
from redis.exceptions import ConnectionError
from scrapy.selector import Selector

logger = logging.getLogger(__name__)


class NoCache(object):
    def __init__(self, *args, **kwargs):
        pass

    def get(self, key):
        return None

    def set(self, key, value, expire=None):
        pass


class RedisCache(object):
    def __init__(self, *args, **kwargs):
        self.cache = Redis(*args, **kwargs)

    def get(self, key):
        try:
            return self.cache.get(key)
        except ConnectionError as e:
            logger.error("Cant connect to Redis server %s", e)
            return None

    def set(self, key, value, expire=None):
        try:
            self.cache.set(key, value, expire)
        except ConnectionError as e:
            logger.error("Cant connect to Redis server %s", e)


class Storage(dict):
    """
    A dict that accepts [keys] or .attributes
    >>> obj = Storage()
    >>> obj["name"] = "Bruno"
    >>> obj.company = "ACME"
    >>> obj.name == obj["name]
    >>> obj["company] == obj.company
    """

    def __getattr__(self, attr):
        return self.get(attr)

    def __setattr__(self, attr, value):
        self[attr] = value


class BaseField(object):
    """
    Base for other selector fields
    """

    def __init__(self, query,
                 auto_extract=False, takes_first=False, processor=None):
        self.query = query
        self.auto_extract = auto_extract
        self.takes_first = takes_first
        self.processor = processor or (lambda untouched_data: untouched_data)
        self._data = self.selector = self._raw_data = None

    @property
    def value(self):
        return self._data

    def _parse(self, selector):
        parsed = self.parse(selector)
        extracted = parsed.extract()
        if self.takes_first and len(extracted) > 0:
            for value in extracted:
                if value is not None and value != '':
                    return self._processor(value)
        elif self.auto_extract:
            return self._processor(extracted)
        return self._processor(parsed)

    def _processor(self, data):
        """
        runs the processor if defined
        processor can be a list of functions to be chained
        or a single function
        """
        if isinstance(self.processor, Sequence):
            for function in self.processor:
                data = function(data)
        else:
            data = self.processor(data)
        return data

    def parse(self, selector):
        raise NotImplementedError("Must be implemented in child class")

    def get_identifier(self):
        return getattr(self, 'identifier', "")

    def __repr__(self):
        return u"<{} - {} - {}>".format(
            self.__class__.__name__, self.get_identifier(), self._data
        )

    def __str__(self):
        return unicode(self._data)

    def __unicode__(self):
        return unicode(self._data)


class GenericField(BaseField):
    def __init__(self, identifier=None, value=None):
        super(GenericField, self).__init__("")
        self._data = value
        self.identifier = identifier

    def parse(self, selector):
        return None


class CSSField(BaseField):
    def parse(self, selector):
        return selector.css(self.query)


class XPathField(BaseField):
    def parse(self, selector):
        return selector.xpath(self.query)


class BaseFetcherModel(object):
    """
    fields example:
            name = CSSField("div.perfil > div > div.perf.col-md-12 >"
                            " div.col-md-10.desc > h1::text")
    mappings example:
        mappings = {
            'name': {'css': 'div#test'},
            'phone': {'xpath': '//phone'},
            'location': '.location'  # assumes css
        }


    Any method named parsed_<field_name> will run after the data is collected
    """

    mappings = {}

    def __init__(self, url=None, mappings=None,
                 cache_fetch=False,
                 cache=NoCache,
                 cache_args=None,
                 cache_expire=None):
        self.load_fields()
        self.url = url
        self.refresh = False
        self._data = Storage()
        self._selector = None
        self.mappings = mappings or self.mappings.copy()
        self.cache_fetch = cache_fetch
        self.cache_expire = cache_expire

        if isinstance(cache, type):
            self.cache = cache(**(cache_args or {}))
        else:
            self.cache = cache

    def load_fields(self):
        self._fields = []
        for name, field in self.__class__.__dict__.items():
            if isinstance(field, BaseField):
                field.identifier = name
                self._fields.append(field)

    def fetch(self, url=None):
        url = self.url or url
        cached = self.cache.get(url)
        if cached and self.cache_fetch:
            return cached
        response = requests.get(url)
        if self.cache_fetch:
            self.cache.set(url, response.content, expire=self.cache_expire)
        return response.content

    @property
    def selector(self):
        if not self._selector or self.refresh:
            self._selector = Selector(text=self.fetch())
            self.refresh = False
        return self._selector

    def parse(self, selector=None):
        """
        The entry point
        fetcher = Fetcher(url="http://...")
        fetcher.parse()
        """

        selector = selector or self.selector

        for field in self._fields:
            data = field._parse(selector)
            self._data[field.identifier] = field._raw_data = data

        # mappings has always the priority
        for field_name, query in self.mappings.items():
            if isinstance(query, dict):
                method = query.keys()[0]
                path = query.values()[0]
            else:
                method = 'css'
                path = query
            self._data[field_name] = getattr(selector, method)(path)

        self.run_field_parsers()

        for field in self._fields:
            field._data = field.selector = self._data.get(field.identifier)

        self.post_parse()

        self.load_generic_fields()

    def load_generic_fields(self):
        for k, v in self._data.items():
            if k not in self._fields:
                field = GenericField(k, v)
                self._fields.append(field)
                setattr(self, k, field)

    def post_parse(self):
        """
        To be implemented optionally in child classes
        """

    def run_field_parsers(self):
        self._raw_data = self._data.copy()
        for field_name, raw_selector in self._data.items():
            field_parser = getattr(self, 'parse_%s' % field_name, None)
            if field_parser:
                try:
                    parsed_data = field_parser(raw_selector)
                except Exception as e:
                    logger.error(
                        "Exception ocurred in parse_%s: %s", field_name, e
                    )
                    self._data[field_name] = raw_selector
                else:
                    self._data[field_name] = parsed_data

    def populate(self, obj, fields=None):
        fields = fields or self._data.keys()
        for field in fields:
            setattr(obj, field, self._data.get(field))

    def load_mappings_from_file(self, path_or_file):
        """
        Will take a JSON file object, string or path
        and loads on to self.mappings
         {
            'name': {'css': 'div#test'},
            'phone': {'xpath': '//phone'},
            'location': '.location'  # assumes css
         }
        """
        if isinstance(path_or_file, basestring):
            try:
                data = open(path_or_file).read()
            except IOError:
                data = path_or_file
        elif isinstance(path_or_file, file) or hasattr(path_or_file, 'read'):
            data = path_or_file.read()

        self.mappings.update(json.loads(data))
