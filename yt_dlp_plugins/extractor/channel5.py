import os

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import (
    int_or_none,
    traverse_obj,
)


class Channel5IE(InfoExtractor):
    _VALID_URL = r'https://www\.channel5\.com/(?:show/)?(?P<show>[a-z0-9\-]+)/(?P<season>[a-z0-9\-]+)(?:/(?P<id>[a-z0-9\-]+))?'
    _GEO_COUNTRIES = ['GB']
    _API_BASE = 'https://cassie-auth.channel5.com/api/v2/media'
    _GUIDANCE = {
        'Guidance': 16,
        'GuidancePlus': 18,
    }

    def set_downloader(self, downloader):
        super().set_downloader(downloader)

        if downloader:
            self._add_handler(downloader._request_director)

    def _real_extract(self, url):
        show, season, episode = self._match_valid_url(url).group('show', 'season', 'id')

        if not episode:
            season_data = self._download_json(
                f'https://corona.channel5.com/shows/{show}/seasons/{season}/episodes.json?platform=my5desktop',
                episode)

            def get_entries():
                for episode in season_data['episodes']:
                    yield self._get_episode(episode)

            return {
                '_type': 'playlist',
                'id': season,
                'title': traverse_obj(season_data, ('episodes', 0, 'sh_title')),
                'entries': get_entries(),
            }

        data = self._download_json(
            f'https://corona.channel5.com/shows/{show}/seasons/{season}/episodes/{episode}.json?platform=my5desktop',
            episode)

        return self._get_episode(data)

    def _get_episode(self, data):
        info_dict = {
            **traverse_obj(data, {
                'id': 'id',
                'title': 'title',
                'description': 'm_desc',
                'series': 'sh_title',
                'series_number': ('sea_num', {int_or_none}),
                'episode_number': ('ep_num', {int_or_none}),
                'genres': ('genre',),
            }),
            'age_limit': self._GUIDANCE.get(data['rat']),
        }

        media = self._download_json(
            '%s/my5firetv/%s.json' % (self._API_BASE, data['id']),
            data['id'])

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

    def _add_handler(self, director):
        req = self._create_request(self._API_BASE)
        default_handler = director._get_handlers(req)[0]

        class Channel5RH(type(default_handler)):
            def _make_sslcontext(self, *args, **kwargs):
                context = super()._make_sslcontext(*args, **kwargs)
                context.set_ciphers('ALL:@SECLEVEL=0')
                context.load_cert_chain(certfile=os.path.join(os.path.dirname(__file__), 'c5.pem'))

                return context

        handler = Channel5RH(ie=self, logger=None)
        director.add_handler(handler)
        director.preferences.add(
            lambda rh, req:
            500 if rh == handler and req.url.startswith(self._API_BASE) else 0)
