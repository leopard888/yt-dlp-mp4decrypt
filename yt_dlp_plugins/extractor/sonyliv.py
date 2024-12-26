import json

from yt_dlp.extractor.sonyliv import SonyLIVIE


class SonyLIVDRMIE(SonyLIVIE, plugin_name='yt-dlp-mp4decrypt'):
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
