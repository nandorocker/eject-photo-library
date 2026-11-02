# Eject photo library

<img src="assets/icon.png" width="72" height="72" alt="Eject photo library icon">

An Alfred workflow for ejecting a photo-library disk image after Photos has closed but its background services are still keeping the image busy.

Type **`ejp`** in Alfred and press **Return**. If several library images match, choose one. The workflow uses generic titles and notifications; volume names appear only when needed to distinguish multiple matches.

Created by **[nando rossi](https://nan.do)**. If it saves you some frustration, **[buy me a coffee](https://buymeacoffee.com/nandorossi)**.

## Install

1. [Download the latest Alfred workflow](https://github.com/nandorocker/eject-photo-library/releases/latest/download/Eject.Photo.Library.alfredworkflow).
2. Double-click it to import into Alfred.
3. Open Alfred, type `ejp`, and press Return.

Requires **macOS and Alfred with Powerpack**. The workflow uses only built-in macOS tools. No Python installation is needed to run it.

Prefer a standalone helper? [Download the `.command` file](https://github.com/nandorocker/eject-photo-library/releases/latest/download/Eject.Photo.Library.command). Make it executable if necessary, then double-click it in Finder. It automatically acts only when exactly one image matches; use Alfred to choose among several images.

## What it does

The workflow finds attached disk images with `.photoslibrary` files open in Photos, its library and media-analysis services, or Spotlight. It looks at open-file metadata; it does not open your photographs or scan your photo folders. No image name or location is hard-coded.

For the selected image, it:

1. Resolves the image’s current device from `hdiutil`’s property-list output.
2. Tries a normal `diskutil eject`.
3. If needed, identifies processes holding files open on the image.
4. Sends a graceful `SIGTERM` only to the current user’s recognized Apple photo-library, photo-analysis, media-analysis, and Spotlight helpers.
5. Retries normal eject up to three times and verifies that the image detached.

If Photos, Finder, an editor, a terminal, or another unrecognized process is still using the image, the workflow asks you to finish your work and quit that app. It does not force eject, force kill, use `sudo`, permanently disable services, or change indexing settings.

An Apple helper may serve several libraries, so restarting it can briefly interrupt other background analysis. macOS may restart these helpers afterward.

## Scope and privacy

- Handles **disk images and sparsebundles**. It does not automatically eject physical external drives or the startup disk.
- Ejects **one selected image**. If several libraries share that image, all of them disconnect together.
- A mounted image with no open photo-library files may not appear. Try Finder’s normal eject in that case.
- Normal Alfred results and notifications are generic. Multiple matches show volume names for selection; photo-library paths are not displayed.
- Nothing is sent over the network. The latest action log is stored with private permissions in Alfred’s workflow cache as `last-run.log`. Logs can contain local diagnostic paths, so review them before sharing.

Tested locally with Alfred 5 on macOS 27.2. Other macOS releases may use different background-service paths. Unknown executables are left alone.

## Command-line use

Run the helper from a checkout:

```sh
./src/eject-photo-library.zsh --diagnose --no-pause
./src/eject-photo-library.zsh --no-pause
```

`--diagnose` inspects a single detected image without ejecting or stopping anything. Normal mode ejects only when exactly one image matches.

To target a specific attached **image file** explicitly:

```sh
./src/eject-photo-library.zsh --image "/path/to/Library.sparsebundle" --no-pause
```

`--list` produces [Alfred Script Filter JSON](https://www.alfredapp.com/help/workflows/inputs/script-filter/json/). Without `--no-pause`, an interactive run waits for Return before closing its window.

## Build and test

Development requires macOS and Python 3; packaging and tests use the Python standard library.

```sh
python3 tests/test_eject.py
python3 scripts/build.py
python3 tests/test_package.py
```

The build produces a self-contained `.alfredworkflow`, a standalone `.command` helper, and `SHA256SUMS` in `dist/`. Build output is deterministic. No local Alfred preferences or files outside the repository are needed.

The safety tests substitute simulated disk, process, and signal commands. They cover target selection, multiple images, unknown apps, another user’s services, executable verification, retry limits, ambiguous devices, private labels, and unusual path characters. They do not eject real disks or stop real processes.

An optional GitHub Actions template is in [`docs/check.yml`](docs/check.yml). To enable automated checks on GitHub, copy it to `.github/workflows/check.yml` using an account or credential allowed to publish workflow definitions.

The normal eject and helper-release procedure has also been tested against an actual mounted image. The generalized version’s latest local live check covered the no-mounted-library state.

## Author and support

**nando rossi** · **[nan.do](https://nan.do)** · **[Buy me a coffee](https://buymeacoffee.com/nandorossi)**

Released under the [MIT license](LICENSE).
