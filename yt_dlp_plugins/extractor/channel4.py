import base64
import json

from yt_dlp.aes import aes_cbc_decrypt_bytes
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import traverse_obj


class Channel4IE(InfoExtractor):
    _VALID_URL = r'https://www\.channel4\.com/programmes/[a-z0-9\-]+/on-demand/(?P<id>[a-z0-9\-]+)'
    _GEO_COUNTRIES = ['GB']

    def _real_extract(self, url):
        video_id = self._match_id(url)
        content = self._download_json(f'https://www.channel4.com/vod/stream/{video_id}', video_id)
        formats = []
        dashwv_stream = None

        for profile in content['videoProfiles']:
            for stream in profile['streams']:
                if profile['name'].startswith('hls'):
                    formats.extend(self._extract_m3u8_formats(stream['uri'], video_id))
                elif profile['name'].startswith('dash'):
                    formats.extend(self._extract_mpd_formats(stream['uri'], video_id))

                if profile['name'].startswith('dashwv'):
                    dashwv_stream = stream

        def license_callback(challenge):
            license_url, token = aes_cbc_decrypt_bytes(
                base64.b64decode(dashwv_stream['token']),
                b'\x6e\x39\x63\x4c\x69\x65\x59\x6b\x71\x77\x7a\x4e\x43\x71\x76\x69',
                b'\x6f\x64\x7a\x63\x55\x33\x57\x64\x55\x69\x58\x4c\x75\x63\x56\x64',
            ).decode('ascii').split('|')

            resp = self._download_json(
                license_url, video_id,
                data=json.dumps({
                    'token': token,
                    'video': {'type': 'ondemand', 'url': dashwv_stream['uri']},
                    'message': base64.b64encode(challenge).decode(),
                }).encode(),
                headers={'Content-Type': 'application/json'})

            return base64.b64decode(resp['license'])

        return {
            'id': video_id,
            'formats': formats,
            **traverse_obj(content, {
                'title': ('episodeTitle'),
                'duration': ('duration'),
                'age_limit': ('rating'),
                'description': ('description'),
                'series': ('brandTitle'),
                'subtitles': {'eng': ('subtitlesAssets', ..., {'url': ('url')})},
            }),
            '_license_callback': license_callback,
        }
