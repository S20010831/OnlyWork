# Third-party notices

## Example vocabulary

`examples/cet4-vocabulary.xlsx` derives from [skywind3000/ECDICT](https://github.com/skywind3000/ECDICT),
commit `bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b`, retrieved 2026-10-08.
Copyright (c) 2025 Linwei. MIT license: [examples/LICENSE-ECDICT](examples/LICENSE-ECDICT).
The complete notice is also embedded in the workbook's vocabulary sheet.

## Windows runtime

The portable ZIP contains unmodified Python, Qt for Python / PySide6 / Shiboken,
openpyxl and et_xmlfile runtime components. They retain their own licenses;
the project's MIT license does not replace those licenses.

- [Python](https://docs.python.org/3/license.html): PSF license, included with the bundled Python runtime.
- [Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html): distributed here under LGPL-3.0;
  license texts are in `docs/licenses/`. Corresponding source is available from
  [Qt for Python source releases](https://download.qt.io/official_releases/QtForPython/pyside6/).
  Qt and Shiboken libraries remain separate in `_internal/` and can be replaced.
  Qt's own third-party notices are available at [Qt license information](https://doc.qt.io/qt-6/licenses.html).
- [openpyxl](https://pypi.org/project/openpyxl/): MIT; see `docs/licenses/openpyxl.txt`.
- [et_xmlfile](https://pypi.org/project/et-xmlfile/): MIT; see `docs/licenses/et_xmlfile.txt`.

Runtime versions for each portable release are listed in `runtime-versions.json` inside the ZIP.
