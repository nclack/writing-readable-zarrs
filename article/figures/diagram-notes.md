# Analytical figure components

These diagrams are exact worked examples and schematic geometry, not benchmark
measurements. They are composed by `diagrams.py`, using the shared typography,
colours and vector export functions in `style.py`. Source and destination shapes
are `[Y, X]` unless a Z axis is explicitly drawn. All byte counts use two bytes
per uint16 element and 1 KiB = 1,024 bytes.

The Nature research figure guide is the project's style baseline, checked
2026-09-25: [specifications](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/)
and [building/exporting](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/).
The 2026-09-26 readability revision follows the user’s request for larger type
and thicker lines for online reading. It intentionally supersedes the earlier
5–7 pt text and 170 mm height limits while preserving editable vectors, clear
labels and scientific meaning. This is an article draft, not a claim of journal
submission compliance.

Reproduce component previews and the allocation table from the repository root:

```sh
article/.venv/bin/python article/figures/diagrams.py
```

The three public drawing functions add artists to a supplied Matplotlib
`SubplotSpec` and do not save or close the parent figure:

- `draw_crop_geometry(fig, spec)`: Figure 1a, designed for 183 × 105 mm.
- `draw_shard_geometry(fig, spec)`: Figure 2a, designed for 183 × 75 mm.
- `draw_conversion_memory(fig, spec)`: Figure 4, designed for 183 × 205 mm.

Preview PDF/SVG/PNG files are in `previews/diagram-*`. The PDF masters preserve
their declared page dimensions and embed editable Arial text. PNGs are 200 dpi
review previews of wholly vector artwork, not source microscopy panels.

## Figure 1a: caption component

**Chunk boundaries determine geometric decoding amplification.** The same
256 × 256-pixel crop starts at `(Y, X) = (64, 64)` in a 512 × 512 uint16 plane.
With 128 × 128 chunks (32 KiB), it intersects nine chunks: 288 KiB decoded for
128 KiB requested, or 2.25×. With 256 × 256 chunks (128 KiB), it intersects four
chunks: 512 KiB decoded, or 4×. Blue marks requested pixels and the crop boundary;
the pale orange region is decoded but unused. Thin lines delimit chunks. The
controls use the 256-square chunk grid: a whole-chunk-aligned 256-square crop and
the complete 512-square array both have decoded/useful ratio 1. These are
uncompressed geometric byte ratios, not measured storage traffic or speed.
Compression, cache reuse and coalesced reads can change bytes transferred. The
measured random-crop example is 256-square; the hypothetical vision transformer
accepts 224-square inputs with 16-square token patches. These do not specify
the storage chunk grid.

**Alt text:** Two equal translated 256-square crops overlay different chunk
grids. A 32 KiB layout decodes nine chunks, 2.25 times the requested bytes; a
128 KiB layout decodes four chunks, four times the requested bytes. Whole-chunk
alignment and full-array controls decode only the requested pixels.

**Long description / calculations:** The crop occupies half-open coordinates
`[64, 320) × [64, 320)`. On the 128-square grid its containing decoded rectangle
is `[0, 384) × [0, 384)`; on the 256-square grid it is the whole 512-square
plane. The decoder is assumed to produce each complete intersected chunk once,
without pre-existing decoded chunks. Useful bytes are `256 × 256 × 2 = 131072`.
Small-chunk decoded bytes are `9 × 128 × 128 × 2 = 294912`; large-chunk decoded
bytes are `4 × 256 × 256 × 2 = 524288`. Unused decoded bytes are respectively
160 KiB and 384 KiB. This chosen offset illustrates the mechanism; it is not
the average over random translations. No compressed-byte size is assigned.

## Figure 2a: caption component

**Concurrent shards are an append-layer geometry.** Orthogonal XY and XZ views
show a Z/Y/X array appended along Z. Heavy lines delimit shard files; fine lines
delimit chunks within each shard. The highlighted XY layer contains 4 × 4 = 16
shard files. The XZ view highlights that same active layer above earlier layers;
Y extends into the page. Both the count and the drawn chunk/shard proportions
are illustrative. The primary measured layer counts are 4, 9, 15 and 30, not a
16-file test. An append-layer count does not establish simultaneous I/O, worker
count, socket assignment or an optimum linked to NFS `nconnect`.

**Alt text:** An XY view shows sixteen shard files, each containing several
chunks. An adjacent XZ view places that active layer at the leading edge of
append along Z. Thick file boundaries and thin chunk boundaries distinguish
the two storage units; sixteen is an illustration, not a measured optimum.

**Long description:** The drawing uses four shard divisions per array dimension
and two chunk divisions per shard dimension to make the hierarchy visible.
These ratios do not depict the benchmark's approximately 1 GiB raw shards or
its exact chunk counts. Each XY square enclosed by heavy lines corresponds to
one active file; the sixteen squares together form the D−1 layer for D = 3.
The side view is a section through one Y position, not sixteen overlapping
file streams or a measured scheduling diagram.

## Figure 4: caption

