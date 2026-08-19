"""Zentrale Produktmetadaten fuer GUI, Info-Fenster und Nuitka-Build.

Eine Quelle fuer Name, Version, Autor und Windows-Dateiversion.
Kein CNC-/Domainbezug.
"""

from __future__ import annotations

APP_NAME = "NC-Code Generator"
APP_VERSION = "0.1.4"

APP_AUTHOR = "Jens Behm"
APP_WEBSITE = "behm-it.de"
APP_WEBSITE_URL = "https://behm-it.de"
APP_EMAIL = "info@behm-it.de"
APP_MAILTO = "mailto:info@behm-it.de"

APP_COPYRIGHT = "© 2026 Jens Behm"

APP_DESCRIPTION = "NC-Code-Erstellung für HEULE BSF und CERATIZIT BGF"

WINDOWS_COMPANY_NAME = "Jens Behm"
EXE_FILENAME = "NC-Code-Generator.exe"
DIST_FOLDER_NAME = "NC-Code-Generator"


def derive_windows_version(app_version: str) -> str:
    """Mappt semantische x.y.z auf die 4-teilige Windows-Version x.y.z.0.

    Freie Strings wie '0.1.0-beta' werden nicht akzeptiert.
    """
    parts = (app_version or "").split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(
            f"APP_VERSION muss genau drei numerische Teile haben (x.y.z), nicht '{app_version}'."
        )
    return f"{int(parts[0])}.{int(parts[1])}.{int(parts[2])}.0"


WINDOWS_FILE_VERSION = derive_windows_version(APP_VERSION)
WINDOWS_PRODUCT_VERSION = WINDOWS_FILE_VERSION

# Release-Kennzeichnung, keine CNC-Domainkopplung.
# True nach fachlichem Gate BSF.VAL.1.
BSF_REAL_TOOL_VALIDATED = True
