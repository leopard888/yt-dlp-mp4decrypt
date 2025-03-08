import base64
import json
import os

from yt_dlp.aes import aes_cbc_decrypt_bytes
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.extractor.sonyliv import SonyLIVIE as _SonyLIVIE
from yt_dlp.extractor.stv import STVPlayerIE as _STVPlayerIE
from yt_dlp.utils import (
    NO_DEFAULT,
    ExtractorError,
    InAdvancePagedList,
    int_or_none,
    js_to_json,
    parse_duration,
    parse_iso8601,
    traverse_obj,
    variadic,
)


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
            'chapters': self._get_chapters(content),
            **traverse_obj(content, {
                'title': 'episodeTitle',
                'duration': 'duration',
                'age_limit': 'rating',
                'description': 'description',
                'series': 'brandTitle',
                'subtitles': {'eng': ('subtitlesAssets', ..., {'url': 'url'})},
            }),
            '_license_callback': license_callback,
        }

    def _get_chapters(self, content):
        chapters = []

        if traverse_obj(content, ('skipIntro', 'skip')):
            intro = traverse_obj(
                content, ('skipIntro', {'start_time': 'skipStart', 'end_time': 'skipEnd'}))
            chapters.append({**intro, 'title': 'Intro'})
            chapters.append({'start_time': intro['end_time']})

        if traverse_obj(content, ('endCredits', 'squeeze')):
            chapters.append({
                'start_time': content['endCredits']['squeezeIn'],
                'title': 'End Credits',
            })

        for start_time in traverse_obj(content, ('adverts', 'breaks', ..., 'breakOffset')):
            if start_time not in traverse_obj(chapters, (..., 'start_time')):
                chapters.append({'start_time': start_time})

        chapters.sort(key=lambda x: x['start_time'])

        return traverse_obj(chapters, (..., {
            'start_time': ('start_time', {lambda x: x / 1000 if x else x}),
            'end_time': ('end_time', {lambda x: x / 1000 if x else x}),
            'title': 'title',
        }))


class Channel4SeriesIE(InfoExtractor):
    _VALID_URL = r'https://www\.channel4\.com/programmes/(?P<id>[a-z0-9\-]+)(?:\?|$)'

    def _real_extract(self, url):
        programme_id = self._match_id(url)
        webpage = self._download_webpage(url, programme_id)
        json_data = self._search_json(
            r'window\.__PARAMS__\s*=', webpage, 'json_data', programme_id,
            transform_source=js_to_json, end_pattern='</script>')
        episodes = traverse_obj(json_data, (
            'initialData', 'brand', 'episodes', lambda _, v: 'assetId' in v, 'hrefLink'))

        return {
            '_type': 'playlist',
            'id': programme_id,
            **traverse_obj(json_data, ('initialData', 'brand', {
                'title': 'title',
                'description': 'summary',
                'thumbnail': ('images', 'hero', 'landscape', 'src'),
            })),
            'entries': InAdvancePagedList(
                lambda idx: (yield self.url_result('https://www.channel4.com' + episodes[idx])),
                len(episodes), 1),
        }


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
        data_url_base = f'https://corona.channel5.com/shows/{show}/seasons/{season}'

        if not episode:
            season_data = self._download_json(
                f'{data_url_base}/episodes.json?platform=my5desktop', episode)

            return {
                '_type': 'playlist',
                'id': season,
                'title': traverse_obj(season_data, ('episodes', 0, 'sh_title')),
                'entries': InAdvancePagedList(
                    lambda idx: (yield self._get_episode(season_data['episodes'][idx])),
                    len(season_data['episodes']), 1),
            }

        return self._get_episode(self._download_json(
            f'{data_url_base}/episodes/{episode}.json?platform=my5desktop', episode))

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
                'timestamp': 'vod_s',
            }),
            'age_limit': self._GUIDANCE.get(data['rat']),
        }

        media = self._download_json(
            '%s/my5firetv/%s.json' % (self._API_BASE, data['id']), data['id'])

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


