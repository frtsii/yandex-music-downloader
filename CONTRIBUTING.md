# Contributing

1. Create a branch from `main`.
2. Keep OAuth tokens, downloaded media, settings, and history out of commits.
3. Run `python -m unittest discover -s tests -v`.
4. Run `flutter analyze` in `app` after interface changes.
5. Describe the user-visible behavior and validation in the pull request.

Please keep provider timeouts short. Failure to find lyrics must never prevent an audio download.
