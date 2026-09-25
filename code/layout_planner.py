#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "pydantic>=2.13,<3",
#   "rich>=15,<16",
#   "typer>=0.27,<1",
# ]
# ///

"""Explainable chunk-and-shard planning for Zarr arrays.

The planner deliberately has two nested phases:

1. generate aspect-guided chunks and reject those that fail chunk limits;
2. generate configurations of chunks per shard for every surviving chunk and
   reject layout limits;
3. order the passing layouts with one documented lexicographic key.

Run ``uv run layout_planner.py --help`` for the command-line interface. The
models and ``run_planner`` function are also imported by layout_explorer.py.
"""

from __future__ import annotations

import itertools
import json
import math
import random
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal, Sequence

import typer
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table


Shape = tuple[int, ...]
Coordinate = tuple[int, ...]


# Policy input schema ---------------------------------------------------------


class PolicyModel(BaseModel):
    """Base model which treats misspelled policy keys as errors."""

    model_config = ConfigDict(extra="forbid")


class ArraySpec(PolicyModel):
    axes: list[str] = Field(min_length=1)
    shape: list[int] = Field(min_length=1)
    bytes_per_element: int = Field(gt=0)


class SearchSpec(PolicyModel):
    minimum_chunk_bytes: int = Field(gt=0)
    maximum_chunk_bytes: int = Field(gt=0)
    minimum_encoding_throughput_bytes_per_second: float = Field(gt=0.0)
    chunk_budget_factor: float = Field(gt=1.0)
    shard_budget_factor: float = Field(gt=1.0)
    neighbor_steps: int = Field(default=1, ge=0, le=4)
    compression_tolerance: float = Field(default=0.10, ge=0.0)
    maximum_enumerated_chunks_per_sample: int = Field(default=100_000, gt=0)

    @model_validator(mode="after")
    def validate_bounds(self) -> SearchSpec:
        if self.minimum_chunk_bytes > self.maximum_chunk_bytes:
            raise ValueError("minimum_chunk_bytes must not exceed maximum_chunk_bytes")
        return self


class EstimateSpec(PolicyModel):
    encoded_fraction: float = Field(gt=0.0, le=1.0)
    encoding_throughput_bytes_per_second: float = Field(gt=0.0)


class StorageSpec(PolicyModel):
    maximum_shards: int = Field(gt=0)
    minimum_efficient_object_bytes: int = Field(gt=0)
    maximum_shard_bytes: int = Field(gt=0)
    range_reads: bool
    index_cache: Literal["cold", "warm"]
    index_bytes_per_chunk: int = Field(default=16, ge=0)
    checksum_bytes_per_shard: int = Field(default=4, ge=0)

    @model_validator(mode="after")
    def validate_sizes(self) -> StorageSpec:
        if self.minimum_efficient_object_bytes > self.maximum_shard_bytes:
            raise ValueError(
                "minimum_efficient_object_bytes must not exceed maximum_shard_bytes"
            )
        return self


class WriterSpec(PolicyModel):
    name: str = Field(min_length=1)
    maximum_memory_bytes: int = Field(gt=0)
    fixed_memory_bytes: int = Field(ge=0)
    unfinished_chunks: int = Field(ge=0)
    active_write_shards: int = Field(ge=0)
    fixed_bytes_per_active_shard: int = Field(ge=0)
    retained_shard_payload_fraction: float = Field(ge=0.0)
    memory_provenance: Literal["modeled"]


class WorkloadSpec(PolicyModel):
    name: str = Field(min_length=1)
    selection_shape: list[int] = Field(min_length=1)
    sample_count: int = Field(gt=0)
    selections_per_sample: int = Field(default=1, gt=0)
    seed: int = 0
    maximum_p95_decode_amplification: float = Field(ge=1.0)
    maximum_p95_requests: float = Field(gt=0.0)
    maximum_p95_transfer_amplification: float = Field(ge=1.0)
    minimum_p05_distinct_shards: float | None = Field(default=None, gt=0.0)


class AspectProfile(PolicyModel):
    name: str = Field(min_length=1)
    base_shape: list[float] = Field(min_length=1)
    growth_weights: list[float] = Field(min_length=1)


class ChunkMeasurement(PolicyModel):
    shape: list[int] = Field(min_length=1)
    encoded_fraction: float = Field(gt=0.0, le=1.0)
    encoding_throughput_bytes_per_second: float = Field(gt=0.0)
    note: str = ""


