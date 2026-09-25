#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "nicegui>=3.16,<4",
#   "plotly>=7,<8",
#   "pydantic>=2.13,<3",
#   "rich>=15,<16",
#   "typer>=0.27,<1",
# ]
# ///

"""Local interactive explorer for layout_planner.py results."""

from __future__ import annotations

import argparse
import html
import tomllib
from pathlib import Path
from typing import Sequence

import plotly.graph_objects as go
from nicegui import ui
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel

import layout_planner as planner


PASS_COLOR = "#2A9D8F"
FAIL_COLOR = "#E76F51"
SELECTED_COLOR = "#264653"
REFERENCE_COLOR = "#E9C46A"
MUTED_COLOR = "#8D99AE"


def _shape(shape: Sequence[int]) -> str:
    return " x ".join(str(value) for value in shape)


def _chunk_score(
    candidate: planner.ChunkCandidateResult, workload_name: str
) -> planner.ChunkWorkloadResult:
    return next(item for item in candidate.workloads if item.workload == workload_name)


def _chunk_figure(
    result: planner.PlanResult,
    workload_name: str,
    status_filter: str,
    selected_chunk: planner.Shape | None,
) -> go.Figure:
    workload = next(
        item for item in result.policy.workloads if item.name == workload_name
    )
    figure = go.Figure()
    for passes, label, color in (
        (True, "passes all chunk limits", PASS_COLOR),
        (False, "rejected", FAIL_COLOR),
    ):
        if status_filter == "passing" and not passes:
            continue
        if status_filter == "rejected" and passes:
            continue
        candidates = [item for item in result.chunk_candidates if item.passes == passes]
        figure.add_trace(
            go.Scatter(
                x=[item.raw_chunk_bytes for item in candidates],
                y=[
                    _chunk_score(item, workload_name).decode_amplification.p95
                    / workload.maximum_p95_decode_amplification
                    for item in candidates
                ],
                mode="markers",
                name=label,
                marker={"color": color, "size": 10, "opacity": 0.78},
                customdata=[
                    [
                        _shape(item.shape),
                        ", ".join(item.origin_profiles),
                        item.encoded_fraction,
                        item.rejection_reasons[0]
                        if item.rejection_reasons
                        else "passes",
                    ]
                    for item in candidates
                ],
                hovertemplate=(
                    "chunk shape %{customdata[0]}<br>"
                    "raw chunk bytes %{x:.3s} B<br>"
                    "p95 decode limit utilization %{y:.3f}<br>"
                    "encoded fraction %{customdata[2]:.3f}<br>"
                    "profiles %{customdata[1]}<br>"
                    "%{customdata[3]}<extra></extra>"
                ),
            )
        )
    if selected_chunk is not None:
        candidate = next(
            item for item in result.chunk_candidates if item.shape == selected_chunk
        )
        score = _chunk_score(candidate, workload_name)
        figure.add_trace(
            go.Scatter(
                x=[candidate.raw_chunk_bytes],
                y=[
                    score.decode_amplification.p95
                    / workload.maximum_p95_decode_amplification
                ],
                mode="markers",
                name="selected layout",
                marker={
                    "color": SELECTED_COLOR,
                    "size": 17,
                    "symbol": "star",
                    "line": {"color": "white", "width": 1},
                },
                hovertemplate=f"selected chunk {_shape(candidate.shape)}<extra></extra>",
            )
        )
    figure.add_hline(
        y=1.0,
        line_dash="dash",
        line_color=REFERENCE_COLOR,
        annotation_text="policy limit",
    )
    figure.update_layout(
        title=f"Chunk tradeoff for {workload_name}",
        xaxis={"title": "raw chunk bytes", "type": "log"},
        yaxis={"title": "p95 decode amplification / limit", "rangemode": "tozero"},
        legend={"orientation": "h", "y": 1.13},
        margin={"l": 55, "r": 20, "t": 85, "b": 55},
        hovermode="closest",
    )
    return figure