**Conversion memory depends on the live allocations.** This analytical example
rechunks a 512 × 512 uint16 array from `[128, 256]` source chunks to `[256, 128]`
destination chunks; either chunk contains 64 KiB. **a**, One 64 KiB decoded
source chunk is processed at a time, in row-major order 1–8. A full 64 KiB
destination allocation is created on first touch, even when only half its
pixels are filled. The current source chunk is the processing block. Input is
released after copying, then complete outputs are encoded and written
synchronously and released before the next source chunk. **b**, The live
unfinished outputs after steps 1–4 occupy 128, 256, 128 and 0 KiB. Steps 5–8
repeat that sequence for the lower half. Orange outlines mark live output
allocations; blue shows filled pixels, pale orange their unfilled space, and
gray marks output already written and released. **c**, During steps 2, 3, 6
and 7, the largest raw-array live set comprises one 64 KiB source and four
64 KiB destination allocations: 320 KiB. Input and output allocations are
distinct and each is counted once; views into them add no new allocation.
The model has no prefetch, decoded-source cache or asynchronous pending-write
queue, and at most one source request and one encoded-output buffer. Codec
workspaces, compressed buffers, metadata and implementation overhead are
additional. TIFF decoding and queued images require their own budget for TIFF
streaming but are absent from this Zarr-to-Zarr example. No complete shard
buffer is assumed. This is an allocation model, not measured process or GPU
memory, and not a universal rechunking bound.

**Alt text:** A 512-square uint16 array changes from wide source chunks to tall
destination chunks. Reading one source at a time leaves two, four, two, then
zero unfinished output chunks. A full allocation may be only half filled. The
largest raw-array live set is 320 KiB; codec buffers, compressed bytes and
process overhead add memory beyond that analytical bound.

### Exact conversion algorithm and allocation record

The model uses independent host source/destination allocations and copy-based
assembly. It assumes the reader can emit one decoded source chunk without
retaining an extra decoded copy, and that the writer can encode/write an output
chunk without a complete raw shard allocation. Those are stated design
assumptions, not claims about all conversion implementations. The grid and
allocation count do not specify or simulate an existing conversion library.

1. Read and decode the next source chunk into one 64 KiB allocation.
2. Allocate any first-touched destination chunks, each at its full 64 KiB size.
3. Copy the two source half-blocks into the corresponding destination chunks.
   These source slices are views; no intermediate copy is counted.
4. Release the decoded source allocation.
5. Encode and synchronously write each complete destination chunk, one at a
   time. Release its raw and encoded allocations after that write. Do not begin
   the next source read before complete outputs are released.

The sequence is generated by `conversion_steps()` and exported to
[`data/diagram-conversion-buffers.csv`](data/diagram-conversion-buffers.csv).
Its exact raw-array allocations are:

| Source step | Destinations allocated before flush | Arrays live during copy (KiB) | Destinations written | Retained outputs after step (KiB) |
|---|---:|---:|---:|---:|
| 1 | 2 | 192 | 0 | 128 |
| 2 | 4 | 320 | 0 | 256 |
| 3 | 4 | 320 | 2 | 128 |
| 4 | 2 | 192 | 2 | 0 |
| 5 | 2 | 192 | 0 | 128 |
| 6 | 4 | 320 | 0 | 256 |
| 7 | 4 | 320 | 2 | 128 |
| 8 | 2 | 192 | 2 | 0 |

| Buffer class | Lifetime / explicit limit | Included in 320 KiB? |
|---|---|---|
| Decoded source | One 64 KiB allocation; read through end of copy | Yes |
| Raw destination | Up to four 64 KiB allocations; first touch through completed write | Yes |
| Compressed source bytes and decoder workspace | One read/decode at a time; bytes depend on implementation and codec | No |
| Encoded output and encoder workspace | One encode/write at a time; release after synchronous write | No |
| Prefetched sources, source cache, asynchronous pending writes | Zero in this model | Not present |
| TIFF decoder and queued images | Different streaming workload; must set its own queue bounds | Not present |
| Metadata, runtime overhead, allocator retention, other caches | Outside this allocation model | No |

A synchronous write here means the conversion waits for the write operation
before releasing its buffer; it does not assert durable storage. The model
requires neither a full-shard buffer nor concurrent complete output encoding.
Increasing prefetch, changing traversal, allocating partial buffers differently
or retaining an additional decoder output copy would change the bound.

## Review record

The 2026-09-26 component previews were rendered at the article’s 880-pixel
display width and visually inspected for overlapping text, clipping, line
hierarchy and correspondence between the illustrated regions and the stated
integer geometry. The additional files `previews/diagram-*-880.png` retain
that check. Fonts are fixed to Arial: ordinary labels are 9–10 pt and panel
letters are 12 pt. Chunk grids use 0.8 pt lines; ordinary lines use 1–1.2 pt;
shard boundaries and active-region outlines use 1.5 pt. Colour is coupled with
boundaries, direct labels and numerical counts. Each component uses shared
column centres and separate title, geometry, metric and legend rows. Dense
qualifications remain in the captions rather than shrinking the artwork text.

A rendered text-bounding-box audit found no pairwise text intersections or
text extending outside any component canvas. Final assembled figures still
need their own review because their enclosing panels can change scale. Crop
geometry and the eight-step memory accounting are unchanged.
