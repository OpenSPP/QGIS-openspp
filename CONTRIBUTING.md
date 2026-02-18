# Contributing to OpenSPP QGIS Plugin

Thanks for contributing.

## Development Setup

1. Clone the repository:

```bash
git clone https://github.com/OpenSPP/QGIS-openspp.git
cd QGIS-openspp
```

2. Install the plugin in development mode:

```bash
./install-dev.sh
```

3. Open QGIS and enable **OpenSPP GIS**.

## Running Tests

Run unit tests from the repository root:

```bash
pytest
```

## Build Check

Validate and package the plugin:

```bash
bash build.sh
```

## Pull Request Guidelines

- Keep changes focused and clearly scoped.
- Include tests for new behavior or bug fixes.
- Update `README.md` when user-facing behavior changes.
- Ensure `pytest` and `bash build.sh` pass before opening a PR.
- Use descriptive commit messages.
