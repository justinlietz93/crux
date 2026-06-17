# Publishing crux-providers to PyPI

Uses PyPI Trusted Publishing (OIDC). No API tokens or secrets in the repo.

## One-time prep (do before first publish)

1. Verify the name `crux-providers` is free at https://pypi.org/project/crux-providers/
   (a 404 means available). An unrelated `crux` distribution exists, so pick a
   distinct name if you want to avoid confusion.
2. Add a `LICENSE` file (pyproject declares MIT but no file is committed).
3. (DONE) Provider core is now import-clean without FastAPI. The eager route
   import was moved out of `service/__init__.py` into `service/app.py` (app
   assembly), and `base/capabilities/observed.py` imports `service.db` lazily.
   Verified: the provider core imports with FastAPI uninstalled; the app still
   registers `/api/chat/stream` when served.

## Validate locally

```bash
pip install build twine
python -m build            # builds sdist + wheel into dist/
twine check dist/*         # metadata sanity
```

## Dry run on TestPyPI (recommended first)

```bash
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ crux-providers
```

## Set up the trusted publisher (one-time, on PyPI)

Go to https://pypi.org/manage/account/publishing/ and "Add a new pending publisher":

- PyPI Project Name: `crux-providers`
- Owner: `justinlietz93`
- Repository name: `crux`            (the GitHub repo)
- Workflow name: `publish.yml`
- Environment name: `pypi`

This works before the project exists ("pending publisher"); the first successful
run activates it.

## Create the GitHub environment

In the GitHub repo: Settings -> Environments -> New environment named `pypi`.

## Publish

1. Bump `version` in `pyproject.toml`.
2. Commit and push.
3. Create a GitHub Release (Releases -> Draft new release), tag e.g. `v0.1.0`.
4. Publishing the release triggers `.github/workflows/publish.yml`, which builds
   and uploads to PyPI via OIDC. Versions are immutable; bump for every release.
