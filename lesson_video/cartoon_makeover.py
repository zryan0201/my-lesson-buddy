"""Optional local, reference-guided cartoon redraw. No hosted inference calls."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import importlib.util
import re
import threading
import time

from PIL import Image, ImageFilter, ImageOps
from character_studio.images import normalize_image, png_bytes

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / '.cache/cartoon_models'
BASE = ('Lykon/dreamshaper-8', 'a7e52b98680b1ba8ff7bce97c7f9f2e2e5337917')
CONTROL = ('lllyasviel/control_v11p_sd15_canny', '115a470d547982438f70198e353a921996e2e819')
DOWNLOAD_BYTES = 3_463_219_720
STYLES = {
    'soft3d': 'polished cute 3D cartoon toy, rounded clay forms, soft ambient shading',
    'storybook': 'polished friendly 2D storybook cartoon sticker, smooth confident outlines, softly rounded shapes, simple soft cel shading',
    'comic': 'polished friendly 2D comic cartoon sticker, bold smooth ink outlines, clean flat colors, simple cel shading',
}
STRENGTHS = {'gentle': .65, 'balanced': .80, 'creative': .85}
CONTROL_SCALES = {'gentle': .75, 'balanced': .40, 'creative': .30}
NEGATIVE = ('photo, photorealistic, scary, violence, weapon, blood, nude, sexual, text, '
            'logo, watermark, background scene, extra characters, extra limbs, cropped, '
            'missing limbs, blurry, messy scribbles, rough broken contours, unwanted ruffles, realistic person')


class CartoonError(ValueError):
    pass


class CartoonCancelled(CartoonError):
    pass


@dataclass(frozen=True)
class CartoonOptions:
    idea: str = ''
    style: str = 'soft3d'
    strength: str = 'balanced'
    seed: int = 24


def validate_options(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or set(value) - {'idea', 'style', 'strength', 'seed'}:
        raise CartoonError('Choose the displayed cartoon options.')
    idea = value.get('idea', '')
    if not isinstance(idea, str) or len(idea) > 240 or re.search(r'[\x00-\x1f\x7f]', idea):
        raise CartoonError('Describe your character in at most 240 characters.')
    if re.search(r'https?:|www\.|[\w.+-]+@[\w.-]+\.[a-z]{2,}|(?:\d[\s()+.-]*){7}', idea, re.I):
        raise CartoonError('Describe the character without links or personal contact details.')
    if re.search(r'\b(?:porn\w*|nude|naked|sex(?:ual)?|rape|suicide|kill|murder|blood|gore|gun|rifle|bomb)\b', idea, re.I):
        raise CartoonError('Describe a friendly character with colors and accessories.')
    style, strength, seed = value.get('style', 'soft3d'), value.get('strength', 'balanced'), value.get('seed', 24)
    if not isinstance(style, str) or not isinstance(strength, str) or style not in STYLES or strength not in STRENGTHS or type(seed) is not int or not 0 <= seed < 2**31:
        raise CartoonError('Choose a supported style, change level, and seed.')
    return CartoonOptions(idea.strip(), style, strength, seed)


def snapshot_path(cache, model):
    return Path(cache) / ('models--' + model[0].replace('/', '--')) / 'snapshots' / model[1]


def model_status(cache=DEFAULT_CACHE):
    base, control = snapshot_path(cache, BASE), snapshot_path(cache, CONTROL)
    required = [base / p for p in ('model_index.json', 'unet/diffusion_pytorch_model.fp16.safetensors',
                'vae/diffusion_pytorch_model.fp16.safetensors', 'text_encoder/model.fp16.safetensors',
                'safety_checker/model.fp16.safetensors', 'feature_extractor/preprocessor_config.json')]
    required.append(control / 'diffusion_pytorch_model.fp16.safetensors')
    dependencies = all(importlib.util.find_spec(name) for name in ('torch', 'diffusers', 'cv2'))
    return {'ready': bool(dependencies and all(p.is_file() for p in required)), 'download_bytes': DOWNLOAD_BYTES,
            'local_only': True, 'safety_checker': True, 'message': 'Local cartoon model ready.' if dependencies and all(p.is_file() for p in required)
            else 'Run the local cartoon setup to install the runtime and download about 3.5 GB of model files.'}


def download_models(cache=DEFAULT_CACHE):
    from huggingface_hub import snapshot_download
    for name, revision in (BASE, CONTROL):
        snapshot_download(name, revision=revision, cache_dir=cache,
                          allow_patterns=['*.json', 'tokenizer/*.txt', '*.fp16.safetensors'], max_workers=4)


def prepare_reference(raw):
    """Keep source colors as img2img conditioning and produce a separate edge guide."""
    import cv2
    import numpy as np
    drawing = normalize_image(raw)
    white = Image.new('RGBA', drawing.size, 'white'); white.alpha_composite(drawing)
    reference = white.convert('RGB').resize((384, 512), Image.Resampling.LANCZOS)
    blurred = np.asarray(reference.filter(ImageFilter.GaussianBlur(2.5)))
    edges = Image.fromarray(cv2.Canny(blurred, 40, 110)).convert('RGB')
    return reference, edges


def palette_colors(reference):
    import cv2
    import numpy as np
    rgb = np.asarray(reference)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    selected = rgb[(hsv[:, :, 1] > 45) & (hsv[:, :, 2] > 45)]
    if not len(selected):
        return []
    # Quantize only the child's visible colors; white paper and dark outlines do not dominate.
    sample = Image.fromarray(selected[::max(1, len(selected)//20000)][None, :, :])
    quantized = sample.quantize(colors=6)
    palette = quantized.getpalette()
    counts = sorted(quantized.getcolors(), reverse=True)
    colors = [palette[3*i:3*i+3] for count, i in counts if count >= len(sample.getdata())*.025]
    return colors[:6]


def preserve_palette(candidate, reference):
    """Align generated chroma to the source palette, retaining generated light/shade."""
    import cv2
    import numpy as np
    palette = palette_colors(reference)
    if not palette:
        return candidate.convert('RGB')
    rgb = np.asarray(candidate.convert('RGB'))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    anchors = cv2.cvtColor(np.asarray([palette], dtype=np.uint8), cv2.COLOR_RGB2HSV)[0].astype(np.float32)
    diff = np.abs(hsv[:, :, None, 0] - anchors[None, None, :, 0]); distance = np.minimum(diff, 180-diff)
    nearest = anchors[np.argmin(distance, axis=2)]
    colored = (hsv[:, :, 1] > 30) & (hsv[:, :, 2] > 35)
    hsv[:, :, 0][colored] = nearest[:, :, 0][colored]
    hsv[:, :, 1][colored] = .80*nearest[:, :, 1][colored] + .20*hsv[:, :, 1][colored]
    return Image.fromarray(cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2RGB))


def fidelity_checks(reference, candidate):
    """Image checks catch large drift, without claiming semantic identity verification."""
    import cv2
    import numpy as np
    def mask(image):
        a = np.asarray(image.convert('RGB')); return (a.min(axis=2) < 220).astype(np.uint8)
    a, b = mask(reference), mask(candidate.resize(reference.size))
    # A small tolerance allows a cleaner contour without demanding identical strokes.
    kernel = np.ones((11, 11), dtype=np.uint8)
    a_near, b_near = cv2.dilate(a, kernel), cv2.dilate(b, kernel)
    recall = float((a*b_near).sum()/max(1, a.sum())); precision = float((b*a_near).sum()/max(1, b.sum()))
    border = int(b[:4].sum()+b[-4:].sum()+b[:, :4].sum()+b[:, -4:].sum())
    return {'source_coverage': round(recall, 3), 'candidate_alignment': round(precision, 3),
            'border_ink_pixels': border, 'passed': recall >= .60 and precision >= .55 and border < 50}


def finish_cartoon(image):
    """Close tiny outline gaps before removing paper, retaining white toy details."""
    import cv2
    import numpy as np
    rgb = np.asarray(image.convert('RGB'))
    mask = (rgb.min(axis=2) < 247).astype(np.uint8)*255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    outside = mask.copy(); cv2.floodFill(outside, None, (0, 0), 255)
    mask = cv2.bitwise_or(mask, cv2.bitwise_not(outside))
    result = image.convert('RGBA'); result.putalpha(Image.fromarray(mask).filter(ImageFilter.GaussianBlur(.35)))
    return normalize_image(png_bytes(result), remove_paper=False)


class CartoonRuntime:
    def __init__(self, cache=DEFAULT_CACHE):
        self.cache = Path(cache); self.pipe = None; self.device = None; self.lock = threading.Lock()

    def _load(self, progress, cancelled):
        if self.pipe is not None:
            return
        if not model_status(self.cache)['ready']:
            raise CartoonError(model_status(self.cache)['message'])
        import torch
        from diffusers import ControlNetModel, StableDiffusionControlNetImg2ImgPipeline, DPMSolverMultistepScheduler
        self.device = 'mps' if torch.backends.mps.is_available() else 'cuda' if torch.cuda.is_available() else 'cpu'
        # Full precision prevents half-precision NaNs observed on the tested M4/MPS path.
        dtype = torch.float32
        progress('loading', 0)
        control = ControlNetModel.from_pretrained(snapshot_path(self.cache, CONTROL), torch_dtype=dtype,
                    variant='fp16', use_safetensors=True, local_files_only=True)
        pipe = StableDiffusionControlNetImg2ImgPipeline.from_pretrained(snapshot_path(self.cache, BASE),
                    controlnet=control, torch_dtype=dtype, variant='fp16', use_safetensors=True, local_files_only=True)
        if pipe.safety_checker is None:
            raise CartoonError('The local safety checker is missing. Re-run setup before generating.')
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config,
                    use_karras_sigmas=True, algorithm_type='dpmsolver++')
        pipe.to(self.device); pipe.enable_attention_slicing(); pipe.enable_vae_slicing()
        # Keep filtering enabled, using CPU float32 CLIP to avoid device-specific
        # numerical differences in this separate safety decision.
        checker = pipe.safety_checker.to('cpu', dtype=torch.float32)
        def check(images, clip_input):
            return checker(images=images, clip_input=clip_input.to('cpu', dtype=torch.float32))
        pipe.safety_checker = check
        if cancelled():
            raise CartoonCancelled('Cartoon makeover cancelled. Your original is safe.')
        self.pipe = pipe

    def generate(self, raw, options=None, *, progress=lambda stage, value: None, cancelled=lambda: False):
        options = validate_options(options)
        reference, edges = prepare_reference(raw)
        if not self.lock.acquire(blocking=False):
            raise CartoonError('One cartoon makeover is already running. Wait or cancel it first.')
        started = time.monotonic()
        try:
            self._load(progress, cancelled)
            import torch
            if cancelled():
                raise CartoonCancelled('Cartoon makeover cancelled. Your original is safe.')
            def step(pipe, step, timestep, callback_kwargs):
                if cancelled() or time.monotonic()-started > 8*60:
                    raise CartoonCancelled('Cartoon makeover cancelled or timed out. Your original is safe.')
                progress('generating', min(95, 100*(step+1)/max(1, int(30*STRENGTHS[options.strength]))))
                return callback_kwargs
            # Put framing before the optional hint; bound the hint to CLIP's budget.
            hint = self.pipe.tokenizer.decode(self.pipe.tokenizer(options.idea, add_special_tokens=False,
                    max_length=32, truncation=True).input_ids) if options.idea else 'the same imaginary character'
            prompt = (f'{STYLES[options.style]}, full body, centered on pure white background, '
                      f'{hint}, same source silhouette, pose and colors')
            result = self.pipe(prompt=prompt, negative_prompt=NEGATIVE, image=reference, control_image=edges,
                      strength=STRENGTHS[options.strength], num_inference_steps=30, guidance_scale=7,
                      controlnet_conditioning_scale=CONTROL_SCALES[options.strength], generator=torch.Generator(device='cpu').manual_seed(options.seed),
                      callback_on_step_end=step)
            if cancelled():
                raise CartoonCancelled('Cartoon makeover cancelled. Your original is safe.')
            if not result.nsfw_content_detected or any(result.nsfw_content_detected):
                raise CartoonError('The image safety check did not approve this version. Your original is safe.')
            progress('checking', 97)
            candidate = preserve_palette(result.images[0], reference)
            checks = fidelity_checks(reference, candidate)
            if not checks['passed']:
                raise CartoonError('This version changed the drawing too much. Try Gentle and describe the features to keep. Your original is safe.')
            return candidate, {'checks': checks, 'seed': options.seed, 'device': self.device,
                    'seconds': round(time.monotonic()-started, 2), 'palette': palette_colors(reference),
                    'models': [list(BASE), list(CONTROL)], 'safety_checker_passed': True}
        finally:
            self.lock.release()
