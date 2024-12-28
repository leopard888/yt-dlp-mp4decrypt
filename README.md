This [yt-dlp](https://github.com/yt-dlp/yt-dlp) plugin integrates `mp4decrypt` and `pywidevine` to streamline downloading and decryption.

## Prerequisites

- `yt-dlp`
    - If the standalone version (i.e. You downloaded the `yt-dlp` executable on its own) doesn't work, install and use the PIP version instead: `pip install -U yt-dlp`.
- The `mp4decrypt` executable (part of [Bento4](https://www.bento4.com/)) in your system's PATH (or in the same directory as `yt-dlp`)
- A CDM in .wvd format

## Installation

You can install this package with pip:
```
python3 -m pip install -U https://github.com/aarubui/yt-dlp-mp4decrypt/archive/master.zip
```

## Usage

Use `--use-postprocessor` to activate the plugin. This can be added to configuration files without effects for unencrypted videos.

```shell
yt-dlp --use-postprocessor Mp4Decrypt:when=before_dl;devicepath=<path_to_wvd_file> <video_url>
```

## Supported extractors

Sites supported by `yt-dlp` where unplayable formats are returned and the license URL is provided in the `mpd` file (e.g. Brightcove) will work out of the box with this plugin. Extractors which give the `This video is DRM protected` error even with `--allow-unplayable-formats` won't work.

## Extending support

Add support for a site by writing your own [plugin](https://github.com/yt-dlp/yt-dlp#plugins). The following extra fields are supported in the info dict:

- `_cenc_key` (decryption key in `kid:key` format)
- `_license_url` (URL to license server)
- `_license_callback` (function which takes the `challenge` data and returns the license server response)

Use `_license_callback` when communication with the license server needs customisation (e.g. server request needs special headers).

### Example

```python
from yt_dlp.extractor.common import InfoExtractor


class YourExtractorIE(InfoExtractor):
    _VALID_URL = r'https?://(?:www\.)?yourextractor\.com/watch/(?P<id>[0-9]+)'

    def _real_extract(self, url):
        video_id = self._match_id(url)
        mpd_url = 'https://yourextractor.com/' + video_id + '.mpd'

        return {
            'id': video_id,
            'title': video_id,
            'formats': self._extract_mpd_formats(mpd_url, video_id),
            '_license_url': 'https://cwip-shaka-proxy.appspot.com/no_auth',
        }
```
