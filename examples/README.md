# Example Apps

Both Example Apps install only their final Engine SDK Distribution and exercise
the same public lifecycle: initialize, open, navigation through Surface reuse,
rectangle updates, close/reopen, Dispose, and visible error reporting.

- `unity/` is a Unity project. CI extracts the final Unity `.tgz` to
  `Packages/com.tedliou.verve-webview` and invokes `BuildExample.Build` through
  the exact editor declared by `compatibility.json`.
- `godot/` is a Godot project. CI extracts the final Godot ZIP at the project
  root and imports/exports it using the exact editor and matching templates
  declared by `compatibility.json`.

The machine-readable scenarios in `verification/shared-suites.json` are the
single semantic source for both engine harnesses. Real platform runs publish
Release Evidence; absence of a device, runtime, required suite result, or exact
artifact digest never counts as a pass.
