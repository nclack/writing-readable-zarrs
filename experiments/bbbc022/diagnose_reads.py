#!/usr/bin/env python3
"""Check the first Blosc chunk and an integer-fill metadata view on a CPU job.

The original array is read only. A new view under --output changes just the
metadata spelling of zero and links to the original shard directory.
"""

from __future__ import annotations

import argparse
import ctypes
import dataclasses
import hashlib
import json
import math
import os
import signal
import struct
import subprocess
import sys
import traceback
from pathlib import Path

SOURCE_SHA256 = "1eff677d3f7d6785bdc8e65079613d6ba2c801a19f33503517a12b8df54affc7"
DEFAULT_BLOSC = "/mnt/main0/home/nclack/.pixi/envs/damacy-cpu-deps/lib/libblosc.so"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def source_values(path):
    import numpy as np

    data = Path(path).read_bytes()
    require(hashlib.sha256(data).hexdigest() == SOURCE_SHA256, "Source hash differs")
    return np.frombuffer(data, dtype="<u2").reshape(16, 520, 696)


def blosc_library(path):
    library = ctypes.CDLL(path)
    library.blosc_get_version_string.restype = ctypes.c_char_p
    library.blosc_cbuffer_validate.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    library.blosc_cbuffer_validate.restype = ctypes.c_int
    library.blosc_cbuffer_complib.argtypes = [ctypes.c_void_p]
    library.blosc_cbuffer_complib.restype = ctypes.c_char_p
    library.blosc_decompress_ctx.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_int,
    ]
    library.blosc_decompress_ctx.restype = ctypes.c_int
    return library


def first_chunk(uri, metadata, library, source):
    import numpy as np

    shard_shape = metadata["chunk_grid"]["configuration"]["chunk_shape"]
    config = metadata["codecs"][0]["configuration"]
    chunk_shape = config["chunk_shape"]
    require(
        metadata["data_type"] == "uint16" and len(chunk_shape) == 3,
        "Expected rank-three uint16",
    )
    require(config.get("index_location", "end") == "end", "Expected index at end")
    require(
        [row["name"] for row in config["index_codecs"]] == ["bytes", "crc32c"],
        "Unexpected index codec",
    )
    index_bytes = (
        math.prod(s // c for s, c in zip(shard_shape, chunk_shape, strict=True)) * 16
        + 4
    )
    shard = uri / "c/0/0/0"
    with shard.open("rb") as stream:
        stream.seek(-index_bytes, os.SEEK_END)
        offset, length = struct.unpack("<QQ", stream.read(16))
        raw_size = math.prod(chunk_shape) * 2
        require(
            16 <= length <= 2 * raw_size + 1024,
            "First encoded chunk is unexpectedly large or absent",
        )
        require(
            offset + length <= shard.stat().st_size - index_bytes,
            "First chunk overlaps the index",
        )
        stream.seek(offset)
        encoded = stream.read(length)
    require(len(encoded) == length, "Short chunk read")
    fields = struct.unpack_from("<BBBBIII", encoded)
    header = dict(
        zip(
            (
                "version",
                "codec_version",
                "flags",
                "typesize",
                "raw_bytes",
                "block_bytes",
                "encoded_bytes",
            ),
            fields,
            strict=True,
        )
    )
    require(header["raw_bytes"] == raw_size, "Unexpected decoded size")
    require(
        16 <= header["encoded_bytes"] <= len(encoded), "Header exceeds indexed length"
    )
    expected = np.ascontiguousarray(
        source[tuple(slice(0, n) for n in chunk_shape)]
    ).tobytes()
    observations = []
    for name, payload in (
        ("indexed_length", encoded),
        ("header_length", encoded[: header["encoded_bytes"]]),
    ):
        buffer = ctypes.create_string_buffer(payload)
        size = ctypes.c_size_t()
        validate = library.blosc_cbuffer_validate(
            buffer, len(payload), ctypes.byref(size)
        )
        compressor = library.blosc_cbuffer_complib(buffer)
        output = ctypes.create_string_buffer(raw_size)
        result = None
        equal = None
        if validate == 0 and size.value == raw_size:
            result = library.blosc_decompress_ctx(buffer, output, raw_size, 1)
            equal = result == raw_size and output.raw == expected
        observations.append(
            {
                "input": name,
                "input_bytes": len(payload),
                "validate_return": validate,
                "validated_raw_bytes": size.value,
                "compressor": compressor.decode() if compressor else None,
                "decompress_return": result,
                "decoded_matches_source": equal,
            }
        )
    return {
        "shard_path": str(shard),
        "index_bytes": index_bytes,
        "indexed_offset": offset,
        "indexed_length": length,
        "header": header,
        "indexed_length_minus_header_cbytes": length - header["encoded_bytes"],
        "within_frozen_encoded_limit": length <= raw_size + 16,
        "blosc_version": library.blosc_get_version_string().decode(),
        "observations": observations,
    }


def read_point(args):
    import numpy as np

    result = {
        "uri": args.uri,
        "point": args.point,
        "decode_workers": 1,
        "status": "failed",
    }
    reader = None
    try:
        source = source_values(args.source)
        metadata = json.loads((Path(args.uri) / "zarr.json").read_text())
        chunk_shape = metadata["codecs"][0]["configuration"]["chunk_shape"]
        sys.path.insert(0, args.helpers_dir)
        from shard_grid_readers import DamacyReader

        os.environ["DAMACY_BENCH_READ_MODE"] = "persistent-default"
        workload = {"samples_per_batch": 1, "sample_shape": [1, 1, 1]}
        reader = DamacyReader(
            args.uri,
            workload,
            {"max_chunk_uses_per_batch": 1},
            math.prod(chunk_shape) * 2,
            1,
            16,
        )
        t, y, x = args.point
        expected = np.asarray([[[source[t % 16, y, x]]]], dtype=np.float32)
        hashes = {"0": hashlib.sha256(expected.tobytes()).hexdigest()}
        with reader:
            reader.stats_reset()
            try:
                checked = reader.prepare([args.point], [1, 1, 1])(hashes)
                result.update(status="passed", checked_samples=checked)
            finally:
                result["stats"] = dataclasses.asdict(reader.pipeline.stats())
                result["file_reader"] = reader.file_stats()
    except Exception as error:
        result.update(
            error_type=type(error).__name__,
            message=str(error),
            traceback=traceback.format_exc(),
        )
    write_json(args.result, result)
    return 0 if result["status"] == "passed" else 1


def supervise_point(args, name, uri, point, output):
    path = output / f"{name}.json"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--uri",
        str(uri),
        "--point",
        *(str(n) for n in point),
        "--source",
        args.source,
        "--helpers-dir",
        args.helpers_dir,
        "--result",
        str(path),
    ]
    with (output / f"{name}.log").open("wb") as log:
        process = subprocess.Popen(
            command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )
        timed_out = False
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
    result = json.loads(path.read_text()) if path.exists() else {"status": "no_result"}
    return {
        "name": name,
        "returncode": process.returncode,
        "timed_out": timed_out,
        "result": result,
    }


