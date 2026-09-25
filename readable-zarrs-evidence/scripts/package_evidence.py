import gzip
import hashlib
import json
import tarfile
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    hashes = {str(path.relative_to(root)): digest(path) for path in files}
    manifest = root / "SHA256SUMS"
    manifest.write_text("".join(f"{value}  {name}\n" for name, value in hashes.items()))
    files.append(manifest)
    hashes[manifest.name] = digest(manifest)
    archive = root.parent / (root.name + ".tar.gz")
    with archive.open("wb") as stream, gzip.GzipFile(filename="", mode="wb", fileobj=stream, compresslevel=3, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as bundle:
            for path in sorted(files):
                info = bundle.gettarinfo(str(path), arcname=root.name + "/" + str(path.relative_to(root)))
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                with path.open("rb") as source:
                    bundle.addfile(info, source)
    checked = set()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            name = str(Path(member.name).relative_to(root.name))
            if not member.isfile() or name not in hashes:
                raise ValueError(f"Unexpected archive entry: {member.name}")
            with bundle.extractfile(member) as stream:
                if hashlib.sha256(stream.read()).hexdigest() != hashes[name]:
                    raise ValueError(f"Archive content mismatch: {name}")
            checked.add(name)
    if checked != set(hashes):
        raise ValueError("Archive entries do not match the evidence files")
    archive_hash = digest(archive)
    Path(str(archive) + ".sha256").write_text(f"{archive_hash}  {archive.name}\n")
    print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size,
                      "files_verified": len(checked), "sha256": archive_hash}))


if __name__ == "__main__":
    main()
