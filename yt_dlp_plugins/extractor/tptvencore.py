from yt_dlp.extractor.common import InfoExtractor


class TPTVEncoreIE(InfoExtractor):
    _VALID_URL = r'https://tptvencore\.co\.uk/product/[a-z0-9\-]+-(?P<id>\d+)'
    BRIGHTCOVE_URL_TEMPLATE = 'http://players.brightcove.net/6272132012001/default_default/index.html?videoId=%s'

    def _real_extract(self, url):
        video_id = self._match_id(url)

        return {
            '_type': 'url_transparent',
            'id': video_id,
            'url': self.BRIGHTCOVE_URL_TEMPLATE % video_id,
        }
