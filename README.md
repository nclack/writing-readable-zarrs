# Writing readable Zarrs

[Read the article](https://nclack.github.io/writing-readable-zarrs/).

An article about choosing Zarr chunk and shard layouts for microscopy reads,
streaming writes, and conversion.

- [Markdown source](article/draft.md)
- [Figures and reproduction](article/figures/README.md)
- [Read and write evidence](readable-zarrs-evidence/README.md)
- [BBBC022 evidence](bbbc022-evidence/README.md)

## Preview locally

With Python 3.12, from the repository root:

```sh
python3 -m venv article/.venv
article/.venv/bin/python -m pip install -r article/requirements-site.txt
article/.venv/bin/python article/build_review.py --output-dir _site
article/.venv/bin/python -m http.server 8000 --directory _site
```

Open <http://localhost:8000>. The site uses the committed figures; supporting
sources and data link to GitHub. See the figure guide above to regenerate figures.

## Publishing

The [Pages workflow](.github/workflows/pages.yml) rebuilds and publishes the
article on every push to `main`. Pull requests build without deploying; the
workflow can also be run manually.

The repository's **Settings → Pages → Build and deployment → Source** must be
set to **GitHub Actions**. See [GitHub's custom workflow guide](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
