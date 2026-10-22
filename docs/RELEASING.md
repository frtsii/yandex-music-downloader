# Releasing

1. Update `CHANGELOG.md` and the version in `pyproject.toml`.
2. Run `python -m unittest discover -s tests -v`.
3. Run `flutter analyze` in `app`.
4. Run `scripts/build-windows.ps1` and test the generated ZIP on Windows.
5. Commit the release changes and push `main`.
6. Create and push a tag, for example `git tag v3.5.4` followed by `git push origin v3.5.4`.

The GitHub Actions workflow builds the project again and attaches the portable ZIP to a GitHub Release. Never add a token, settings file, history file, or downloaded media to a release.
