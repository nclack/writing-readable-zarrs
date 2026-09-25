The first 54-shard sample, `046-fast-target54-r4-sample` in Slurm job
`3836189`, failed after 1.055 seconds with native `{"status":"error"}` and
no measurement. Its raw request, result and logs remain under
`jobs/gpu-3836189/measurements/046-fast-target54-r4-sample/` in the study root.
This attempt supplies no throughput observation.

The frozen benchmark declares `METER_MAX_WRITERS 32` in
`writer/bench/sink_metering.h:9`. In `sink_metering.c:84`, `metering_open`
opens the underlying shard and then searches those 32 wrappers. It returns
NULL when none is free. The 54-shard layout needs 54 simultaneously active
wrappers; the passing 30-shard layout fits. `src/zarr/shard_write_plan.c:620`
propagates the NULL writer as a delivery error, and `bench/bench_util.c:484`
returns the append error from `pump_measurement`, matching the retained log.

Batch divisibility does not explain this failure. `src/zarr/host_batch.c:199`
and `:249` explicitly split a batch at a temporal shard boundary. A batch
of 19 epochs can therefore cross the boundary of a 16,384-epoch shard.

The study-only `writer-metering.patch` raises the wrapper capacity from 32
to 64. It changes one header constant. The 64 MiB target batch, four output
buffers, 32 I/O workers, per-file write limit, geometry and codec remain
unchanged. The old header SHA-256 is
`3fe30f2377bdf8ce602a931570c5c52a6ee542c5bbd75486353228a8a79b84c1`;
the patched header SHA-256 is
`140df2d3624db8b7376f2519ea569352bebd22022b22cad8adbca087650a4c8d`.

The CPU rebuild preserves the previous source manifest and writer identity,
pins both header hashes, and records the new binary and patch hashes. No
direct metering-wrapper tests are present in the frozen source. CPU build
success does not establish successful GPU execution of the 54-shard case.

The completed 18 fixed-layout records remain unchanged. The interrupted
shard sweep remains raw evidence and is excluded from the new primary
phase. All samples in the resumed primary shard experiment use the rebuilt
binary; the original failure is retained as a failed attempt.