class PlannerPolicy(PolicyModel):
    array: ArraySpec
    search: SearchSpec
    estimates: EstimateSpec
    storage: StorageSpec
    writer: WriterSpec
    workloads: list[WorkloadSpec] = Field(min_length=1)
    chunk_profiles: list[AspectProfile] = Field(min_length=1)
    shard_profiles: list[AspectProfile] = Field(min_length=1)
    chunk_measurements: list[ChunkMeasurement] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dimensions(self) -> PlannerPolicy:
        rank = len(self.array.axes)
        if len(set(self.array.axes)) != rank:
            raise ValueError("array axis names must be unique")
        if len(self.array.shape) != rank or any(
            value <= 0 for value in self.array.shape
        ):
            raise ValueError("array.shape must contain one positive extent per axis")

        names = [workload.name for workload in self.workloads]
        if len(set(names)) != len(names):
            raise ValueError("workload names must be unique")

        for workload in self.workloads:
            self._check_rank(
                f"workload {workload.name!r} selection_shape",
                workload.selection_shape,
                rank,
            )
            if any(value <= 0 for value in workload.selection_shape):
                raise ValueError(
                    f"workload {workload.name!r} selection extents must be positive"
                )
            if any(
                requested > available
                for requested, available in zip(
                    workload.selection_shape, self.array.shape
                )
            ):
                raise ValueError(
                    f"workload {workload.name!r} selection exceeds the array"
                )

        for kind, profiles in (
            ("chunk", self.chunk_profiles),
            ("shard", self.shard_profiles),
        ):
            profile_names = [profile.name for profile in profiles]
            if len(set(profile_names)) != len(profile_names):
                raise ValueError(f"{kind} profile names must be unique")
            for profile in profiles:
                self._check_rank(
                    f"{kind} profile {profile.name!r} base_shape",
                    profile.base_shape,
                    rank,
                )
                self._check_rank(
                    f"{kind} profile {profile.name!r} growth_weights",
                    profile.growth_weights,
                    rank,
                )
                if any(value <= 0 for value in profile.base_shape):
                    raise ValueError(
                        f"{kind} profile {profile.name!r} base values must be positive"
                    )
                if any(value < 0 for value in profile.growth_weights):
                    raise ValueError(
                        f"{kind} profile {profile.name!r} growth weights cannot be negative"
                    )

        measured_shapes: set[Shape] = set()
        for measurement in self.chunk_measurements:
            self._check_rank("chunk measurement shape", measurement.shape, rank)
            shape = tuple(measurement.shape)
            if shape in measured_shapes:
                raise ValueError(f"duplicate chunk measurement for shape {shape}")
            measured_shapes.add(shape)
            if any(value <= 0 for value in shape):
                raise ValueError("chunk measurement extents must be positive")
            if any(value > cap for value, cap in zip(shape, self.array.shape)):
                raise ValueError(f"measured chunk shape {shape} exceeds the array")
            size = math.prod(shape) * self.array.bytes_per_element
            if (
                not self.search.minimum_chunk_bytes
                <= size
                <= self.search.maximum_chunk_bytes
            ):
                raise ValueError(
                    f"measured chunk shape {shape} is outside the chunk-byte search range"
                )
        return self

    @staticmethod
    def _check_rank(label: str, values: Sequence[object], rank: int) -> None:
        if len(values) != rank:
            raise ValueError(f"{label} has rank {len(values)}; expected {rank}")


# Planner result schema -------------------------------------------------------


class Distribution(PolicyModel):
    minimum: float
    p05: float
    p50: float
    p95: float
    maximum: float


class ChunkWorkloadResult(PolicyModel):
    workload: str
    chunks: Distribution
    decode_amplification: Distribution


class ChunkCandidateResult(PolicyModel):
    shape: Shape
    origin_profiles: tuple[str, ...]
    target_byte_budgets: tuple[int, ...]
    raw_chunk_bytes: int
    encoded_fraction: float
    encoding_throughput_bytes_per_second: float
    compression_provenance: str
    throughput_provenance: str
    workloads: tuple[ChunkWorkloadResult, ...]
    worst_decode_limit_utilization: float
    passes: bool
    rejection_reasons: tuple[str, ...]


class PairWorkloadResult(PolicyModel):
    workload: str
    requests: Distribution
    transfer_amplification: Distribution
    distinct_shards: Distribution


class LayoutCandidateResult(PolicyModel):
    chunk_shape: Shape
    shard_shape_in_chunks: Shape
    shard_origin_profiles: tuple[str, ...]
    target_shard_byte_budgets: tuple[int, ...]
    raw_chunk_bytes: int
    total_chunks: int
    shard_grid_shape: Shape
    total_shards: int
    estimated_dataset_bytes: int
    average_shard_bytes: int
    maximum_shard_bytes: int
    estimated_writer_memory_bytes: int
    writer_memory_provenance: str
    workloads: tuple[PairWorkloadResult, ...]
    chunk_worst_decode_limit_utilization: float
    worst_request_limit_utilization: float
    minimum_p05_distinct_shards: float
    passes: bool
    rejection_reasons: tuple[str, ...]


class PlanResult(PolicyModel):
    policy_path: str
    policy: PlannerPolicy
    best_candidate_encoded_fraction: float
    chunk_candidates: tuple[ChunkCandidateResult, ...]
    layout_candidates: tuple[LayoutCandidateResult, ...]
    selected: LayoutCandidateResult | None
    limitations: tuple[str, ...]


# Internal selection geometry ------------------------------------------------


class PlannerError(RuntimeError):
    """The policy is valid, but the bounded planner cannot evaluate it."""


@dataclass(frozen=True)
class Selection:
    start: Shape
    shape: Shape


@dataclass(frozen=True)
class SelectionBatch:
    selections: tuple[Selection, ...]


@dataclass(frozen=True)
class BatchGeometry:
    chunk_coordinates: tuple[Coordinate, ...]
    decoded_bytes: int
    useful_bytes: int


@dataclass(frozen=True)
class WorkloadGeometry:
    workload: WorkloadSpec
    batches: tuple[BatchGeometry, ...]


@dataclass
class CandidateOrigin:
    profiles: set[str] = field(default_factory=set)
    target_budgets: set[int] = field(default_factory=set)


@dataclass
class ChunkState:
    result: ChunkCandidateResult
    geometry: tuple[WorkloadGeometry, ...]


LIMITATIONS = (
    "Selections are generated rectangles, not imported application traces.",
    "Compression is modeled globally unless an exact chunk-shape measurement overrides it.",
    "Generated selection batches are independent; spatial and temporal locality across batches is not represented.",
    "Only all-cold or all-warm shard-index access is modeled; payload and decoded-chunk caches are absent.",
    "Latency, scheduling, and time to first displayed pixel are not modeled.",
    "Range requests are not coalesced.",
    "Each multiscale level must be planned as a separate array.",
    "Object-store multipart limits are not modeled.",
    "End-to-end conversion throughput must be measured after planning; only encoding throughput is gated here.",
    "Writer working memory follows a declared model; measured layout overrides are not implemented yet.",
    "Fill-value chunk omission is not modeled; every chunk-grid cell that intersects the array contributes an encoded payload estimate.",
)


