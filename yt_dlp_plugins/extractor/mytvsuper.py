from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import (
    InAdvancePagedList,
    int_or_none,
    traverse_obj,
)


class MytvSuperIE(InfoExtractor):
    _VALID_URL = r'https://www\.mytvsuper\.com/(?:(?P<lang>tc|en)/)?programme/.*/e/(?P<id>\d+)/'
    _GEO_COUNTRIES = ['HK']
    _ANON_TOKEN = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJib3NzX2lkIjoiMDAwMDAwMDAxIiwiZGV2aWNlX3Rva2VuIjoiQ3ZmTUNzVTh4UGlpYmtDUUVrSzM5NUpnIiwiZGV2aWNlX2lkIjoiMCIsImRldmljZV90eXBlIjoid2ViIiwiZGV2aWNlX29zIjoiYnJvd3NlciIsImRybV9pZCI6bnVsbCwiZXh0cmEiOnsicHJvZmlsZV9pZCI6MX0sImlhdCI6MTY0NjI5MzQxNCwiZXhwIjoxNjQ2Mjk3MDE0fQ.t5qYMiV4RJkAZ9FfmmJtigpzNca0P5ZnI4AEXU61HWVIJd5cIUQlNufOJbN4R3MPJxs7msOVBdosIMaIhF49so_ubufqSNDDK9s3qZRpAUaHvRtiXQWCuuL3Am07IwaR6vO-yNFpNtnhTWp7V-5KkmJjmjgwtbQlwK5FU424Ef9iFu64aeounen8o5cuBuql5nRl6mFOX7QMx3Cr0XmLyJBRsuuoXlivaGzNchqT4rkmck0SUqeeBSzcpoDdFry4SXZO9I_CIK75bOX4Icw5p8ZFwAzYvE5xhTpAEdRUKMPSDMRD9Vak-WKPWhQBeV8X5LJONhaofMaq0j0HC5sM6arPQR6x2r5y5IPZwVOcUaYqJVlgXOAP72iFwCkZBm30qJV9p5eLSNWizpVUbYIEiwjcqBQ9ZZR2jqszzSEZpsTO1kwQ3jIViewwFJjffBljrp5ZsRDj-vXrdZ-tXVY4ecsgrjUXJJEEMKMCBVFLzuu5is6Hgdr8BUdm8QAPQqvvkqu7W0Gt-2YAgcU4eEG2wzx1485wxNxLgXXG10SwzH12OHxqoMl3_KP22JN9JgP6uS1Br4yLFqo-v3Z-UOAo3x_yfivgcW34uI4VHSF1JiQfJinsSWeHOGPJrDSDvrCNLZbFonX2xaWVOQ3Uf8hXum55xNufLM8Trt4Ga8CBZMY'

    def _real_extract(self, url):
        lang, episode_id = self._match_valid_url(url).group('lang', 'id')
        episode = self._download_json(
            'https://content-api.mytvsuper.com/v2/episode/id', episode_id,
            query={'episode_id': episode_id})
        programme = self._download_json(
            'https://content-api.mytvsuper.com/v1/programme/details', episode_id,
            query={'programme_id': episode['programme_id']})

        return self._get_episode(programme, episode['currEpisode'], lang or 'tc')

    def _get_token(self, video_id):
        if self._cookies_passed:
            session = self._download_json(
                'https://www.mytvsuper.com/api/auth/getSession/self/', video_id)

            if token := traverse_obj(session, ('user', 'token')):
                self.cache.store('mytvsuper', 'token', token)

        return self.cache.load('mytvsuper', 'token') or self._ANON_TOKEN

    def _get_episode(self, programme, episode, lang):
        episode_name = self._get_mytv_episode_name(episode, lang)
        episode_id = episode['episode_id']

        data = self._download_json(
            'https://user-api.mytvsuper.com/v1/video/checkout', episode_id,
            query={'platform': 'web', 'video_id': episode['video_id']},
            headers={'Authorization': 'Bearer ' + self._get_token(episode_id)})

        formats = []
        profiles = {profile['quality']: profile['streaming_path'] for profile in data['profiles']}
        profiles = (profiles['auto'],) if 'auto' in profiles else profiles.values()

        for profile in profiles:
            formats.extend(self._extract_mpd_formats(profile.replace('https://', 'http://'), episode_id))

        def license_callback(challenge):
            return self._request_webpage(
                'https://wv.drm.tvb.com/wvproxy/mlicense', episode_id,
                query={'contentid': data['content_id']},
                data=challenge,
                headers={
                    'Content-Type': 'application/octet-stream',
                    'x-user-token': self._get_token(episode_id),
                }).read()

        return {
            'id': str(episode_id),
            'title': '%s %s' % (programme['name_' + lang], episode_name),
            'formats': formats,
            'description': episode['desc_' + lang],
            'subtitles': {sub['language']: [{'url': sub['path']}] for sub in data['subtitles']},
            'thumbnails': [{'id': size, 'url': episode['image'][size]} for size in episode['image']],
            'duration': episode['duration'],
            **self._get_programme_info(programme, lang),
            'series': programme['name_' + lang],
            'episode': episode_name,
            'episode_number': episode['episode_no'],
            '_license_callback': license_callback,
        }

    def _get_mytv_episode_name(self, episode, lang='tc'):
        if episode['name_tc']:
            return episode['name_' + lang]
        if episode['episode_no'] < 1e7:
            return ('第%d集' if lang == 'tc' else 'Episode %d') % episode['episode_no']

        name = str(episode['episode_no'])
        return '%s/%s/%s' % (name[0:4], name[4:6], name[6:8])

    def _get_programme_info(self, programme, lang):
        return {
            'release_year': int_or_none(next((tag['name_en'] for tag in programme['tags']
                                              if tag['type'] == 'prod_year'), None)),
            'location': next((tag['name_' + lang] for tag in programme['tags']
                              if tag['type'] == 'country_of_origin'), None),
            'age_limit': 18 if programme['parental_lock'] else None,
            'categories': [tag['name_' + lang] for tag in programme['tags']
                           if tag['type'] in ('main_cat', 'category', 'sub_category')],
            'cast': traverse_obj(programme, ('artists', ..., 'name_' + lang)),
        }


class MytvSuperPlaylistIE(MytvSuperIE):
    _VALID_URL = r'https://www\.mytvsuper\.com/(?P<lang>tc|en)/programme/[a-z0-9]+_(?P<id>\d+)/([^/#]+)/$'

    def _real_extract(self, url):
        lang, programme_id = self._match_valid_url(url).group('lang', 'id')
        programme = self._download_json(
            'https://content-api.mytvsuper.com/v1/programme/details', programme_id,
            query={'programme_id': programme_id})
        episodes = self._download_json(
            'https://content-api.mytvsuper.com/v1/episode/list', programme_id,
            query={
                'programme_id': programme_id,
                'start_episode_no': 1,
                'end_episode_no': programme['latest_episode_no'],
            })

        def _get_entry(idx):
            yield self._get_episode(programme, episodes['items'][idx], lang)

        return {
            '_type': 'playlist',
            'id': programme_id,
            'title': programme['name_' + lang],
            'description': programme['long_desc_' + lang],
            'thumbnails': [{'id': size, 'url': programme['image'][size]} for size in programme['image']],
            **self._get_programme_info(programme, lang),
            'entries': InAdvancePagedList(_get_entry, len(episodes['items']), 1),
        }
