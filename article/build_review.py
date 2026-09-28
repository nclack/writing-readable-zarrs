"""Render the Markdown draft to a local HTML reading copy."""
from pathlib import Path
import markdown

HERE = Path(__file__).resolve().parent
body = markdown.markdown(
    (HERE / "draft.md").read_text(),
    extensions=["tables", "fenced_code", "toc"],
)
page = """<!doctype html>
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
<nav>Working draft · <a href="draft.md">Markdown source</a> ·
<a href="figures/README.md">Figure sources and reproduction</a></nav>
<main>""" + body + "</main></html>\n"
(HERE / "index.html").write_text(page)
print("Wrote article/index.html")
