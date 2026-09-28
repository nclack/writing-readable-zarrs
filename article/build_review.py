"""Render the Markdown draft for local reading or GitHub Pages."""
import argparse
from pathlib import Path
import shutil
from urllib.parse import unquote, urljoin, urlsplit

import markdown
from markdown.treeprocessors import Treeprocessor

HERE = Path(__file__).resolve().parent
SOURCE_URL = "https://github.com/nclack/writing-readable-zarrs/blob/main/article/"


class SiteLinks(Treeprocessor):
    """Keep figures local and send supporting-file links to GitHub."""

    def __init__(self, md, output_dir):
        super().__init__(md)
        self.output_dir = output_dir

    def run(self, root):
        for element in root.iter():
            attribute = {"a": "href", "img": "src"}.get(element.tag)
            if attribute is None:
                continue
            link = element.get(attribute, "")
            url = urlsplit(link)
            if url.scheme or url.netloc or not url.path:
                continue
            source = (HERE / unquote(url.path)).resolve()
            source.relative_to(HERE.parent)
            if not source.is_file():
                raise FileNotFoundError(f"Missing article asset: {link}")
            if element.tag == "a":
                element.set(attribute, urljoin(SOURCE_URL, link))
            else:
                destination = self.output_dir / source.relative_to(HERE)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        return root


PAGE_HEADER = """<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Writing readable Zarrs — draft</title>
<style>
:root { color-scheme: light; }
body { max-width: 880px; margin: 40px auto 100px; padding: 0 24px;
       font: 18px/1.6 Georgia, serif; color: #20242a; background: white; }
h1,h2,h3,nav,table { font-family: Arial, sans-serif; }
h1 { font-size: 38px; line-height: 1.15; margin-bottom: 30px; }
h2 { font-size: 25px; line-height: 1.25; margin-top: 48px; }
h3 { font-size: 20px; margin-top: 32px; }
a { color: #005f8f; text-underline-offset: 3px; }
nav { font-size: 13px; border-bottom: 1px solid #ddd; padding-bottom: 14px; }
img { display: block; width: 100%; height: auto; margin: 28px 0 12px; }
table { border-collapse: collapse; font-size: 14px; line-height: 1.45; width: 100%; }
th,td { text-align: left; padding: 10px 8px; vertical-align: top; }
th { border-top: 1px solid; border-bottom: 1px solid; }
tr:last-child td { border-bottom: 1px solid; }
code { font-size: .85em; overflow-wrap: anywhere; }
pre { overflow: auto; padding: 14px; background: #f5f6f7; }
blockquote { border-left: 3px solid #ddd; margin-left: 0; padding-left: 20px; }
@media print { body { font-size: 11pt; max-width: none; margin: 0; }
 nav { display: none; } img,table { break-inside: avoid; } }
</style>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path,
        help="Build a standalone site here; default: local article/index.html",
    )
    args = parser.parse_args()
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc"])
    if args.output_dir:
        md.treeprocessors.register(SiteLinks(md, args.output_dir), "site_links", 0)
    body = md.convert((HERE / "draft.md").read_text(encoding="utf-8"))
    source_url = SOURCE_URL if args.output_dir else ""
    page = PAGE_HEADER + (
        f'<nav>Working draft · <a href="{source_url}draft.md">Markdown source</a> ·\n'
        f'<a href="{source_url}figures/README.md">Figure sources and reproduction</a></nav>\n'
        f"<main>{body}</main></html>\n"
    )
    output_dir = args.output_dir if args.output_dir else HERE
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "index.html"
    output.write_text(page, encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
