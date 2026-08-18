# Changelog

## 0.1.1 – 2026-08-18

### Neu

- Freie Z-Lage der Bearbeitungsebene fuer BGF.
- BGF Teilkreis unterstuetzt gemeinsame Oberflaeche auf Z+/Z-.
- BGF Koordinatenliste behaelt individuelle `surface_z`-Werte.
- Freie Z-Lage der HEULE-BSF-Bezugsebene.
- HEULE-BSF Werkzeugprofile eingefuehrt.
- Werkzeuglaengenvermessung erfolgt ueber Halter-Messflaeche.
- BSF-C-1000/050-10.5-23: Halter -> Schneide 8.550 mm.
- BSF-E-1350/050-16.5-14: Halter -> Schneide 11.400 mm.
- HEULE Aktivierungsdrehzahl automatisch aus Werkzeugprofil: C = 2000 U/min, E = 1500 U/min.
- BSF Projektformat Version 2.

### Kompatibilitaet

- BSF V1-Projekte werden weiterhin geladen.
- Keine automatische Umrechnung alter BladeGeometry auf ein HEULE-Werkzeug.
- Werkzeug muss bei Legacy V1 explizit gewaehlt werden.

### Entfernt

- manuelle Schwertdicken-Eingabe
- SPINDLE_SIDE_EDGE
- TOOL_TIP_SIDE_EDGE
- Messerschneide als Werkzeuglaengenreferenz

### Sicherheit

- Keine Heidenhain Nullpunktverschiebung eingefuehrt.
- Kein CYCL DEF 7.
- safe_z / end_safe_z bleiben absolute Programm-Z-Werte.
- Aktivierungsdrehzahl ersetzt NICHT die Prozessdrehzahl.
- Messer-/M-Funktionssequenz bleibt unveraendert.

## Version 0.1.0

2026-08-17

Technisches Windows-Standalone-Paket (Nuitka). Keine Aussage über eine abgeschlossene reale HEULE-Werkzeugvalidierung.

### CERATIZIT BGF

- CERATIZIT BGF Codeerzeugung
- BGF M5/M6/M8/M10/M16/M16x1.5
- variable Gewindetiefe über AXIAL_TEMPLATE_SHIFT_MODEL
- Einzelposition
- Teilkreis
- Koordinatenliste
- JSON/CSV Persistenz
- Positionsvorschau
- BGF Hilfsgrafik
- Werkzeugradius-Hinweis
- Bohrungsanfang Z / `surface_z` fuer Teilkreis, Einzelposition und Koordinatenliste

### HEULE BSF

- HEULE BSF Codeerzeugung
- Schwertdicke
- Vermessreferenz
- Einzelposition
- Teilkreis
- Koordinatenliste
- JSON/CSV Persistenz
- Positionsvorschau
- BSF Hilfsgrafik
- freie Z-Lage der Bezugsebene (`reference_z`, Default 0.000)

Offener Punkt: reale HEULE-BSF-Schwert-/Vermessvalidierung steht aus (`BSF.VAL.1` / `PENDING`).

### Anwendung / Packaging

- Windows App-Icon
- Info-Fenster
- Nuitka Standalone Build
- portables Releasepaket
