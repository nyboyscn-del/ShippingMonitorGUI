# Legacy build scripts

These files are kept only for historical reference. They are **not** release
entry points and may not match the current packaging rules.

The single official build path is the repository-root `build_exe.bat`. It runs
the dependency check, the release smoke tests, the PyInstaller command line
build, and the release security check in one sequence. No `.spec` file is
maintained in the source tree; the spec emitted under `build/` is a build
artifact.

Do not add new build wrappers here. If a historical workflow is still needed,
fold it into `build_exe.bat` or `tools/package_usb_portable.py` instead.
