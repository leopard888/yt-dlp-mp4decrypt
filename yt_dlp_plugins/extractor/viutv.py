import json

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import (
    ExtractorError,
    traverse_obj,
)


class ViuTVIE(InfoExtractor):
    _VALID_URL = r'https://viu\.tv/encore/(?P<id>[a-z0-9\-]+)(?:/(?P<episode>[a-z0-9\-]+))?'

    def _real_extract(self, url):
        programme_slug, video_slug = self._match_valid_url(url).group('id', 'episode')
        programme_data = self._download_json(
            f'https://api.viu.tv/production/programmes/{programme_slug}', programme_slug)['programme']

        if video_slug:
            if episode := next(ep for ep in programme_data['episodes'] if ep['slug'] == video_slug):
                return self._get_episode(episode)

            raise ExtractorError('Content not found')

        def get_entries():
            for episode in programme_data['episodes']:
                yield self._get_episode(episode)

        return {
            '_type': 'playlist',
            'id': programme_slug,
            'title': programme_data['title'],
            'description': programme_data['synopsis'],
            'cast': traverse_obj(programme_data, ('programmeMeta', 'actors', ..., 'name')),
            'genres': traverse_obj(programme_data, ('genres', ..., 'name')),
            'thumbnail': programme_data['avatar'],
            'entries': get_entries(),
        }

    def _get_episode(self, episode):
        vod = self._download_json(
            'https://api.viu.now.com/p8/3/getVodURL', episode['productId'],
            data=json.dumps({
                'contentId': episode['productId'],
                'contentType': 'Vod',
                'deviceType': 'ANDROID_WEB',
            }).encode(),
        )

        if '.m3u8' in vod['asset'][0]:
            formats, subtitles = self._extract_m3u8_formats_and_subtitles(vod['asset'][0], episode['productId'])
        else:
            formats, subtitles = self._extract_mpd_formats_and_subtitles(vod['asset'][0], episode['productId'])

        return {
            'id': episode['productId'],
            'title': episode['episodeNameU3'],
            'formats': formats,
            'subtitles': subtitles,
            'thumbnail': episode['avatar'],
            'description': episode['program_synopsis'],
            'cast': traverse_obj(episode, ('videoMeta', 'actors', ..., 'name')),
            'genres': traverse_obj(episode, ('programmeMeta', 'genre', ..., 'name')),
            'duration': episode['totalDurationSec'],
            'series': episode['program_title'],
            'episode': episode['episodeNameU3'],
            'episode_number': episode['episodeNum'],
            '_cenc_key': '91ba752a446148c68400d78374b178b4:a01d7dc4edf582496b7e73d67e9e6899',
        }
