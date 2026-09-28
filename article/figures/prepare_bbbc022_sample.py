"""Extract the fixed first benchmark field without changing its pixel values."""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).resolve().parent / "data"


def prepare(raw_path):
    source = json.loads((ROOT / "bbbc022-evidence/input-source.json").read_text())
    dataset = source["dataset"]
    asset = dataset["assets"][0]
    raw = Path(raw_path).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == asset["sha256"]
    values = np.frombuffer(raw, dtype="<u2").reshape(asset["shape"])
    plane = asset["preview"]["plane"]
    field = values[plane].copy()
    limits = np.percentile(field, asset["preview"]["percentiles"])
    assert np.allclose(limits, asset["preview"]["intensity_range"])
    DATA.mkdir(exist_ok=True)
    output = DATA / "bbbc022-a14-s1-w5.npy"
    np.save(output, field, allow_pickle=False)
    record = {
        "dataset": "BBBC022v1",
        "source_url": dataset["source"]["url"],
        "attribution": dataset["source"]["attribution"],
        "license": dataset["source"]["license"],
        "license_url": dataset["source"]["license_url"],
        "benchmark_input_provenance": "bbbc022-evidence/input-source.json",
        "verified_raw_asset_sha256": asset["sha256"],
        "source_tiff_record": asset["provenance"]["files"][plane],
        "source_tiff_verification": "Recorded source TIFF checksum; figure extraction verifies the complete benchmark raw asset.",
        "selection": "Fixed first field, matching the existing corpus thumbnail; no new image selection.",
        "plate": asset["selection"]["plate"],
        "well": asset["selection"]["wells"][plane],
        "site": 1,
        "channel": "MitoTracker Deep Red (w5)",
        "pixel_size_um_yx": dataset["source"]["acquisition"]["pixel_size_um_yx"],
        "shape_yx": list(field.shape),
        "dtype": str(field.dtype),
        "native_pixel_min_max": [int(field.min()), int(field.max())],
        "array_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "pixel_processing": "None. Complete native uint16 field extracted without cropping, filtering, rescaling or denoising.",
        "display": {
            "mapping": "Whole-field linear grayscale; values outside the limits saturate at black or white for display only.",
            "percentiles": asset["preview"]["percentiles"],
            "intensity_limits": limits.tolist(),
            "pixels_below_lower_limit": int(np.count_nonzero(field < limits[0])),
            "pixels_above_upper_limit": int(np.count_nonzero(field > limits[1])),
            "total_pixels": int(field.size),
            "interpolation": "none in vector exports; native raster resolution retained",
            "scale_bar_um": 100,
        },
    }
    output.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"Saved {output.relative_to(ROOT)}: {field.shape}, unchanged {field.dtype} pixels.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_path", help="Path to the complete bbbc022-mito.raw benchmark asset")
    prepare(parser.parse_args().raw_path)
