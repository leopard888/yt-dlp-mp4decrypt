import json

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import (
    parse_duration,
    traverse_obj,
)


class ITVXIE(InfoExtractor):
    _VALID_URL = r'https://www\.itv\.com/watch/(?:[^/]+/)+(?P<id>[0-9a-zA-Z]+)'

    def _real_extract(self, url):
        video_id = self._match_id(url)
        webpage = self._download_webpage(url, video_id)
        props = self._search_nextjs_data(webpage, video_id)['props']['pageProps']

        if 'episode' in props:
            return self._get_episode(props['episode'], video_id)

        if programme := props.get('programme'):

            def get_entries():
                for series in props['seriesList']:
                    for episode in series['titles']:
                        yield self._get_episode(episode, video_id)

            return {
                '_type': 'playlist',
                'id': video_id,
                'title': programme['title'],
                'description': programme['longDescription'],
                'entries': get_entries(),
            }

    def _get_episode(self, episode, video_id):
        data = self._download_json(
            episode['playlistUrl'], video_id,
            data=json.dumps({
                'client': {
                    'version': '4.1',
                    'id': 'browser',
                    'supportsAdPods': False,
                },
                'device': {
                    'manufacturer': 'Chrome',
                    'model': '131.0.0.0',
                    'os': {
                        'name': 'Windows',
                        'version': '10',
                        'type': 'desktop',
                    },
                },
                'variantAvailability': {
                    'featureset': {
                        'min': ['mpeg-dash', 'widevine', 'outband-webvtt'],
                        'max': ['mpeg-dash', 'widevine', 'outband-webvtt'],
                    },
                    'platformTag': 'dotcom',
                },
            }).encode(),
            headers={
                'Accept': 'application/vnd.itv.vod.playlist.v2+json',
                'Content-Type': 'application/json',
            })

        info_dict = {
            'id': traverse_obj(episode, ('encodedEpisodeId', 'letterA')),
            'title': traverse_obj(episode, 'episodeTitle', 'heroCtaLabel'),
            'description': traverse_obj(episode, 'synopsis', 'longDescription'),
            'release_year': episode.get('productionYear'),
            'series_number': episode.get('series'),
            'episode_number': episode.get('episode'),
            'duration': parse_duration(traverse_obj(data, ('Playlist', 'Video', 'Duration'))),
            'thumbnail': episode['image'].format(width=1920, height=1080, quality=100, blur=0, bg='false'),
        }

        if files := traverse_obj(data, ('Playlist', 'Video', 'MediaFiles')):
            for file in files:
                if '.mp4' in file['Href']:
                    info_dict['url'] = file['Href']
                else:
                    info_dict.update({
                        'formats': self._extract_mpd_formats(
                            data['Playlist']['Video']['Base'] + file['Href'], video_id),
                        'subtitles': {'eng': traverse_obj(
                            data, ('Playlist', 'Video', 'Subtitles', ..., {'url': ('Href')}))},
                        '_license_url': file['KeyServiceUrl'],
                    })

        return info_dict
