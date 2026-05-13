import logging
import httpx
from app.config import settings
from app.services.zpl_generator import strip_print_quantity

log = logging.getLogger(__name__)


def render_to_png(zpl: str, label_index: int = 0) -> bytes:
    url = (
        f'{settings.labelary_base_url}/{settings.labelary_dpmm}/labels/'
        f'{settings.label_width_inches}x{settings.label_height_inches}/{label_index}/'
    )
    log.info('Labelary request → %s', url)
    log.debug('ZPL:\n%s', zpl)

    preview_zpl = strip_print_quantity(zpl)
    # Labelary expects form-urlencoded but ZPL ^ chars must NOT be percent-encoded.
    # Sending the raw body string with Content-Type header bypasses encoding.
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'image/png',
    }
    raw_body = f'file={preview_zpl}'

    with httpx.Client(timeout=30) as client:
        response = client.post(url, content=raw_body.encode(), headers=headers)

    if response.status_code != 200:
        raise RuntimeError(f'Labelary API returned {response.status_code}: {response.text}')

    return response.content


def render_all_to_png(zpl_list: list[str]) -> list[bytes]:
    return [render_to_png(zpl, 0) for zpl in zpl_list]
