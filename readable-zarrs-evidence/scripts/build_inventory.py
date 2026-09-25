import csv
import json
from collections import defaultdict
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    groups = defaultdict(list)
    with (root / "write-runs.csv").open(newline="") as stream:
        for row in csv.DictReader(stream):
            groups[row["study_id"]].append(row)
    metadata = json.loads((root / "write-metadata.json").read_text())["studies"]
    index = []
    for study, rows in groups.items():
        item = {"study_id": study, "observations": len(rows), "created": metadata[study].get("created"),
                "finished": metadata[study].get("finished"), "metadata_file": "write-metadata.json",
                "metadata_record": "#/studies/" + study}
        for key in ("tool", "runner_revision", "compiled_revision", "hostname", "backend", "storage_type",
                    "destination", "input_id", "workload", "study_status", "archive_disposition", "status", "source_file"):
            item[key] = sorted({row[key] for row in rows if row.get(key)})
        index.append(item)
    with (root / "inventory-write-studies.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(index[0]))
        writer.writeheader()
        writer.writerows({key: json.dumps(value, separators=(",", ":")) if isinstance(value, list) else value
                         for key, value in item.items()} for item in index)
    parts = ["# Experiment inventory", "",
             "Snapshot: 2026-09-25. This inventory follows the existing-evidence scope in `planning/cluster-data-prompts.md`. "
             "[README.md](README.md) maps the working claims to findings and exports. All original source records were preserved; no new measurement or allocation was run.", "",
             "Families can overlap across sections: CHAMMI preparation, its subsequent read timings, and the shard-count analysis concern related records. "
             "Reports and copied archives are not additional measurements. Exact row-level locators and unknown fields remain in the companion CSV/JSON files.", ""]
    for name in ("reads", "writes", "concurrency", "conversions"):
        content = (root / "inventory-parts" / (name + ".md")).read_text()
        parts.extend(("\n".join("#" + line if line.startswith("#") else line for line in content.splitlines()), ""))
    parts.extend(("## Recorded write-study provenance", "",
                  "This table expands the write families into their retained study records. Revisions here identify the runner; "
                  "the compiled revision is separately recorded when known. Missing revisions or dates remain unknown. "
                  "Status comes from the archived checkpoint; the canceled 3710801 study still says running there, as explained in its family entry. "
                  "[The machine-readable index](inventory-write-studies.csv) includes full revisions, actual recorded destinations, original source paths, "
                  "input IDs, workloads and status values. Each row points into `write-metadata.json`; observations resolve through `write-runs.csv`.", "",
                  "| Study | Date interval | Runner revision | Machine / backend | Storage | Observations / study status |",
                  "| --- | --- | --- | --- | --- | --- |"))
    for item in index:
        dates = " → ".join(str(item[key])[:10] if item[key] else "unknown" for key in ("created", "finished"))
        revision = ", ".join(value[:12] for value in item["runner_revision"]) or "unknown"
        machine = ", ".join(item["hostname"]) or "unknown"
        backend = ", ".join(item["backend"]) or "unknown"
        storage = ", ".join(item["storage_type"]) or "unknown"
        status = ", ".join(item["study_status"]) or "unknown"
        parts.append(f"| {item['study_id']} | {dates} | {revision} | {machine} / {backend} | {storage} | {item['observations']} / {status} |")
    (root / "inventory.md").write_text("\n".join(parts) + "\n")
    print(f"Combined four inventories and indexed {len(index)} write studies.")


if __name__ == "__main__":
    main()
