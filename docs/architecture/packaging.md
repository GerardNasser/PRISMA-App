# Packaging

The release artifacts are matrix-built in CI on every push to `main`.

| Platform | Target | Output |
|---|---|---|
| macOS (arm64) | `macos-14` | `.dmg` |
| macOS (x86_64) | `macos-13` | `.dmg` |
| Windows | `windows-latest` | `.msi` + `.exe` installer |
| Linux | `ubuntu-22.04` | `.AppImage` + `.deb` |

The workflow is `.github/workflows/ci.yml`'s `desktop` job. It runs only on `main` to avoid burning CI minutes on every feature branch.

## Inside a bundle

A release bundle contains:

```
PrismAPI.app/                 (or PrismAPI.exe, or PrismAPI.AppImage)
├── shell binary              ← the Rust executable
└── Resources/
    └── core/                 ← apps/core/, packaged via Tauri externalBin
        ├── src/prismapi/
        ├── pyproject.toml
        └── ...
    └── binaries/python/      ← (release-only) python-build-standalone interpreter
```

`python-build-standalone` (from Astral) ships a redistributable CPython that runs without any system Python install. The exact distribution is selected per platform during the CI build and copied into `apps/desktop/binaries/python/<platform>/`. The Rust shell points `PRISMAPI_PYTHON` at this when launching the sidecar.

In dev (`cargo tauri dev`) we use whatever `python3` is on your PATH. Set `PRISMAPI_PYTHON` to a venv path to test against a specific interpreter.

## Signing and notarisation

**v1 ships unsigned.** Both macOS Gatekeeper and Windows SmartScreen will warn users that the binary isn't signed. To accept on macOS:

1. Right-click the .dmg in Finder and choose Open.
2. Confirm the "developer cannot be verified" dialog.

To accept on Windows:

1. Click "More info" on the SmartScreen warning.
2. Click "Run anyway".

When you're ready for a public release:

- **macOS**: enroll in the [Apple Developer Program](https://developer.apple.com/programs/) ($99/yr), get a Developer ID Application certificate, set Tauri's `signingIdentity` in `tauri.conf.json`, and notarise via `xcrun notarytool`.
- **Windows**: buy an Authenticode certificate ($200-400/yr from SSL.com, DigiCert, GlobalSign). Set Tauri's `certificateThumbprint`. Optionally also EV code-signing to bypass SmartScreen entirely.

## Verifying a release

```bash
# After downloading from the GitHub Releases page:
shasum -a 256 PrismAPI-0.6.0.dmg
```

Match this against the hash in the release notes. Once we're signing, you'll also be able to inspect:

- macOS: `codesign -dvv PrismAPI.app`
- Windows: `signtool verify /pa /v PrismAPI.exe`

## Building locally

```bash
cd apps/desktop
cargo tauri build
```

The output lands in `apps/desktop/target/release/bundle/`. Without a vendored interpreter under `binaries/python/`, the resulting app will look for `python3` on the user's PATH — fine for personal builds in a lab, not for distribution.
