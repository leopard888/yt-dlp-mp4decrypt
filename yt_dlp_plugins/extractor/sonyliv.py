import json

from yt_dlp.extractor.sonyliv import SonyLIVIE


class SonyLIVDRMIE(SonyLIVIE):
    _license_info = {}

    def _download_json(self, url, video_id, *args, **kwargs):
        is_vod = '/VOD/' in url

        if is_vod:
            url = url.replace('/AGL/1.5/', '/AGL/3.8/').replace('/IN/CONTENT/', '/IN/DL/CONTENT/')
            kwargs['headers']['content-type'] = 'application/json'
            kwargs['data'] = json.dumps({
                'actionType': 'play',
                'browser': 'Chrome',
                'deviceId': self._get_device_id(),
                'os': 'Windows',
                'platform': 'web',
                'hasLAURLEnabled': True,
            }).encode()

        response = super()._download_json(url, video_id, *args, **kwargs)

        if is_vod and response.get('resultObj', {}).get('isEncrypted'):
            self._license_info[video_id] = response['resultObj'].get('LA_Details')

        return response

    def _real_extract(self, url):
        info_dict = super()._real_extract(url)

        if info_dict['id'] in self._license_info:
            info_dict['_license_url'] = self._license_info[info_dict['id']].get('laURL')

        return info_dict
