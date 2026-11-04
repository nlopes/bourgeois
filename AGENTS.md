# Repository Guidelines

## Project structure and module organization

bourgeois themes GRUB with an interface inspired by point-and-click adventure games.
Development targets Ubuntu 24.04 x86_64 UEFI in a disposable QEMU guest.

- `README.adoc` describes the project’s motivation and direction.
- `AGENTS.md` contains contributor guidance.
- `docs/research/` contains feasibility research and design proposals.
- `docs/research/mockups/` contains concept boards, generation prompts, and runtime captures.
- `tools/` contains Python build and VM tooling, with tests beside the code.
- `assets/` contains shared PNG artwork and generation prompts.
- `fancy/` contains the GPLv3+ native GRUB module, host C tests and GRUB service doubles, isolated trial patches, and its license.
- `.github/workflows/` contains the GitHub Actions checks for Python, C compilers, static analysis, and sanitizers.
- `build/` contains ignored guest disks, keys, caches, and evidence.

Add implementation directories when needed, and document their purpose here.
Keep the README focused on the project and its setup.

## Implementation constraints

- Preserve GRUB's native boot commands, entry IDs, authentication, and recovery paths. Generate boot entries from the distribution configuration.
- Slim keeps the distribution EFI binary unchanged. Use the compact two-entry menu with Up/Down and Enter. The lab's lowercase `l`/`w` shortcuts boot immediately; the host artwork follows the existing menu's controls and shows a static hero at the selected door.
- Fancy uses a native module in a separate EFI image. Left/Right walks; Space enters only at a gate; L/W boots immediately.
- Both editions use rear-facing gate poses that look up at the nameplates. Fancy adds twinkling stars and a short inward turn/step on Space, and keeps the hero in GRUB's boot handoff background.
- Doorway feedback uses a soft amber light behind the selected hero. Slim keeps it static; Fancy fades it in on arrival, brightens it on Space, and retains it with the boot handoff hero.
- Keep Linux and Windows as the two OS choices. Default to Linux after 30 seconds, cancel the timer on input, and keep Esc as the route to the technical menu.
- Keep the shared stone nameplates in the background artwork and preserve each edition's title, controls, and visual layout. See `assets/README.adoc` for asset sources.
- Keep host snapshots, firmware identifiers, trust hashes, hardware inventories, and private logs in ignored `build/` storage. Use synthetic identifiers in committed fixtures and publish only captures without host details or personal metadata.
- Install general development previews only in the disposable lab guest. Use the backed-up host installer for the existing Slim host theme. The explicitly requested Fancy host trial uses the separate, hash-enrolled EFI and one-time BootNext workflow in `docs/research/host-fancy.adoc`; preserve Ubuntu/Slim as the default. Windows lab tests use a routing fixture; see `docs/research/validation.adoc` for validation limits.

## Build, test, and development commands

Use Python 3.11 or newer, a C compiler, Make, QEMU, xorriso, and OpenSSH.
See the README for setup and verified commands.

- `make vm` starts the disposable Ubuntu guest.
- `make screenshot` captures its display under `build/evidence/`.
- `make test` runs the Python tests and C controller, layout, pixel blending, and command tests.
- `make test-c` runs only the host C tests with compiler warnings treated as errors.
- `make analyze-c` runs Clang static analysis on the host C tests and included module.
- `make sanitize-c CC=clang` runs the C tests with AddressSanitizer and UndefinedBehaviorSanitizer.
- `make lab-preflight` checks the local VM tools and reports missing packages.
- `make slim` installs the stock-binary theme in the guest.
- `make host-doctor` checks host dependencies and reports graphics adapters without changes.
- `make host-gpus` reports adapters and recommends a firmware display adapter.
- `make host-gpu-select` interactively selects an adapter for setup guidance.
- `make host-stage` builds Slim artwork for the host's existing clean menu.
- `make host-install` backs up and updates the existing host theme with sudo.
- `make host-rollback` restores the last host theme backup and refreshes GRUB.
- `make host-fancy-stage` builds an isolated EFI trial for the inspected Ubuntu 26.04 host.
- `make host-fancy-check` checks that image in disposable Secure Boot QEMU firmware.
- `make host-fancy-benchmark` measures VM rendering and checks shortcuts, gate activation, and the full countdown.
- `make host-fancy-demo` records left/right/left movement and Linux fixture selection as a GIF and extracts a still.
- `make host-fancy-install` installs a separate EFI entry without selecting it.
- `make host-fancy-enroll` requests image hash enrollment through MokManager.
- `make host-fancy-once` arms an enrolled image for one boot only.
- `make host-fancy-remove` removes the separate trial entry and files.
- `make native-build` builds the module against the matching Ubuntu source.
- `make fancy` builds and selects the custom EFI preview in the guest.
- `make boot-test` runs the keyboard and boot regression checks.
- `make dist` packages previews with source and notices.

Useful inspection commands from the project root:

- `jj status` shows the working-copy state.
- `jj diff` shows the current changes.
- `rg --files` lists visible project files.
- `cat README.adoc` displays the project concept.

When adding executable code, document its prerequisites and exact build, run, and test commands in the same change. Verify each command before documenting it.

## Coding style and naming conventions

Preserve AsciiDoc in `README.adoc` and Markdown in this guide. Use short, direct sentences and descriptive headings. In AsciiDoc prose, follow the existing pattern of one sentence per line.

Use four spaces in Python and GRUB's GNU C style in the native module.
Use descriptive names that reflect each file's purpose.

## Testing guidelines

Python tests use `unittest` and live beside the code as `*_test.py`.
For documentation changes, check spelling, markup, referenced paths, and command accuracy.

When adding behavior, include appropriate tests and a reproducible test command. Name tests after the behavior they verify, and add regression coverage for bug fixes.
Run only one boot-test process against the VM at a time.
GitHub Actions runs `make test` with GCC and Clang on Ubuntu 24.04, including the font-dependent artwork tests, plus Clang static analysis and sanitizers.
For rendering or input changes, inspect actual GRUB captures as well as the automated results; see `docs/research/preview.adoc`.

## Commit and pull request guidelines

Use Jujutsu (`jj`) for all version-control operations in this repository, including status, diffs, and commits.
When commits are authorized, commit at logical step boundaries.
Use short, imperative commit subjects, such as `docs: clarify project scope`.

Keep pull requests focused. Explain the purpose, describe the changes, and state how you verified them. Link related issues when available. For visual or interaction changes, include screenshots or a short recording. Update this guide when the project structure or workflow changes.
