# Repository Guidelines

## Project structure and module organization

bourgeois explores a grub experience inspired by point-and-click adventure games. The project is at the concept stage.

- `README.adoc` describes the project’s motivation and direction.
- `AGENTS.md` contains contributor guidance.

There are no source, test, or asset directories yet. Add directories when implementation requires them, and document their purpose here. Keep the README focused on the project and its setup.

## Build, test, and development commands

No build system, dependency manifest, or development scripts are configured. There are currently no build, run, or test commands.

Useful inspection commands from the project root:

- `jj status` shows the working-copy state.
- `jj diff` shows the current changes.
- `rg --files` lists visible project files.
- `cat README.adoc` displays the project concept.

When adding executable code, document its prerequisites and exact build, run, and test commands in the same change. Verify each command before documenting it.

## Coding style and naming conventions

Preserve AsciiDoc in `README.adoc` and Markdown in this guide. Use short, direct sentences and descriptive headings. In AsciiDoc prose, follow the existing pattern of one sentence per line.

No language-specific indentation rules, formatter, or linter exist yet. When introducing a language, use its standard formatter and document the command. Use descriptive names that reflect each file’s purpose.

## Testing guidelines

No test framework or coverage threshold is configured. For documentation changes, check spelling, markup, referenced paths, and command accuracy.

When adding behavior, include appropriate tests and a reproducible test command. Name tests after the behavior they verify, and add regression coverage for bug fixes.

## Commit and pull request guidelines

Use Jujutsu (`jj`) for all version-control operations in this repository, including status, diffs, and commits.
When commits are authorized, commit at logical step boundaries.
Use short, imperative commit subjects, such as `docs: clarify project scope`.

Keep pull requests focused. Explain the purpose, describe the changes, and state how you verified them. Link related issues when available. For visual or interaction changes, include screenshots or a short recording. Update this guide when the project structure or workflow changes.
