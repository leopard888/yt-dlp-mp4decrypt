from yt_dlp.extractor.stv import STVPlayerIE
from yt_dlp.utils import NO_DEFAULT


class STVIE(STVPlayerIE, plugin_name='yt-dlp-mp4decrypt'):
    def _real_extract(self, url):
        self.BRIGHTCOVE_URL_TEMPLATE = self.BRIGHTCOVE_URL_TEMPLATE.replace('6204867266001', '1486976045')
        return super()._real_extract(url)

    def report_drm(self, video_id, partial=NO_DEFAULT):
        self.BRIGHTCOVE_URL_TEMPLATE = self.BRIGHTCOVE_URL_TEMPLATE.replace('1486976045', '6204867266001')
