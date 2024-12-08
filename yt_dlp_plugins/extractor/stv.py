from yt_dlp.extractor.stv import STVPlayerIE
from yt_dlp.utils import NO_DEFAULT


class STVIE(STVPlayerIE):
    IE_NAME = 'STV'

    def report_drm(self, video_id, partial=NO_DEFAULT):
        self.BRIGHTCOVE_URL_TEMPLATE = self.BRIGHTCOVE_URL_TEMPLATE.replace('1486976045', '6204867266001')