class ITVXIE(InfoExtractor):
    _VALID_URL = r'https://www\.itv\.com/watch/(?:[^/]+/)+(?P<id>[0-9a-zA-Z]+)'

    def _real_extract(self, url):
        video_id = self._match_id(url)
        webpage = self._download_webpage(url, video_id)
        props = self._search_nextjs_data(webpage, video_id)['props']['pageProps']

        if 'episode' in props:
            return self._get_episode(props['episode'], video_id)

        if programme := props.get('programme'):
            episodes = [ep for series in props['seriesList'] for ep in series['titles']]

            return {
                '_type': 'playlist',
                'id': video_id,
                'title': programme['title'],
                'description': programme['longDescription'],
                'entries': InAdvancePagedList(
                    lambda idx: (yield self._get_episode(episodes[idx], video_id)),
                    len(episodes), 1),
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
            **traverse_obj(episode, {
                'id': ((('encodedEpisodeId', 'letterA'), 'episodeId'), any),
                'title': (('episodeTitle', 'heroCtaLabel'), any),
                'description': (('synopsis', 'longDescription'), any),
                'release_year': 'productionYear',
                'series_number': 'series',
                'episode_number': 'episode',
                'thumbnail': (('image', 'imageUrl'), any, {lambda i: i.format(
                    width=1920, height=1080, quality=100, blur=0, bg='false', image_format='jpg')}),
                'timestamp': ('broadcastDateTime', {parse_iso8601}),
            }),
            'duration': parse_duration(traverse_obj(data, ('Playlist', 'Video', 'Duration'))),
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
                            data, ('Playlist', 'Video', 'Subtitles', ..., {'url': 'Href'}))},
                        'chapters': self._get_chapters(data),
                        '_license_url': file['KeyServiceUrl'],
                    })

        return info_dict

    def _get_chapters(self, data):
        chapters = traverse_obj(data, (
            'Playlist', 'Video', 'Timecodes',
            {'Opening Titles': 'OpeningTitles', 'End Credits': 'EndCredits'},
            {dict.items}, ...,
            {
                'start_time': (1, 'StartTime', {parse_duration}),
                'end_time': (1, 'EndTime', {parse_duration}),
                'title': 0,
            },
        ))

        for start_time in traverse_obj(data, ('Playlist', 'ContentBreaks', ..., 'TimeCode', {parse_duration})):
            if start_time not in traverse_obj(chapters, (..., 'start_time')):
                chapters.append({'start_time': start_time})

        chapters.sort(key=lambda x: x['start_time'])
        return chapters


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

            if not session.get('error') and (token := traverse_obj(session, ('user', 'token'))):
                self.cache.store('mytvsuper', 'token', token)
                return token

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
        def tag_filter(types):
            return lambda _, t: t['type'] in variadic(types)

        return traverse_obj(programme, {
            'release_year': ('tags', tag_filter('prod_year'), 'name_en', any, {int_or_none}),
            'location': ('tags', tag_filter('country_of_origin'), 'name_' + lang, any),
            'age_limit': ('parental_lock', {lambda x: 18 if x else None}),
            'categories': ('tags', tag_filter(('main_cat', 'category', 'sub_category')), 'name_' + lang),
            'cast': ('artists', ..., 'name_' + lang),
            'timestamp': ('start_time', {parse_iso8601}),
        })


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
                'sort_desc': 'true',
            })

        return {
            '_type': 'playlist',
            'id': programme_id,
            'title': programme['name_' + lang],
            'description': programme['long_desc_' + lang],
            'thumbnails': [{'id': size, 'url': programme['image'][size]} for size in programme['image']],
            **self._get_programme_info(programme, lang),
            'entries': InAdvancePagedList(
                lambda idx: (yield {
                    **self._get_episode(programme, episodes['items'][idx], lang),
                    'ie_key': 'MytvSuper',
                }),
                len(episodes['items']), 1),
        }


class SonyLIVIE(_SonyLIVIE, plugin_name='yt-dlp-mp4decrypt'):
    _license_info = {}

    def _download_json(self, url, video_id, *args, **kwargs):
        is_vod = '/VOD/' in url

        if is_vod:
            url = url.replace('/AGL/1.5/', '/AGL/3.8/').replace('/IN/CONTENT/', '/IN/DL/CONTENT/')
            kwargs['headers']['content-type'] = 'application/json'
            kwargs['data'] = json.dumps({
                'deviceId': self._get_device_id(),
                'hasLAURLEnabled': True,
                'platform': 'web',
                'actionType': 'play',
                'browser': 'Chrome',
                'os': 'Windows',
            }).encode()

        response = super()._download_json(url, video_id, *args, **kwargs)

        if is_vod and response.get('resultObj', {}).get('isEncrypted'):
            self._license_info[video_id] = response['resultObj'].get('LA_Details')

        return response

    def _real_extract(self, url):
        info_dict = super()._real_extract(url)

        if details := self._license_info.get(info_dict['id']):
            info_dict['_license_url'] = details.get('laURL')

        return info_dict


