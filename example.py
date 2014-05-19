# coding: utf-8

from scrapy_model import BaseFetcherModel, CSSField, XPathField, RedisCache


class TestFetcher(BaseFetcherModel):
    photo_url = XPathField('//*[@id="content"]/div[1]/table/tr[2]/td/a')

    nationality = CSSField(
        '#content > div:nth-child(1) > table > tr:nth-child(4) > td > a::text',
        takes_first=True,
        processor=lambda value: value.upper()  # it could be a list of funcs
    )

    links = CSSField(
        '#content > div:nth-child(11) > ul > li > a.external::attr(href)',
        auto_extract=True
    )

    def parse_photo_url(self, selector):
        return "http://en.m.wikipedia.org/{}".format(
            selector.xpath("@href").extract()[0]
        )

    def parse_name(self, selector):
        return selector.extract()[0]

    def post_parse(self):
        # executed after all parsers
        # you can load any data on to self._data
        # access self._data and self._fields for current data
        # self.selector contains original page
        # self.fetch() returns original html
        self._data.url = self.url


class DummyModel(object):
    """
    For tests only, it can be a model in your database ORM
    """


if __name__ == "__main__":
    from pprint import pprint

    fetcher = TestFetcher(cache_fetch=True,
                          cache=RedisCache,
                          cache_expire=1800)

    fetcher.url = "http://en.m.wikipedia.org/wiki/Guido_van_Rossum"

    # Mappings can be loaded from a json file
    # fetcher.load_mappings_from_file('path/to/file')
    fetcher.mappings['name'] = {
        "css": ("#section_0::text")
    }

    fetcher.parse()

    print "Fetcher holds the data"
    print fetcher._data.name
    pprint(fetcher._data)

    # How to populate an object
    print "Populating an object"
    dummy = DummyModel()

    fetcher.populate(dummy, fields=["name", "nationality"])
    # fields attr is optional
    print dummy.nationality
    pprint(dummy.__dict__)