def _layout_figure(
    result: planner.PlanResult,
    status_filter: str,
    selected_index: int | None,
) -> go.Figure:
    figure = go.Figure()
    for passes, label, color in (
        (True, "passes every limit", PASS_COLOR),
        (False, "rejected", FAIL_COLOR),
    ):
        if status_filter == "passing" and not passes:
            continue
        if status_filter == "rejected" and passes:
            continue
        indexed = [
            (index, item)
            for index, item in enumerate(result.layout_candidates)
            if item.passes == passes
        ]
        figure.add_trace(
            go.Scatter(
                x=[item.average_shard_bytes for _, item in indexed],
                y=[item.total_shards for _, item in indexed],
                mode="markers",
                name=label,
                marker={"color": color, "size": 10, "opacity": 0.72},
                customdata=[
                    [
                        index,
                        _shape(item.chunk_shape),
                        _shape(
                            planner.shard_shape(
                                item.chunk_shape, item.shard_shape_in_chunks
                            )
                        ),
                        _shape(item.shard_shape_in_chunks),
                        planner.format_bytes(item.estimated_writer_memory_bytes),
                        item.rejection_reasons[0]
                        if item.rejection_reasons
                        else "passes",
                    ]
                    for index, item in indexed
                ],
                hovertemplate=(
                    "chunk shape %{customdata[1]}<br>"
                    "shard shape %{customdata[2]} array elements<br>"
                    "chunks per shard %{customdata[3]}<br>"
                    "average stored shard %{x:.3s} B<br>"
                    "%{y:,.0f} shards<br>"
                    "writer working memory %{customdata[4]}<br>"
                    "%{customdata[5]}<extra></extra>"
                ),
            )
        )
    if selected_index is not None:
        item = result.layout_candidates[selected_index]
        figure.add_trace(
            go.Scatter(
                x=[item.average_shard_bytes],
                y=[item.total_shards],
                mode="markers",
                name="selected layout",
                marker={
                    "color": SELECTED_COLOR,
                    "size": 17,
                    "symbol": "star",
                    "line": {"color": "white", "width": 1},
                },
                hovertemplate=(
                    f"selected chunk shape {_shape(item.chunk_shape)}<br>"
                    f"shard shape {_shape(planner.shard_shape(item.chunk_shape, item.shard_shape_in_chunks))} array elements<br>"
                    f"chunks per shard {_shape(item.shard_shape_in_chunks)}<extra></extra>"
                ),
            )
        )
    storage = result.policy.storage
    figure.add_hline(
        y=storage.maximum_shards,
        line_dash="dash",
        line_color=REFERENCE_COLOR,
        annotation_text="maximum shard count",
    )
    figure.add_vline(
        x=storage.minimum_efficient_object_bytes,
        line_dash="dot",
        line_color=MUTED_COLOR,
        annotation_text="minimum efficient stored-value bytes",
    )
    figure.add_vline(
        x=storage.maximum_shard_bytes,
        line_dash="dash",
        line_color=REFERENCE_COLOR,
        annotation_text="maximum stored shard bytes",
    )
    figure.update_layout(
        title="Stored shard bytes versus shard count",
        xaxis={"title": "estimated average stored shard bytes", "type": "log"},
        yaxis={"title": "shards", "type": "log"},
        legend={"orientation": "h", "y": 1.13},
        margin={"l": 65, "r": 20, "t": 85, "b": 55},
        hovermode="closest",
    )
    return figure


def _axis_figure(
    result: planner.PlanResult, layout: planner.LayoutCandidateResult | None
) -> go.Figure:
    figure = go.Figure()
    if layout is None:
        figure.update_layout(title="No candidate layouts were generated")
        return figure
    array_shape = result.policy.array.shape
    chunk_fraction = [
        chunk / available for chunk, available in zip(layout.chunk_shape, array_shape)
    ]
    shard_fraction = [
        min(available, chunk * shard) / available
        for chunk, shard, available in zip(
            layout.chunk_shape, layout.shard_shape_in_chunks, array_shape
        )
    ]
    figure.add_trace(
        go.Bar(
            name="chunk extent / array extent",
            x=result.policy.array.axes,
            y=chunk_fraction,
            marker_color=PASS_COLOR,
            customdata=list(layout.chunk_shape),
            hovertemplate="%{x}: %{customdata} elements (%{y:.2%} of array)<extra></extra>",
        )
    )
    figure.add_trace(
        go.Bar(
            name="maximum in-bounds shard extent / array",
            x=result.policy.array.axes,
            y=shard_fraction,
            marker_color=SELECTED_COLOR,
            customdata=[
                min(available, chunk * shard)
                for chunk, shard, available in zip(
                    layout.chunk_shape, layout.shard_shape_in_chunks, array_shape
                )
            ],
            hovertemplate="%{x}: %{customdata} elements (%{y:.2%} of array)<extra></extra>",
        )
    )
    figure.update_layout(
        title="Chunk and maximum in-bounds shard extents by axis",
        barmode="group",
        yaxis={"title": "fraction of array extent", "tickformat": ".0%"},
        legend={"orientation": "h", "y": 1.13},
        margin={"l": 55, "r": 20, "t": 85, "b": 45},
    )
    return figure


