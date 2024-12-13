from os import path

import requests
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import (
    int_or_none,
    traverse_obj,
)


class Channel5IE(InfoExtractor):
    _VALID_URL = r'https://www\.channel5\.com/show/(?P<show>[a-z0-9\-]+)/(?P<season>[a-z0-9\-]+)/(?P<id>[a-z0-9\-]+)'
    _GEO_COUNTRIES = ['GB']
    _GUIDANCE = {
        'Guidance': 16,
        'GuidancePlus': 18,
    }

    def _real_extract(self, url):
        show, season, episode = self._match_valid_url(url).group('show', 'season', 'id')
        data = self._download_json(
            f'https://corona.channel5.com/shows/{show}/seasons/{season}/episodes/{episode}.json?platform=my5desktop',
            episode)

        info_dict = {
            **traverse_obj(data, {
                'id': 'id',
                'title': 'title',
                'description': 'm_desc',
                'series': 'sh_title',
                'series_number': ('sea_num', {int_or_none}),
                'episode_number': ('ep_num', {int_or_none}),
                'genres': (('genre',)),
            }),
            'age_limit': self._GUIDANCE.get(data['rat']),
        }

        script_dir = path.dirname(__file__)
        media = requests.get(
            'https://cassie-auth.channel5.com/api/v2/media/my5firetv/%s.json' % data['id'],
            headers={'X-Forwarded-For': self._x_forwarded_for_ip},
            cert=(path.join(script_dir, 'c5.cert'), path.join(script_dir, 'c5.key')),
        ).json()

        if asset := traverse_obj(media, ('assets', 0)):
            formats = []
            subtitles = {}

            for rendition in asset.get('renditions', []):
                formats.extend(self._extract_mpd_formats(rendition['url'], data['id']))

            if url := asset.get('subtitleurl'):
                subtitles['eng'] = [{'url': url}]

            return {
                **info_dict,
                'formats': formats,
                'subtitles': subtitles,
                **traverse_obj(asset, {
                    'duration': 'duration',
                    '_license_url': 'keyserver',
                }),
            }