# Aspect-guided candidate generation -----------------------------------------


def load_policy(path: Path) -> PlannerPolicy:
    """Load and validate a TOML planner policy."""

    return PlannerPolicy.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))


def _geometric_budgets(minimum: int, maximum: int, factor: float) -> tuple[int, ...]:
    if minimum > maximum:
        minimum = maximum
    values = [minimum]
    while values[-1] < maximum:
        candidate = min(maximum, math.ceil(values[-1] * factor))
        if candidate <= values[-1]:
            candidate = values[-1] + 1
        values.append(candidate)
    return tuple(values)


def _continuous_aspect_shape(
    target_elements: float,
    base_shape: Sequence[float],
    growth_weights: Sequence[float],
    caps: Shape,
) -> tuple[float, ...]:
    """Fit one log-space scale parameter to an element-count target."""

    def shape_at(scale: float) -> tuple[float, ...]:
        return tuple(
            min(float(cap), max(1.0, base * (2.0 ** (scale * weight))))
            for base, weight, cap in zip(base_shape, growth_weights, caps)
        )

    low, high = -64.0, 64.0
    for _ in range(96):
        middle = (low + high) / 2.0
        if math.prod(shape_at(middle)) < target_elements:
            low = middle
        else:
            high = middle
    return shape_at((low + high) / 2.0)


def _nearest_power_of_two(value: float) -> int:
    if value <= 1.0:
        return 1
    lower = 2 ** math.floor(math.log2(value))
    upper = lower * 2
    return int(lower if value / lower <= upper / value else upper)


def _quantize_shape(values: Sequence[float], caps: Shape) -> Shape:
    return tuple(
        min(cap, max(1, _nearest_power_of_two(value)))
        for value, cap in zip(values, caps)
    )


