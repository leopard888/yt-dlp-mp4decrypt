import subprocess
from os import name as os_name
from os import path, rename, replace
from re import sub

from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH
from yt_dlp.networking.common import Request
from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.utils import (
    Popen,
    PostProcessingError,
    prepend_extension,
    YoutubeDLError,
)


class Mp4DecryptPP(PostProcessor):
    def __init__(self, downloader=None, **kwargs):
        PostProcessor.__init__(self, downloader)
        self._sniff_mpds(downloader)
        self._kwargs = kwargs
        self._pssh = {}
        self._license_urls = {}
        self._encrypted_mpds = []
        self._keys = {}

        class _FileDecrypter(PostProcessor):
            def run(_self, info):
                return self._real_run(info)

        decryptor = _FileDecrypter(downloader)

        class _KeyFetcher(PostProcessor):
            def run(_self, info):
                for part in info.get('requested_formats', []):
                    _self._get_keys(info, part)

                _self._get_keys(info, info)
                return [], info

            def _get_keys(_self, info, part):
                if self._is_mpd(part) and self._has_drm(part):
                    if not self._get_keys(info, part):
                        raise YoutubeDLError('No keys found for ' + part['format_id'])

                    if not decryptor in info.get('__postprocessors', []):
                        info.setdefault('__postprocessors', [])
                        info['__postprocessors'].append(decryptor)

        downloader.add_post_processor(_KeyFetcher(downloader), when='before_dl')

    def _sniff_mpds(self, downloader):
        oldextmethod = downloader.add_info_extractor

        def newextmethod(ie):
            oldmpdmethod = ie._parse_mpd_periods

            def newmpdmethod(mpd_doc, *args, **kwargs):
                elements = mpd_doc.findall('.//{*}ContentProtection')
                found = False

                for element in elements:
                    if element.get('schemeIdUri').lower() == PSSH.SystemId.Widevine.urn:
                        mpd_url = kwargs.get('mpd_url') or args[2]

                        if pssh := element.findtext('./{*}pssh'):
                            self._pssh[mpd_url] = pssh

                        self._license_urls[mpd_url] = element.get('{urn:brightcove:2015}licenseAcquisitionUrl')
                        found = True

                if elements and found:
                    # treat formats as unprotected
                    for parent in mpd_doc.findall('.//*/..[{*}ContentProtection]'):
                        for child in parent.findall('{*}ContentProtection'):
                            parent.remove(child)

                    self._encrypted_mpds.append(mpd_url)

                return oldmpdmethod(mpd_doc, *args, **kwargs)

            ie._parse_mpd_periods = newmpdmethod

            if hasattr(ie, '_parse_brightcove_metadata'):
                oldbcmethod = ie._parse_brightcove_metadata

                def newbcmethod(json_data, *args, **kwargs):
                    for source in json_data.get('sources') or []:
                        if 'com.widevine.alpha' in source.get('key_systems') or {}:
                            del source['key_systems']

                    return oldbcmethod(json_data, *args, **kwargs)

                ie._parse_brightcove_metadata = newbcmethod

            oldextmethod(ie)

        downloader.add_info_extractor = newextmethod

    def _real_run(self, info):
        encrypted = []

        if 'requested_formats' in info:
            encrypted = [p for p in info['requested_formats'] if self._is_encrypted(p)]
        elif info.get('__real_download') and self._is_encrypted(info):
            encrypted.append(info)

        if encrypted:
            self.to_screen('Decrypting format(s)')

            for part in encrypted:
                if self._is_mpd(part) and (keys := self._get_keys(info, part)):
                    self._decrypt_part(keys, part['filepath'])

        return [], info

    def _has_drm(self, info):
        return info.get('manifest_url') in self._encrypted_mpds

    def _is_encrypted(self, info):
        return 'filepath' in info and self._has_drm(info)

    def _is_mpd(self, info):
        return info.get('container') in ('mp4_dash', 'm4a_dash')

    def _get_keys(self, info, part):
        if key := info.get('_cenc_key'):
            return ('--key', key)

        mpd_url = part['manifest_url']

        if mpd_url in self._pssh:
            pssh = self._pssh[mpd_url]
        else:
            pssh = self._pssh[mpd_url] = self._pssh_from_init(part)

        if not pssh:
            return ()

        if keys := self._keys.get(pssh):
            return keys

        license_callback = info.get('_license_callback')
        license_url = info.get('_license_url', self._license_urls.get(mpd_url))

        if not license_callback and license_url:

            def license_callback(challenge):
                self.to_screen(f'Fetching keys from {license_url}')
                return self._downloader.urlopen(Request(
                    license_url, data=challenge,
                    headers={'Content-Type': 'application/octet-stream'})).read()

        if license_callback:
            return self._fetch_keys(pssh, license_callback)

        return ()

    def _pssh_from_init(self, part):
        def find_wv_pssh_offsets(raw):
            offset = 0

            while True:
                offset = raw.find(b'pssh', offset)

                if offset == -1:
                    break

                pssh_offset = offset - 4
                size = int.from_bytes(raw[pssh_offset:offset], byteorder='big')
                offset += size
                yield PSSH(raw[pssh_offset: pssh_offset + size])

        init_data = self._downloader.urlopen(Request(
            part['fragment_base_url'] + part['fragments'][0]['path'],
            headers=part['http_headers'])).read()

        for pssh in find_wv_pssh_offsets(init_data):
            if pssh.system_id == PSSH.SystemId.Widevine:
                self.to_screen('Extracted PSSH from init segment')
                return pssh.dumps()

        self.report_warning('Could not find PSSH for ' + part['format_id'])
        return None

    def _fetch_keys(self, pssh, callback):
        keys = ()

        if devicepath := self._kwargs.get('devicepath'):
            cdm = Cdm.from_device(Device.load(devicepath))
            session_id = cdm.open()
            challenge = cdm.get_license_challenge(session_id, PSSH(pssh), 'STREAMING', privacy_mode=True)
            cdm.parse_license(session_id, callback(challenge))

            for key in cdm.get_keys(session_id):
                if key.type == 'CONTENT':
                    keyarg = f'{key.kid.hex}:{key.key.hex()}'
                    self.to_screen(f'Fetched key: {keyarg}')
                    keys += ('--key', keyarg)

        self._keys[pssh] = keys
        return keys

    def _decrypt_part(self, keys, filepath):
        cwd = path.dirname(filepath)
        filename = path.basename(filepath)
        originalpath = filepath

        if os_name == 'nt':
            # mp4decrypt on Windows cannot handle certain filenames
            filename = sub(r'[^\x20-\x7E]+', '', filename)
            filepath = path.join(cwd, filename)
            rename(originalpath, filepath)

        tmpname = prepend_extension(filename, 'decrypted')
        cmd = ('mp4decrypt', *keys, filename, tmpname)

        _, stderr, returncode = Popen.run(
            cmd, cwd=cwd or None, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)

        if returncode != 0:
            raise PostProcessingError(stderr)

        if filepath != originalpath:
            rename(filepath, originalpath)
            filepath = originalpath

        replace(path.join(cwd, tmpname), filepath)
