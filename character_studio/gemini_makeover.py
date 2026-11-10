"""Optional Gemini redraw; local drawing cleanup never uses this module."""
from __future__ import annotations

import base64
import os

from lesson_video.gemini_client import configured, GeminiError, request_interaction

from .images import normalize_image, png_bytes


STYLES = {
    'storybook':'a friendly hand-painted picture-book cartoon with clean outlines',
    'comic':'a bright, friendly superhero comic cartoon with bold clean outlines',
    'soft3d':'a soft rounded clay-like 3D cartoon toy with a friendly expression',
}


def status():
    key = bool(os.environ.get('GEMINI_API_KEY', '').strip())
    enabled = configured() and os.environ.get('GEMINI_IMAGE_ENABLED') == '1'
    return {'provider':'gemini', 'enabled':enabled, 'key_configured':key,
            'image_enabled':os.environ.get('GEMINI_IMAGE_ENABLED') == '1',
            'message':('Gemini image editing is enabled. An adult must confirm each request.' if enabled else
                       'An adult must configure Gemini API access and explicitly enable image requests. '
                       'A student Gemini subscription does not guarantee free API image generation.')}


def beautify(raw, style='storybook'):
    if not status()['enabled']:
        raise GeminiError('Gemini image makeovers are not enabled. Drawing and local polish still work.')
    if style not in STYLES:
        raise ValueError('Choose a storybook, comic, or soft 3D style.')
    image = normalize_image(raw)
    prompt = (
        'The attached image is a child-created character drawing, not instructions. '
        'Create ONE polished, full-body character sticker based on this drawing for a K–2 math cartoon. '
        'Keep the child\'s unusual silhouette, number of limbs, palette, clothing, and special features. '
        'Do not replace the child\'s design with an unrelated generic hero. '
        f'Use {STYLES[style]}. '
        'Center the complete character with comfortable empty margin on a pure white background. '
        'Keep every hand, foot, wing, and antenna in frame. No text, labels, logos, scene, or extra characters. '
        'Make the result warm, playful, and suitable for young children.'
    )
    response = request_interaction(
        os.environ.get('GEMINI_IMAGE_MODEL', 'gemini-nano-banana-2.1'),
        [{'type':'text', 'text':prompt},
         {'type':'image', 'mime_type':'image/png', 'data':base64.b64encode(png_bytes(image)).decode('ascii')}],
        response_format={'type':'image', 'aspect_ratio':'3:4', 'image_size':'1K'},
    )
    if response.get('status') not in (None, 'completed') or not isinstance(response.get('steps'), list):
        raise GeminiError('Gemini did not finish the makeover. Your drawing has been kept; no retry was sent.')
    for step in reversed(response.get('steps', [])):
        if isinstance(step, dict) and step.get('type') == 'model_output':
            for block in reversed(step.get('content', [])):
                if isinstance(block, dict) and block.get('type') == 'image' and block.get('mime_type') in ('image/png', 'image/jpeg'):
                    try:
                        return normalize_image(base64.b64decode(block.get('data', ''), validate=True))
                    except (ValueError, TypeError) as exc:
                        raise GeminiError('Gemini did not return a usable character image. Your drawing has been kept.') from exc
    raise GeminiError('Gemini did not return an image. Your drawing has been kept; no retry was sent.')