def diagnose(args):
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    roundtrip = json.loads(Path(args.roundtrip).read_text())
    uri = Path(roundtrip["array_path"])
    metadata_bytes = (uri / "zarr.json").read_bytes()
    metadata = json.loads(metadata_bytes)
    require(
        math.prod(metadata["shape"]) * 2 <= 64 << 20,
        "Use the small preflight volume for this diagnostic",
    )
    require(
        metadata["fill_value"] == 0,
        "This diagnostic changes only zero's numeric spelling",
    )
    source = source_values(args.source)
    report = {
        "source_sha256": SOURCE_SHA256,
        "original_uri": str(uri),
        "original_metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
        "original_fill_value": metadata["fill_value"],
        "original_fill_value_python_type": type(metadata["fill_value"]).__name__,
        "blosc_library": args.blosc_lib,
        "first_chunk": first_chunk(
            uri, metadata, blosc_library(args.blosc_lib), source
        ),
        "metadata_hypothesis": "uint16 parse_fill_value calls json_as_uint, which rejects JSON_NODE_FLAG_NUM_FLOAT even for 0.0; array_meta maps parse failure to DAMACY_DECODE",
    }
    write_json(output / "first-chunk.json", report)
    (output / "original-zarr.json").write_bytes(metadata_bytes)
    view = output / "integer-fill-view"
    view.mkdir()
    edited = dict(metadata)
    edited["fill_value"] = 0
    write_json(view / "zarr.json", edited)
    (view / "c").symlink_to(uri / "c", target_is_directory=True)
    shape = metadata["shape"]
    report["reads"] = [
        supervise_point(args, "original-interior", uri, [0, 0, 0], output),
        supervise_point(args, "integer-fill-interior", view, [0, 0, 0], output),
        supervise_point(
            args,
            "integer-fill-tail-edge",
            view,
            [shape[0] - 1, shape[1] - 1, shape[2] - 1],
            output,
        ),
    ]
    require(
        (uri / "zarr.json").read_bytes() == metadata_bytes,
        "Original metadata changed during diagnosis",
    )
    report["original_metadata_unchanged"] = True
    report["metadata_view_uri"] = str(view)
    write_json(output / "diagnosis.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roundtrip")
    parser.add_argument("--source", required=True)
    parser.add_argument("--helpers-dir", required=True)
    parser.add_argument("--output")
    parser.add_argument("--blosc-lib", default=DEFAULT_BLOSC)
    parser.add_argument("--uri", help=argparse.SUPPRESS)
    parser.add_argument("--point", type=int, nargs=3, help=argparse.SUPPRESS)
    parser.add_argument("--result", help=argparse.SUPPRESS)
    args = parser.parse_args()
    require(
        os.environ.get("SLURM_JOB_ID"),
        "Run this diagnostic inside an allocated Slurm CPU job",
    )
    if args.uri:
        return read_point(args)
    require(args.roundtrip and args.output, "--roundtrip and --output are required")
    return diagnose(args)


if __name__ == "__main__":
    raise SystemExit(main())
