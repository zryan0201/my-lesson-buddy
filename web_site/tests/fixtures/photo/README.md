# Synthetic camera-condition fixtures

These are deterministic simulations built from the project's original popsicle
worksheet and yellow-dot worksheet. They are **not real phone photographs** and
do not establish classroom or device accuracy.

Each JSON contains width, height and zlib-compressed RGBA pixels as Base64. The
metadata retains the known projected page corners and expected geometry action
and object-extraction outcome. Perspective images are 640×480, with the paper at
pixel corners `(74,53), (574,81), (543,431), (96,408)`. The original printed objects
are placed on a 560×420 white page, exposed to a smooth scalar illumination field
and broad soft shadow, then perspective-warped onto a dark desk and JPEG encoded
at quality 90. Random texture seeds are 1729–1733.

The positive cases retain seven original popsicles or five original yellow dots.
Clipped paper requires manual corner review. Very dark paper can have a valid
geometric outline but must decline lighting correction and object extraction.
The clean originals stay byte-for-byte unchanged through lighting correction.

Run `node scripts/check_photo_fixtures.mjs` from the `web_site` directory to write
the measured corner, lighting and extraction report under
`../output/photo_worksheets/`. The local generation recipe and visual comparison
are saved there as `make_photo_fixtures.py` and `synthetic_before_after.png`.