def _neighbor_shapes(
    shape: Shape,
    caps: Shape,
    growth_weights: Sequence[float],
    steps: int,
) -> set[Shape]:
    neighbors = {shape}
    for dimension, weight in enumerate(growth_weights):
        if weight <= 0:
            continue
        for step in range(1, steps + 1):
            factor = 2**step
            for new_extent in (
                max(1, shape[dimension] // factor),
                min(caps[dimension], shape[dimension] * factor),
            ):
                candidate = list(shape)
                candidate[dimension] = new_extent
                neighbors.add(tuple(candidate))
    return neighbors


def _add_origin(
    candidates: dict[Shape, CandidateOrigin],
    shape: Shape,
    profile: str,
    budget: int,
) -> None:
    origin = candidates.setdefault(shape, CandidateOrigin())
    origin.profiles.add(profile)
    origin.target_budgets.add(budget)


def generate_chunk_candidates(policy: PlannerPolicy) -> dict[Shape, CandidateOrigin]:
    candidates: dict[Shape, CandidateOrigin] = {}
    caps = tuple(policy.array.shape)
    budgets = _geometric_budgets(
        policy.search.minimum_chunk_bytes,
        policy.search.maximum_chunk_bytes,
        policy.search.chunk_budget_factor,
    )
    for profile in policy.chunk_profiles:
        for budget in budgets:
            target_elements = budget / policy.array.bytes_per_element
            continuous = _continuous_aspect_shape(
                target_elements,
                profile.base_shape,
                profile.growth_weights,
                caps,
            )
            center = _quantize_shape(continuous, caps)
            for shape in _neighbor_shapes(
                center,
                caps,
                profile.growth_weights,
                policy.search.neighbor_steps,
            ):
                raw_bytes = math.prod(shape) * policy.array.bytes_per_element
                if (
                    policy.search.minimum_chunk_bytes
                    <= raw_bytes
                    <= policy.search.maximum_chunk_bytes
                ):
                    _add_origin(candidates, shape, profile.name, budget)

    for measurement in policy.chunk_measurements:
        _add_origin(
            candidates,
            tuple(measurement.shape),
            "measured candidate",
            math.prod(measurement.shape) * policy.array.bytes_per_element,
        )
    if not candidates:
        raise PlannerError(
            "the aspect profiles generated no chunks inside the byte range"
        )
    return candidates


# Exact chunk/selection geometry ---------------------------------------------


def _generated_workloads(
    policy: PlannerPolicy,
) -> dict[str, tuple[SelectionBatch, ...]]:
    generated: dict[str, tuple[SelectionBatch, ...]] = {}
    for workload in policy.workloads:
        random_source = random.Random(workload.seed)
        batches: list[SelectionBatch] = []
        for sample_index in range(workload.sample_count):
            selections: list[Selection] = []
            for _ in range(workload.selections_per_sample):
                if workload.selections_per_sample == 1 and sample_index < 3:
                    position = (0.0, 1.0, 0.5)[sample_index]
                    start = tuple(
                        round((available - requested) * position)
                        for available, requested in zip(
                            policy.array.shape, workload.selection_shape
                        )
                    )
                else:
                    start = tuple(
                        random_source.randint(0, available - requested)
                        for available, requested in zip(
                            policy.array.shape, workload.selection_shape
                        )
                    )
                selections.append(
                    Selection(start=start, shape=tuple(workload.selection_shape))
                )
            batches.append(SelectionBatch(selections=tuple(selections)))
        generated[workload.name] = tuple(batches)
    return generated


def _raw_chunk_bytes(policy: PlannerPolicy, chunk_shape: Shape) -> int:
    """Return bytes in one full decoded chunk representation.

    Zarr edge chunks retain the declared chunk shape; array bounds only reduce
    the in-bounds extent, not the decoded chunk representation.
    """

    return math.prod(chunk_shape) * policy.array.bytes_per_element


def _chunk_coordinates(selection: Selection, chunk_shape: Shape) -> itertools.product:
    ranges = tuple(
        range(start // chunk, (start + extent - 1) // chunk + 1)
        for start, extent, chunk in zip(selection.start, selection.shape, chunk_shape)
    )
    return itertools.product(*ranges)


def _distribution(values: Sequence[float | int]) -> Distribution:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise PlannerError("cannot summarize an empty measurement distribution")

    def nearest_rank(probability: float) -> float:
        index = max(0, math.ceil(probability * len(ordered)) - 1)
        return ordered[index]

    return Distribution(
        minimum=ordered[0],
        p05=nearest_rank(0.05),
        p50=nearest_rank(0.50),
        p95=nearest_rank(0.95),
        maximum=ordered[-1],
    )


def _evaluate_chunk(
    policy: PlannerPolicy,
    shape: Shape,
    origin: CandidateOrigin,
    samples: dict[str, tuple[SelectionBatch, ...]],
) -> ChunkState:
    measurements = {tuple(item.shape): item for item in policy.chunk_measurements}
    measurement = measurements.get(shape)
    if measurement is None:
        encoded_fraction = policy.estimates.encoded_fraction
        throughput = policy.estimates.encoding_throughput_bytes_per_second
        compression_provenance = "modeled global estimate"
        throughput_provenance = "modeled global estimate"
    else:
        encoded_fraction = measurement.encoded_fraction
        throughput = measurement.encoding_throughput_bytes_per_second
        suffix = f": {measurement.note}" if measurement.note else ""
        compression_provenance = f"measured exact shape{suffix}"
        throughput_provenance = f"measured exact shape{suffix}"

    workload_results: list[ChunkWorkloadResult] = []
    workload_geometry: list[WorkloadGeometry] = []
    reasons: list[str] = []
    worst_decode_utilization = 0.0

    for workload in policy.workloads:
        batch_geometries: list[BatchGeometry] = []
        decoded_amplifications: list[float] = []
        chunk_counts: list[int] = []
        for sample_index, batch in enumerate(samples[workload.name]):
            coordinates: set[Coordinate] = set()
            useful_bytes = 0
            for selection in batch.selections:
                useful_bytes += (
                    math.prod(selection.shape) * policy.array.bytes_per_element
                )
                for coordinate in _chunk_coordinates(selection, shape):
                    coordinates.add(tuple(coordinate))
                    if (
                        len(coordinates)
                        > policy.search.maximum_enumerated_chunks_per_sample
                    ):
                        raise PlannerError(
                            f"chunk {shape}, workload {workload.name!r}, sample {sample_index} "
                            "exceeds maximum_enumerated_chunks_per_sample"
                        )
            ordered_coordinates = tuple(sorted(coordinates))
            decoded_bytes = len(ordered_coordinates) * _raw_chunk_bytes(policy, shape)
            batch_geometries.append(
                BatchGeometry(
                    chunk_coordinates=ordered_coordinates,
                    decoded_bytes=decoded_bytes,
                    useful_bytes=useful_bytes,
                )
            )
            decoded_amplifications.append(decoded_bytes / useful_bytes)
            chunk_counts.append(len(ordered_coordinates))

        decode_distribution = _distribution(decoded_amplifications)
        chunk_distribution = _distribution(chunk_counts)
        workload_results.append(
            ChunkWorkloadResult(
                workload=workload.name,
                chunks=chunk_distribution,
                decode_amplification=decode_distribution,
            )
        )
        workload_geometry.append(
            WorkloadGeometry(workload=workload, batches=tuple(batch_geometries))
        )
        utilization = (
            decode_distribution.p95 / workload.maximum_p95_decode_amplification
        )
        worst_decode_utilization = max(worst_decode_utilization, utilization)
        if utilization > 1.0:
            reasons.append(
                f"{workload.name}: p95 decode amplification "
                f"{decode_distribution.p95:.3g} > {workload.maximum_p95_decode_amplification:.3g}"
            )

    if throughput < policy.search.minimum_encoding_throughput_bytes_per_second:
        reasons.append(
            "encoding throughput "
            f"{throughput:.3g} B/s < "
            f"{policy.search.minimum_encoding_throughput_bytes_per_second:.3g} B/s"
        )

    return ChunkState(
        result=ChunkCandidateResult(
            shape=shape,
            origin_profiles=tuple(sorted(origin.profiles)),
            target_byte_budgets=tuple(sorted(origin.target_budgets)),
            raw_chunk_bytes=_raw_chunk_bytes(policy, shape),
            encoded_fraction=encoded_fraction,
            encoding_throughput_bytes_per_second=throughput,
            compression_provenance=compression_provenance,
            throughput_provenance=throughput_provenance,
            workloads=tuple(workload_results),
            worst_decode_limit_utilization=worst_decode_utilization,
            passes=not reasons,
            rejection_reasons=tuple(reasons),
        ),
        geometry=tuple(workload_geometry),
    )


def _apply_compression_constraint(
    policy: PlannerPolicy, states: list[ChunkState]
) -> float:
    best = min(state.result.encoded_fraction for state in states)
    maximum = best * (1.0 + policy.search.compression_tolerance)
    for state in states:
        reasons = list(state.result.rejection_reasons)
        if state.result.encoded_fraction > maximum:
            reasons.append(
                f"encoded fraction {state.result.encoded_fraction:.3g} > "
                f"best {best:.3g} x (1 + {policy.search.compression_tolerance:.3g})"
            )
        state.result = state.result.model_copy(
            update={"passes": not reasons, "rejection_reasons": tuple(reasons)}
        )
    return best


# Shard generation and candidate-layout scoring ------------------------------


def _chunk_grid(policy: PlannerPolicy, chunk_shape: Shape) -> Shape:
    return tuple(
        math.ceil(available / chunk)
        for available, chunk in zip(policy.array.shape, chunk_shape)
    )


def _estimated_shard_bytes_at(
    policy: PlannerPolicy,
    chunk_shape: Shape,
    chunks_per_shard: Shape,
    shard_coordinate: Coordinate,
    encoded_fraction: float,
) -> int:
    chunk_counts = []
    for available_chunks, shard_extent, coordinate in zip(
        _chunk_grid(policy, chunk_shape), chunks_per_shard, shard_coordinate
    ):
        start = coordinate * shard_extent
        stop = min(available_chunks, start + shard_extent)
        chunk_counts.append(max(0, stop - start))
    raw_bytes = math.prod(chunk_counts) * _raw_chunk_bytes(policy, chunk_shape)
    index_bytes = math.prod(chunks_per_shard) * policy.storage.index_bytes_per_chunk
    return (
        math.ceil(raw_bytes * encoded_fraction)
        + index_bytes
        + policy.storage.checksum_bytes_per_shard
    )


def generate_shard_candidates(
    policy: PlannerPolicy,
    chunk: ChunkCandidateResult,
) -> dict[Shape, CandidateOrigin]:
    candidates: dict[Shape, CandidateOrigin] = {}
    caps = _chunk_grid(policy, chunk.shape)
    decoded_dataset_bytes = math.prod(caps) * chunk.raw_chunk_bytes
    payload_bytes = math.ceil(decoded_dataset_bytes * chunk.encoded_fraction)
    minimum_index_bytes = math.prod(caps) * policy.storage.index_bytes_per_chunk
    lower_bound = max(
        policy.storage.minimum_efficient_object_bytes,
        math.ceil((payload_bytes + minimum_index_bytes) / policy.storage.maximum_shards)
        + policy.storage.checksum_bytes_per_shard,
    )
    budgets = _geometric_budgets(
        lower_bound,
        policy.storage.maximum_shard_bytes,
        policy.search.shard_budget_factor,
    )
    estimated_stored_chunk_bytes = max(
        1.0,
        chunk.raw_chunk_bytes * chunk.encoded_fraction
        + policy.storage.index_bytes_per_chunk,
    )
    for profile in policy.shard_profiles:
        for budget in budgets:
            target_chunks = budget / estimated_stored_chunk_bytes
            continuous = _continuous_aspect_shape(
                target_chunks,
                profile.base_shape,
                profile.growth_weights,
                caps,
            )
            center = _quantize_shape(continuous, caps)
            for shape in _neighbor_shapes(
                center,
                caps,
                profile.growth_weights,
                policy.search.neighbor_steps,
            ):
                _add_origin(candidates, shape, profile.name, budget)

    # Boundary cases improve diagnostics when no aspect-guided shape passes.
    _add_origin(candidates, tuple(1 for _ in caps), "one chunk per shard", 0)
    _add_origin(candidates, caps, "one shard", policy.storage.maximum_shard_bytes)
    return candidates


def _evaluate_layout(
    policy: PlannerPolicy,
    chunk_state: ChunkState,
    chunks_per_shard: Shape,
    origin: CandidateOrigin,
) -> LayoutCandidateResult:
    chunk = chunk_state.result
    chunk_grid = _chunk_grid(policy, chunk.shape)
    shard_grid = tuple(
        math.ceil(available_chunks / chunk_count)
        for available_chunks, chunk_count in zip(chunk_grid, chunks_per_shard)
    )
    total_chunks = math.prod(chunk_grid)
    total_shards = math.prod(shard_grid)
    index_bytes_per_shard = (
        math.prod(chunks_per_shard) * policy.storage.index_bytes_per_chunk
        + policy.storage.checksum_bytes_per_shard
    )
    estimated_dataset_bytes = (
        math.ceil(total_chunks * chunk.raw_chunk_bytes * chunk.encoded_fraction)
        + total_shards * index_bytes_per_shard
    )
    average_shard_bytes = math.ceil(estimated_dataset_bytes / total_shards)
    maximum_chunks_in_shard = math.prod(
        min(available_chunks, shard_extent)
        for available_chunks, shard_extent in zip(chunk_grid, chunks_per_shard)
    )
    maximum_shard_bytes = (
        math.ceil(
            maximum_chunks_in_shard
            * chunk.raw_chunk_bytes
            * chunk.encoded_fraction
        )
        + index_bytes_per_shard
    )

    active_shards = min(policy.writer.active_write_shards, total_shards)
    unfinished_chunks = min(policy.writer.unfinished_chunks, total_chunks)
    writer_memory = math.ceil(
        policy.writer.fixed_memory_bytes
        + unfinished_chunks * chunk.raw_chunk_bytes
        + active_shards
        * (
            policy.writer.fixed_bytes_per_active_shard
            + policy.writer.retained_shard_payload_fraction * maximum_shard_bytes
        )
    )

    reasons: list[str] = []
    if total_shards > policy.storage.maximum_shards:
        reasons.append(
            f"shard count {total_shards:,} > {policy.storage.maximum_shards:,}"
        )
    if average_shard_bytes < policy.storage.minimum_efficient_object_bytes:
        reasons.append(
            f"average stored shard bytes {average_shard_bytes:,} < "
            f"{policy.storage.minimum_efficient_object_bytes:,}"
        )
    if maximum_shard_bytes > policy.storage.maximum_shard_bytes:
        reasons.append(
            f"maximum stored shard bytes {maximum_shard_bytes:,} > "
            f"{policy.storage.maximum_shard_bytes:,}"
        )
    if writer_memory > policy.writer.maximum_memory_bytes:
        reasons.append(
            "writer working memory "
            f"{writer_memory:,} > {policy.writer.maximum_memory_bytes:,}"
        )

    workload_results: list[PairWorkloadResult] = []
    worst_request_utilization = 0.0
    minimum_distinct_shards = math.inf
    for geometry in chunk_state.geometry:
        requests: list[int] = []
        transfer_amplifications: list[float] = []
        distinct_shards: list[int] = []
        for batch in geometry.batches:
            touched_shards = {
                tuple(
                    coordinate[dimension] // chunks_per_shard[dimension]
                    for dimension in range(len(chunks_per_shard))
                )
                for coordinate in batch.chunk_coordinates
            }
            if policy.storage.range_reads:
                request_count = len(batch.chunk_coordinates)
                transferred_bytes = len(batch.chunk_coordinates) * math.ceil(
                    chunk.raw_chunk_bytes * chunk.encoded_fraction
                )
                if policy.storage.index_cache == "cold":
                    request_count += len(touched_shards)
                    transferred_bytes += len(touched_shards) * index_bytes_per_shard
            else:
                request_count = len(touched_shards)
                transferred_bytes = sum(
                    _estimated_shard_bytes_at(
                        policy,
                        chunk.shape,
                        chunks_per_shard,
                        coordinate,
                        chunk.encoded_fraction,
                    )
                    for coordinate in touched_shards
                )
            requests.append(request_count)
            estimated_useful_encoded_bytes = batch.useful_bytes * chunk.encoded_fraction
            transfer_amplifications.append(
                transferred_bytes / estimated_useful_encoded_bytes
            )
            distinct_shards.append(len(touched_shards))

        request_distribution = _distribution(requests)
        transfer_distribution = _distribution(transfer_amplifications)
        shard_distribution = _distribution(distinct_shards)
        workload = geometry.workload
        workload_results.append(
            PairWorkloadResult(
                workload=workload.name,
                requests=request_distribution,
                transfer_amplification=transfer_distribution,
                distinct_shards=shard_distribution,
            )
        )
        request_utilization = request_distribution.p95 / workload.maximum_p95_requests
        worst_request_utilization = max(worst_request_utilization, request_utilization)
        minimum_distinct_shards = min(minimum_distinct_shards, shard_distribution.p05)
        if request_utilization > 1.0:
            reasons.append(
                f"{workload.name}: p95 storage read requests "
                f"{request_distribution.p95:.3g} > "
                f"{workload.maximum_p95_requests:.3g}"
            )
        if transfer_distribution.p95 > workload.maximum_p95_transfer_amplification:
            reasons.append(
                f"{workload.name}: p95 transfer amplification "
                f"{transfer_distribution.p95:.3g} > "
                f"{workload.maximum_p95_transfer_amplification:.3g}"
            )
        if (
            workload.minimum_p05_distinct_shards is not None
            and shard_distribution.p05 < workload.minimum_p05_distinct_shards
        ):
            reasons.append(
                f"{workload.name}: p05 distinct shards {shard_distribution.p05:.3g} < "
                f"{workload.minimum_p05_distinct_shards:.3g}"
            )

    return LayoutCandidateResult(
        chunk_shape=chunk.shape,
        shard_shape_in_chunks=chunks_per_shard,
        shard_origin_profiles=tuple(sorted(origin.profiles)),
        target_shard_byte_budgets=tuple(sorted(origin.target_budgets)),
        raw_chunk_bytes=chunk.raw_chunk_bytes,
        total_chunks=total_chunks,
        shard_grid_shape=shard_grid,
        total_shards=total_shards,
        estimated_dataset_bytes=estimated_dataset_bytes,
        average_shard_bytes=average_shard_bytes,
        maximum_shard_bytes=maximum_shard_bytes,
        estimated_writer_memory_bytes=writer_memory,
        writer_memory_provenance=policy.writer.memory_provenance,
        workloads=tuple(workload_results),
        chunk_worst_decode_limit_utilization=chunk.worst_decode_limit_utilization,
        worst_request_limit_utilization=worst_request_utilization,
        minimum_p05_distinct_shards=minimum_distinct_shards,
        passes=not reasons,
        rejection_reasons=tuple(reasons),
    )


# Final selection -------------------------------------------------------------


def _selection_key(layout: LayoutCandidateResult) -> tuple[object, ...]:
    return (
        -layout.raw_chunk_bytes,
        layout.chunk_worst_decode_limit_utilization,
        layout.worst_request_limit_utilization,
        layout.average_shard_bytes,
        -layout.minimum_p05_distinct_shards,
        layout.chunk_shape,
        layout.shard_shape_in_chunks,
        layout.shard_origin_profiles,
    )


def run_planner(policy: PlannerPolicy, policy_path: str = "<memory>") -> PlanResult:
    """Enumerate the bounded candidate space, filter it, and select one layout."""

    samples = _generated_workloads(policy)
    chunk_origins = generate_chunk_candidates(policy)
    states = [
        _evaluate_chunk(policy, shape, chunk_origins[shape], samples)
        for shape in sorted(chunk_origins)
    ]
    best_fraction = _apply_compression_constraint(policy, states)

    layouts: list[LayoutCandidateResult] = []
    for state in states:
        if not state.result.passes:
            continue
        shard_origins = generate_shard_candidates(policy, state.result)
        layouts.extend(
            _evaluate_layout(policy, state, shape, shard_origins[shape])
            for shape in sorted(shard_origins)
        )

    passing = [layout for layout in layouts if layout.passes]
    selected = min(passing, key=_selection_key) if passing else None
    chunk_results = tuple(
        sorted(
            (state.result for state in states),
            key=lambda item: (not item.passes, -item.raw_chunk_bytes, item.shape),
        )
    )
    layout_results = tuple(
        sorted(layouts, key=lambda item: (not item.passes, _selection_key(item)))
    )
    return PlanResult(
        policy_path=policy_path,
        policy=policy,
        best_candidate_encoded_fraction=best_fraction,
        chunk_candidates=chunk_results,
        layout_candidates=layout_results,
        selected=selected,
        limitations=LIMITATIONS,
    )


def plan_file(path: Path) -> PlanResult:
    """Convenience entry point used by both front ends."""

    return run_planner(load_policy(path), str(path))


# Rich and Markdown reporting -------------------------------------------------


def format_bytes(value: float | int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    number = float(value)
    for unit in units:
        if abs(number) < 1024.0 or unit == units[-1]:
            return f"{number:.3g} {unit}"
        number /= 1024.0
    raise AssertionError("unreachable")


def shape_text(shape: Sequence[int]) -> str:
    return "x".join(str(value) for value in shape)


def shard_shape(chunk_shape: Shape, chunks_per_shard: Shape) -> Shape:
    """Return the shard shape in array elements."""

    return tuple(
        chunk_extent * shard_extent
        for chunk_extent, shard_extent in zip(chunk_shape, chunks_per_shard)
    )


def _candidate_limit(
    items: Sequence[object], show_all: bool, default: int = 18
) -> Sequence[object]:
    return items if show_all else items[:default]


def render_console(
    result: PlanResult, console: Console, show_all: bool = False
) -> None:
    policy = result.policy
    passing_chunks = sum(candidate.passes for candidate in result.chunk_candidates)
    passing_layouts = sum(candidate.passes for candidate in result.layout_candidates)
    console.print(
        Panel.fit(
            f"[bold]{' x '.join(policy.array.axes)}[/bold]  {shape_text(policy.array.shape)}\n"
            f"{len(result.chunk_candidates)} chunks ({passing_chunks} pass); "
            f"{len(result.layout_candidates)} layouts ({passing_layouts} pass)",
            title="Zarr layout planner",
        )
    )

    if result.selected is None:
        console.print(
            Panel(
                "No candidate layout satisfies every policy limit. "
                "Inspect the rejection reasons below or write the JSON report.",
                title="No feasible layout",
                border_style="red",
            )
        )
    else:
        selected = result.selected
        selected_shard_shape = shard_shape(
            selected.chunk_shape, selected.shard_shape_in_chunks
        )
        console.print(
            Panel(
                f"chunk [bold]{shape_text(selected.chunk_shape)}[/bold] "
                f"({format_bytes(selected.raw_chunk_bytes)} raw chunk bytes)\n"
                f"shard [bold]{shape_text(selected_shard_shape)}[/bold] array elements; "
                f"chunks per shard [bold]{shape_text(selected.shard_shape_in_chunks)}[/bold]\n"
                f"{format_bytes(selected.average_shard_bytes)} average stored shard; "
                f"{selected.total_shards:,} shards\n"
                f"writer working memory {format_bytes(selected.estimated_writer_memory_bytes)} "
                f"[{selected.writer_memory_provenance}]",
                title="Selected layout",
                border_style="green",
            )
        )

    chunk_table = Table(title="Chunk candidates", show_lines=False)
    chunk_table.add_column("pass")
    chunk_table.add_column("chunk shape")
    chunk_table.add_column("raw chunk bytes", justify="right")
    chunk_table.add_column("worst decode limit utilization", justify="right")
    chunk_table.add_column("encoded fraction", justify="right")
    chunk_table.add_column("profiles")
    chunk_table.add_column("reason")
    for candidate in _candidate_limit(result.chunk_candidates, show_all):
        chunk_table.add_row(
            "[green]yes[/green]" if candidate.passes else "[red]no[/red]",
            shape_text(candidate.shape),
            format_bytes(candidate.raw_chunk_bytes),
            f"{candidate.worst_decode_limit_utilization:.2f}",
            f"{candidate.encoded_fraction:.3f}",
            ", ".join(candidate.origin_profiles),
            candidate.rejection_reasons[0] if candidate.rejection_reasons else "",
        )
    console.print(chunk_table)

    if result.layout_candidates:
        layout_table = Table(title="Candidate layouts", show_lines=False)
        layout_table.add_column("pass")
        layout_table.add_column("chunk shape")
        layout_table.add_column("shard shape")
        layout_table.add_column("chunks / shard")
        layout_table.add_column("shards", justify="right")
        layout_table.add_column("average stored shard", justify="right")
        layout_table.add_column("writer working memory", justify="right")
        layout_table.add_column("reason")
        for candidate in _candidate_limit(result.layout_candidates, show_all):
            selected = result.selected == candidate
            layout_table.add_row(
                "[bold green]selected[/bold green]"
                if selected
                else ("[green]yes[/green]" if candidate.passes else "[red]no[/red]"),
                shape_text(candidate.chunk_shape),
                shape_text(
                    shard_shape(
                        candidate.chunk_shape, candidate.shard_shape_in_chunks
                    )
                ),
                shape_text(candidate.shard_shape_in_chunks),
                f"{candidate.total_shards:,}",
                format_bytes(candidate.average_shard_bytes),
                format_bytes(candidate.estimated_writer_memory_bytes),
                candidate.rejection_reasons[0] if candidate.rejection_reasons else "",
            )
        console.print(layout_table)

    if result.selected is not None:
        chunk = next(
            candidate
            for candidate in result.chunk_candidates
            if candidate.shape == result.selected.chunk_shape
        )
        by_workload = {item.workload: item for item in chunk.workloads}
        workload_table = Table(title="Selected layout by required workload")
        workload_table.add_column("workload")
        workload_table.add_column("p95 decode amplification", justify="right")
        workload_table.add_column("p95 storage read requests", justify="right")
        workload_table.add_column("p95 transfer amplification", justify="right")
        workload_table.add_column("p05 distinct shards", justify="right")
        for pair_score in result.selected.workloads:
            decode = by_workload[pair_score.workload].decode_amplification.p95
            workload_table.add_row(
                pair_score.workload,
                f"{decode:.3g}",
                f"{pair_score.requests.p95:.3g}",
                f"{pair_score.transfer_amplification.p95:.3g}",
                f"{pair_score.distinct_shards.p05:.3g}",
            )
        console.print(workload_table)

    if not show_all:
        console.print(
            "[dim]Use --all-candidates or --json to inspect every candidate and rejection.[/dim]"
        )


def render_markdown(result: PlanResult) -> str:
    lines = [
        "# Zarr layout planner report",
        "",
        f"Policy: `{result.policy_path}`",
        "",
    ]
    if result.selected is None:
        lines.extend(
            [
                "## Result",
                "",
                "No candidate layout satisfies every policy limit.",
                "",
            ]
        )
    else:
        selected = result.selected
        selected_shard_shape = shard_shape(
            selected.chunk_shape, selected.shard_shape_in_chunks
        )
        lines.extend(
            [
                "## Recommendation",
                "",
                f"- Chunk shape: `{shape_text(selected.chunk_shape)}` ({format_bytes(selected.raw_chunk_bytes)} raw chunk bytes)",
                f"- Shard shape: `{shape_text(selected_shard_shape)}` array elements",
                f"- Chunks per shard: `{shape_text(selected.shard_shape_in_chunks)}`",
                f"- Estimated average stored shard bytes: {format_bytes(selected.average_shard_bytes)}",
                f"- Total shards: {selected.total_shards:,}",
                f"- Estimated writer working memory: {format_bytes(selected.estimated_writer_memory_bytes)} ({selected.writer_memory_provenance})",
                "",
                "### Required workloads",
                "",
                "| Workload | p95 decode amplification | p95 storage read requests | p95 transfer amplification | p05 distinct shards |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        chunk = next(
            candidate
            for candidate in result.chunk_candidates
            if candidate.shape == selected.chunk_shape
        )
        decode_by_name = {
            item.workload: item.decode_amplification.p95 for item in chunk.workloads
        }
        for workload in selected.workloads:
            lines.append(
                f"| {workload.workload} | {decode_by_name[workload.workload]:.3g} | "
                f"{workload.requests.p95:.3g} | {workload.transfer_amplification.p95:.3g} | "
                f"{workload.distinct_shards.p05:.3g} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Candidate summary",
            "",
            f"- Chunk candidates: {len(result.chunk_candidates)}; {sum(item.passes for item in result.chunk_candidates)} pass",
            f"- Candidate layouts: {len(result.layout_candidates)}; {sum(item.passes for item in result.layout_candidates)} pass",
            f"- Best candidate encoded fraction: {result.best_candidate_encoded_fraction:.4f}",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {limitation}" for limitation in result.limitations)
    lines.append("")

    if result.selected is None:
        reasons = Counter(
            reason
            for chunk in result.chunk_candidates
            for reason in chunk.rejection_reasons
        )
        reasons.update(
            reason
            for layout in result.layout_candidates
            for reason in layout.rejection_reasons
        )
        lines.extend(["## Frequent rejection reasons", ""])
        lines.extend(
            f"- {count} candidates: {reason}"
            for reason, count in reasons.most_common(20)
        )
        lines.append("")
    return "\n".join(lines)


# Command-line interface ------------------------------------------------------


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Find explainable Zarr chunk and shard shapes inside explicit policy limits.",
)
console = Console()


def _load_or_exit(path: Path) -> PlannerPolicy:
    try:
        return load_policy(path)
    except (OSError, tomllib.TOMLDecodeError, ValidationError) as error:
        console.print(Panel(str(error), title="Invalid policy", border_style="red"))
        raise typer.Exit(2) from error


@app.command("plan")
def plan_command(
    policy_path: Annotated[
        Path,
        typer.Argument(
            exists=True, dir_okay=False, readable=True, help="TOML policy file."
        ),
    ],
    json_path: Annotated[
        Path | None,
        typer.Option("--json", help="Write the complete machine-readable result."),
    ] = None,
    markdown_path: Annotated[
        Path | None,
        typer.Option("--markdown", help="Write a compact Markdown report."),
    ] = None,
    all_candidates: Annotated[
        bool,
        typer.Option("--all-candidates", help="Print every candidate to the terminal."),
    ] = False,
) -> None:
    """Evaluate POLICY_PATH and print the recommendation or infeasibility result."""

    policy = _load_or_exit(policy_path)
    try:
        result = run_planner(policy, str(policy_path))
    except PlannerError as error:
        console.print(Panel(str(error), title="Planner stopped", border_style="red"))
        raise typer.Exit(2) from error
    render_console(result, console, all_candidates)
    if json_path is not None:
        json_path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
        console.print(f"Wrote [bold]{json_path}[/bold]")
    if markdown_path is not None:
        markdown_path.write_text(render_markdown(result), encoding="utf-8")
        console.print(f"Wrote [bold]{markdown_path}[/bold]")
    if result.selected is None:
        raise typer.Exit(1)


@app.command("validate")
def validate_command(
    policy_path: Annotated[
        Path,
        typer.Argument(
            exists=True, dir_okay=False, readable=True, help="TOML policy file."
        ),
    ],
) -> None:
    """Validate policy structure and cross-field dimensional constraints."""

    policy = _load_or_exit(policy_path)
    console.print(
        f"[green]Valid[/green]: rank {len(policy.array.shape)}, "
        f"{len(policy.workloads)} workloads, "
        f"{len(policy.chunk_profiles)} chunk profiles, "
        f"{len(policy.shard_profiles)} shard profiles."
    )


@app.command("schema")
def schema_command() -> None:
    """Print the JSON Schema for the TOML policy model."""

    schema = json.dumps(PlannerPolicy.model_json_schema(), indent=2)
    console.print(Syntax(schema, "json", word_wrap=True))


if __name__ == "__main__":
    app()
