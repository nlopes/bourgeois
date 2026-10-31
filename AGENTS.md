# Repository Guidelines

## Project structure and module organization

bourgeois themes GRUB with an interface inspired by point-and-click adventure games.
Development targets Ubuntu 24.04 x86_64 UEFI in a disposable QEMU guest.

- `README.adoc` describes the project’s motivation and direction.
- `AGENTS.md` contains contributor guidance.
- `docs/research/` contains feasibility research and design proposals.
- `docs/research/mockups/` contains concept boards and their generation prompts.
- `tools/` contains Python build and VM tooling, with tests beside the code.
- `assets/` contains shared PNG artwork and generation prompts.
- `fancy/` contains the GPLv3+ native GRUB module and its license.
- `build/` contains ignored guest disks, keys, caches, and evidence.

Add implementation directories when needed, and document their purpose here.
Keep the README focused on the project and its setup.

## Build, test, and development commands

Use Python 3.11 or newer, Make, QEMU, xorriso, and OpenSSH.
See the README for setup and verified commands.

- `make vm` starts the disposable Ubuntu guest.
- `make screenshot` captures its display under `build/evidence/`.
- `make test` runs the local tests.

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

## Commit and pull request guidelines

Use Jujutsu (`jj`) for all version-control operations in this repository, including status, diffs, and commits.
When commits are authorized, commit at logical step boundaries.
Use short, imperative commit subjects, such as `docs: clarify project scope`.

Keep pull requests focused. Explain the purpose, describe the changes, and state how you verified them. Link related issues when available. For visual or interaction changes, include screenshots or a short recording. Update this guide when the project structure or workflow changes.
