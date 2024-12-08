from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import int_or_none


class UIE(InfoExtractor):
    _VALID_URL = r'https?://u\.co\.uk/shows/(?:[^/]+/)*(?P<id>\d+)'
    BRIGHTCOVE_URL_TEMPLATE = 'http://players.brightcove.net/1242911124001/0RyQs9qPh_default/index.html?videoId=%s'

    def _real_extract(self, url):
        video_id = self._match_id(url)
        webpage = self._download_webpage(url, video_id)
        app_link = self._html_search_meta('twitter:app:url:iphone', webpage, 'twitter url')
        house_number = self._search_regex(r'uktvplay://video/(\w+)/', app_link, 'house number')

        info = self._download_json(
            f'https://myapi.uktvapi.co.uk/brand/?platform_type=mobile&platform_name=ios&house_number={house_number}',
            video_id)
        episode = info['landing_episode']
        title = episode['name'] if not episode['hide_episode_title'] \
            else 'S%s E%d' %(episode['series_number'], episode['episode_number'])

        return {
            '_type': 'url_transparent',
            'id': video_id,
            'title': episode['brand_name'] + ' - ' + title,
            'url': self.BRIGHTCOVE_URL_TEMPLATE % episode['video_id'],
            'thumbnail': episode['image'],
            'description': episode['synopsis'],
            'duration': episode['content_duration'],
            'series': episode['brand_name'],
            'series_id': episode['brand_id'],
            'season_number': int_or_none(episode['series_number']),
            'season_id': episode['series_id'],
            'episode': episode['name'] if episode['hide_episode_title'] else None,
            'episode_number': episode['episode_number'],
            'episode_id': episode['id'],
            'ie_key': 'BrightcoveNew',
        }