class STVPlayerIE(_STVPlayerIE, plugin_name='yt-dlp-mp4decrypt'):
    def _real_extract(self, url):
        self.BRIGHTCOVE_URL_TEMPLATE = self.BRIGHTCOVE_URL_TEMPLATE.replace('6204867266001', '1486976045')
        return super()._real_extract(url)

    def report_drm(self, video_id, partial=NO_DEFAULT):
        self.BRIGHTCOVE_URL_TEMPLATE = self.BRIGHTCOVE_URL_TEMPLATE.replace('1486976045', '6204867266001')


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
                'id': video['publisherMetadata']['brightcoveVideoId'],
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
                    'timestamp': ('onTime', {parse_iso8601}),
                }),
                'ie_key': 'BrightcoveNew',
            }

        if video['type'] == 'sportVideo':
            return {
                '_type': 'url_transparent',
                'id': video['media']['id'],
                'url': self.BRIGHTCOVE_URL_TEMPLATE % (
                    video['media']['accountId'], 'default', video['media']['id']),
                **traverse_obj(video, {
                    'title': 'phase',
                    'alt_title': 'subtext',
                    'description': 'description',
                    'thumbnails': ('images', ..., {'url': 'src'}),
                    'series': 'title',
                    'episode': 'phase',
                    'timestamp': ('onTime', {parse_iso8601}),
                }),
                'ie_key': 'BrightcoveNew',
            }

        if video['type'] == 'newsVideo':
            return {
                '_type': 'url_transparent',
                'id': video['media']['id'],
                'url': self.BRIGHTCOVE_URL_TEMPLATE % (
                    video['media']['accountId'], 'default', video['media']['id']),
                **traverse_obj(video, {
                    'title': 'title',
                    'description': 'description',
                    'thumbnails': ('images', ..., {'url': 'src'}),
                    'timestamp': ('onTime', {parse_iso8601}),
                }),
                'ie_key': 'BrightcoveNew',
            }


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
            else 'S%s E%d' % (episode['series_number'], episode['episode_number'])

        return {
            '_type': 'url_transparent',
            'id': episode['video_id'],
            'title': episode['brand_name'] + ' - ' + title,
            'url': self.BRIGHTCOVE_URL_TEMPLATE % episode['video_id'],
            **traverse_obj(episode, {
                'thumbnail': 'image',
                'description': 'synopsis',
                'duration': 'content_duration',
                'series': 'brand_name',
                'series_id': 'brand_id',
                'season_number': ('series_number', {int_or_none}),
                'season_id': 'series_id',
                'episode_number': ('episode_number', {int_or_none}),
                'episode_id': 'id',
            }),
            'episode': episode['name'] if episode['hide_episode_title'] else None,
            'ie_key': 'BrightcoveNew',
        }


class ViuTVIE(InfoExtractor):
    _VALID_URL = r'https://viu\.tv/encore/(?P<id>[a-z0-9\-]+)(?:/(?P<episode>[a-z0-9\-]+))?'

    def _real_extract(self, url):
        programme_slug, video_slug = self._match_valid_url(url).group('id', 'episode')
        programme_data = self._download_json(
            f'https://api.viu.tv/production/programmes/{programme_slug}', programme_slug)['programme']

        if video_slug:
            for vtype in ('episodes', 'clips'):
                if episode := next((ep for ep in programme_data[vtype] if ep['slug'] == video_slug), None):
                    return self._get_episode(episode)

            raise ExtractorError('Content not found')

        return {
            '_type': 'playlist',
            'id': programme_slug,
            **traverse_obj(programme_data, {
                'title': 'title',
                'description': 'synopsis',
                'cast': ('programmeMeta', 'actors', ..., 'name'),
                'genres': ('genres', ..., 'name'),
                'thumbnail': 'avatar',
            }),
            'entries': InAdvancePagedList(
                lambda idx: (yield self._get_episode(programme_data['episodes'][idx])),
                len(programme_data['episodes']), 1),
        }

    def _get_formats(self, product_id):
        vod = self._download_json(
            'https://api.viu.now.com/p8/3/getVodURL', product_id,
            data=json.dumps({
                'contentId': product_id,
                'contentType': 'Vod',
                'deviceType': 'ANDROID_WEB',
            }).encode(),
        )

        if vod['responseCode'] == 'GEO_CHECK_FAIL':
            self.raise_geo_restricted()

        if '.m3u8' in vod['asset'][0]:
            return self._extract_m3u8_formats_and_subtitles(vod['asset'][0], product_id)

        return self._extract_mpd_formats_and_subtitles(vod['asset'][0], product_id)

    def _get_episode(self, episode):
        formats, subtitles = self._get_formats(episode['productId'])

        return {
            **traverse_obj(episode, {
                'id': 'productId',
                'title': 'episodeNameU3',
                'thumbnail': 'avatar',
                'description': 'program_synopsis',
                'cast': ('videoMeta', 'actors', ..., 'name'),
                'genres': ('programmeMeta', 'genre', ..., 'name'),
                'duration': 'totalDurationSec',
                'series': 'program_title',
                'episode': 'episodeNameU3',
                'episode_number': 'episodeNum',
                'timestamp': ('onAirStartDate', {int_or_none(scale=1000)}),
            }),
            'formats': formats,
            'subtitles': subtitles,
            '_cenc_key': '91ba752a446148c68400d78374b178b4:a01d7dc4edf582496b7e73d67e9e6899',
        }
