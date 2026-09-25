# Matthew Hartley

a) The DCA array standard and bioformats2raw (which both the IDR and BIA teams
are using for conversion) aren't currently compatible. Chunk and shard extents
along t and c are fixed at 1 in bf2raw, so DCA’s 2D+t chunk example of (16, 1,
1, 128, 128) and "time shard SHOULD be >= 16" aren’t achievable. 2d+t also makes
the 1 GB minimum uncompressed shard recommendation harder.

b) Our existing chunk/shard patterns are typically optimised for interactive
exploration/visualisation (loosely optimised, we haven’t done a lot of
profiling). Even there we already have trade-offs (e.g. plane visualisers vs
orthographic 3D/volume rendering want different chunk shapes and downsampling
regimes). A (16, 1, 1, 128, 128) chunk shape forces loading 16 time points to
display the first plane which is more likely to be painful for viewing (anything
that tries to render thumbnails direct from the OME-Zarr will especially suffer
there).

c) Understanding what downstream consumers want to do would definitely help
us - the visualisation case is easier to understand, but something like model
training often depends on the type of model so more insight there would be
really valuable.