def _workload_rows(
    result: planner.PlanResult, layout: planner.LayoutCandidateResult | None
) -> list[dict[str, str]]:
    if layout is None:
        return []
    chunk = next(
        item for item in result.chunk_candidates if item.shape == layout.chunk_shape
    )
    chunk_by_name = {item.workload: item for item in chunk.workloads}
    policy_by_name = {item.name: item for item in result.policy.workloads}
    rows = []
    for pair_score in layout.workloads:
        name = pair_score.workload
        chunk_score = chunk_by_name[name]
        policy = policy_by_name[name]
        minimum_shards = (
            "-"
            if policy.minimum_p05_distinct_shards is None
            else f"{policy.minimum_p05_distinct_shards:g}"
        )
        rows.append(
            {
                "workload": name,
                "decode": f"{chunk_score.decode_amplification.p95:.3g} / {policy.maximum_p95_decode_amplification:.3g}",
                "requests": f"{pair_score.requests.p95:.3g} / {policy.maximum_p95_requests:.3g}",
                "transfer": f"{pair_score.transfer_amplification.p95:.3g} / {policy.maximum_p95_transfer_amplification:.3g}",
                "shards": f"{pair_score.distinct_shards.p05:.3g} / {minimum_shards}",
            }
        )
    return rows


class Explorer:
    def __init__(self, result: planner.PlanResult):
        self.result = result
        self.selected_index = self._recommended_index()

    def _recommended_index(self) -> int | None:
        if self.result.selected is None:
            return 0 if self.result.layout_candidates else None
        return next(
            index
            for index, item in enumerate(self.result.layout_candidates)
            if item == self.result.selected
        )

    def _layout_options(self) -> dict[str, str]:
        options: dict[str, str] = {}
        for index, item in enumerate(self.result.layout_candidates):
            status = "PASS" if item.passes else "FAIL"
            options[str(index)] = (
                f"{status} · chunk shape {_shape(item.chunk_shape)} · "
                f"shard shape {_shape(planner.shard_shape(item.chunk_shape, item.shard_shape_in_chunks))} · "
                f"chunks per shard {_shape(item.shard_shape_in_chunks)} · "
                f"{item.total_shards:,} shards"
            )
        return options

    def build(self) -> None:
        result = self.result
        ui.colors(
            primary=SELECTED_COLOR,
            secondary=PASS_COLOR,
            accent=REFERENCE_COLOR,
            positive=PASS_COLOR,
            negative=FAIL_COLOR,
        )
        with ui.header().classes("items-center justify-between"):
            with ui.column().classes("gap-0"):
                ui.label("Zarr layout explorer").classes("text-h5 font-bold")
                ui.label(result.policy_path).classes("text-caption opacity-75")
            if result.selected is not None:
                ui.badge("passing layout available", color="positive")
            else:
                ui.badge("no passing layout", color="negative")

        with ui.column().classes("w-full max-w-screen-2xl mx-auto p-4 gap-4"):
            ui.markdown(
                "This view uses linked two-dimensional projections instead of "
                "trying to draw a five-dimensional array. Choose a required "
                "workload and a candidate layout; the plots and limits update together."
            ).classes("max-w-4xl")

            with ui.row().classes("w-full items-end gap-4"):
                self.workload_select = ui.select(
                    options=[item.name for item in result.policy.workloads],
                    value=result.policy.workloads[0].name,
                    label="Chunk plot workload",
                    on_change=self.refresh,
                ).classes("w-64")
                self.status_select = ui.select(
                    options={
                        "all": "All candidates",
                        "passing": "Passing only",
                        "rejected": "Rejected only",
                    },
                    value="all",
                    label="Plot filter",
                    on_change=self.refresh,
                ).classes("w-48")
                if result.selected is not None:
                    ui.button(
                        "Use recommendation", on_click=self.use_recommendation
                    ).props("outline")

            options = self._layout_options()
            if options:
                self.layout_select = ui.select(
                    options=options,
                    value=str(self.selected_index),
                    label="Selected candidate layout",
                    on_change=self.choose_layout,
                ).classes("w-full")
            else:
                self.layout_select = ui.select(
                    options={"": "No candidate layouts: every chunk was rejected"},
                    value="",
                    label="Selected candidate layout",
                ).classes("w-full")
                self.layout_select.disable()

            with ui.row().classes("w-full gap-4 items-stretch"):
                with ui.card().classes("grow basis-[34rem]"):
                    self.chunk_plot = ui.plotly(go.Figure()).classes("w-full h-[28rem]")
                with ui.card().classes("grow basis-[34rem]"):
                    self.layout_plot = ui.plotly(go.Figure()).classes(
                        "w-full h-[28rem]"
                    )

            with ui.row().classes("w-full gap-4 items-stretch"):
                with ui.card().classes("grow basis-[32rem]"):
                    self.axis_plot = ui.plotly(go.Figure()).classes("w-full h-[25rem]")
                with ui.card().classes("grow basis-[32rem]"):
                    ui.label("Selected layout").classes("text-h6")
                    self.summary = ui.markdown("")
                    self.reasons = ui.markdown("")

            with ui.card().classes("w-full"):
                ui.label("Required-workload checks: observed / policy limit").classes(
                    "text-h6"
                )
                self.workload_table = ui.table(
                    columns=[
                        {
                            "name": "workload",
                            "label": "Workload",
                            "field": "workload",
                            "align": "left",
                        },
                        {
                            "name": "decode",
                            "label": "p95 decode amplification",
                            "field": "decode",
                            "align": "right",
                        },
                        {
                            "name": "requests",
                            "label": "p95 storage read requests",
                            "field": "requests",
                            "align": "right",
                        },
                        {
                            "name": "transfer",
                            "label": "p95 transfer amplification",
                            "field": "transfer",
                            "align": "right",
                        },
                        {
                            "name": "shards",
                            "label": "p05 distinct shards / target",
                            "field": "shards",
                            "align": "right",
                        },
                    ],
                    rows=[],
                    row_key="workload",
                ).classes("w-full")

            with ui.expansion("Model boundaries", icon="info").classes("w-full"):
                for limitation in result.limitations:
                    ui.label(f"• {limitation}")

        self.refresh()

    def _current_layout(self) -> planner.LayoutCandidateResult | None:
        if self.selected_index is None:
            return None
        return self.result.layout_candidates[self.selected_index]

    def choose_layout(self, event) -> None:
        if event.value == "":
            self.selected_index = None
        else:
            self.selected_index = int(event.value)
        self.refresh()

    def use_recommendation(self) -> None:
        self.selected_index = self._recommended_index()
        if self.selected_index is not None:
            self.layout_select.set_value(str(self.selected_index))
        self.refresh()

    def refresh(self, _event=None) -> None:
        layout = self._current_layout()
        selected_chunk = None if layout is None else layout.chunk_shape
        self.chunk_plot.figure = _chunk_figure(
            self.result,
            self.workload_select.value,
            self.status_select.value,
            selected_chunk,
        )
        self.chunk_plot.update()
        self.layout_plot.figure = _layout_figure(
            self.result,
            self.status_select.value,
            self.selected_index,
        )
        self.layout_plot.update()
        self.axis_plot.figure = _axis_figure(self.result, layout)
        self.axis_plot.update()
        self.workload_table.rows = _workload_rows(self.result, layout)
        self.workload_table.update()

        if layout is None:
            self.summary.set_content("No candidate layout is available. Inspect the chunk plot.")
            self.reasons.set_content("")
            return
        recommendation = layout == self.result.selected
        badge = "**Planner recommendation.**  " if recommendation else ""
        self.summary.set_content(
            badge
            + f"Chunk shape `{_shape(layout.chunk_shape)}` "
            + f"({planner.format_bytes(layout.raw_chunk_bytes)} raw chunk bytes); "
            + f"shard shape `{_shape(planner.shard_shape(layout.chunk_shape, layout.shard_shape_in_chunks))}` array elements; "
            + f"chunks per shard `{_shape(layout.shard_shape_in_chunks)}`.  \n\n"
            + f"Estimated average stored shard bytes: **{planner.format_bytes(layout.average_shard_bytes)}**; "
            + f"maximum stored shard bytes: **{planner.format_bytes(layout.maximum_shard_bytes)}**; "
            + f"total shards: **{layout.total_shards:,}**.  \n\n"
            + f"Estimated {html.escape(self.result.policy.writer.name)} writer working memory: "
            + f"**{planner.format_bytes(layout.estimated_writer_memory_bytes)}** "
            + f"({layout.writer_memory_provenance})."
        )
        if layout.passes:
            self.reasons.set_content("This layout satisfies every configured limit.")
        else:
            self.reasons.set_content(
                "**Why this layout is rejected**\n\n"
                + "\n".join(f"- {reason}" for reason in layout.rejection_reasons)
            )


def _arguments() -> argparse.Namespace:
    default_policy = Path(__file__).with_name("example-policy.toml")
    parser = argparse.ArgumentParser(
        description="Explore chunk and shard tradeoffs in a local browser."
    )
    parser.add_argument(
        "policy",
        nargs="?",
        type=Path,
        default=default_policy,
        help=f"TOML policy file (default: {default_policy.name})",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8080, type=int)
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the server without opening a browser",
    )
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    console = Console()
    try:
        result = planner.plan_file(arguments.policy)
    except (
        OSError,
        tomllib.TOMLDecodeError,
        ValidationError,
        planner.PlannerError,
    ) as error:
        console.print(
            Panel(str(error), title="Could not build explorer", border_style="red")
        )
        raise SystemExit(2) from error

    @ui.page("/")
    def index() -> None:
        Explorer(result).build()

    try:
        ui.run(
            host=arguments.host,
            port=arguments.port,
            show=not arguments.no_browser,
            reload=False,
            title="Zarr layout explorer",
        )
    except KeyboardInterrupt:
        pass


if __name__ in {"__main__", "__mp_main__"}:
    main()
