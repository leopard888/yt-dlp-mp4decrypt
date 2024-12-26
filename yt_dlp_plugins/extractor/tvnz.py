from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import (
    int_or_none,
    traverse_obj,
)


class TVNZIE(InfoExtractor):
    _VALID_URL = r'https://www\.tvnz\.co\.nz/(?P<id>[0-9a-z\-\/]+)'
    BRIGHTCOVE_URL_TEMPLATE = 'http://players.brightcove.net/%s/%s_default/index.html?videoId=%s'

    def _real_extract(self, url):
        video_id = self._match_id(url)
        data = self._download_json(
            'https://apis-public-prod.tech.tvnz.co.nz/api/v1/web/play/page/' + video_id, video_id)
        video = data['_embedded'][data['layout']['video']['href']]

        if video['type'] == 'showVideo':
            return {
                '_type': 'url_transparent',
                'id': video['videoId'],
                'url': self.BRIGHTCOVE_URL_TEMPLATE % (
                    video['publisherMetadata']['brightcoveAccountId'],
                    video['publisherMetadata']['brightcovePlayerId'],
                    video['publisherMetadata']['brightcoveVideoId']),
                **traverse_obj(video, {
                    'title': 'title',
                    'thumbnail': ('image', 'src'),
                    'description': 'synopsis',
                    'series': 'title',
                    'season_number': ('seasonNumber', {int_or_none}),
                    'episode_number': ('episodeNumber', {int_or_none}),
                }),
            }

        if video['type'] == 'sportVideo':
            return {
                '_type': 'url_transparent',
                'id': video['videoId'],
                'url': self.BRIGHTCOVE_URL_TEMPLATE % (
                    video['media']['accountId'], 'default', video['media']['id']),
                **traverse_obj(video, {
                    'title': ('phase'),
                    'alt_title': ('subtext'),
                    'description': ('description'),
                    'thumbnails': ('images', ..., {'url': ('src')}),
                    'series': ('title'),
                    'episode': ('phase'),
                }),
            }

        if video['type'] == 'newsVideo':
            return {
                '_type': 'url_transparent',
                'id': video['videoId'],
                'url': self.BRIGHTCOVE_URL_TEMPLATE % (
                    video['media']['accountId'], 'default', video['media']['id']),
                **traverse_obj(video, {
                    'title': ('title'),
                    'description': ('description'),
                    'thumbnails': ('images', ..., {'url': ('src')}),
                }),
            }
