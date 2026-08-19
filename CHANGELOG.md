# Changelog

## 0.1.4 – 2026-08-19

### Neu

- Windows-Installer auf Basis von Inno Setup
- Installation nach Program Files
- Startmenü-Verknüpfung
- optionale Desktop-Verknüpfung
- saubere Windows-Deinstallation
- portable ZIP-Version bleibt parallel verfügbar

### Installer / Updates

- stabile AppId für spätere Upgrades
- Upgrade bestehender Installation ohne Doppelinstallation
- Same-Version-Reinstall erlaubt
- Downgrade auf ältere Version wird blockiert
- Benutzerdaten bleiben bei Upgrade und Deinstallation erhalten
- vollständig offline
- kein Python auf dem Zielrechner erforderlich

### Release-Pipeline

- einheitliche Windows-Pipeline für Nuitka, portable ZIP und Setup
- ZIP und installierte EXE verwenden denselben Nuitka-Binary
- SHA256-Sidecars und SHA256SUMS
- Release-Manifest und Integritätsprüfungen

## 0.1.3 – 2026-08-19

### Behoben

- BGF-Teilkreis: Der aktive Heidenhain-Pol wird vor jeder Teilkreisposition absolut wiederhergestellt.
- Verhindert Positionsverschiebungen, wenn das BGF-Unterprogramm eigene CC-Sätze verwendet.

### Verbessert

- BLK FORM gibt auch ungerade und dezimale Rohteilmaße exakt aus.
- Rohteil-Kantenlänge und Rohteil-Hoehe muessen finite und > 0 sein.
- Rohteil-Oberkante Z ist jetzt unabhaengig vom Bohrungsanfang Z.
- Lokale Bearbeitungsflaechen auf Absaetzen, z. B. Z-10 bei Rohteiloberkante Z0, werden korrekt unterstuetzt.

### Sicherheit

- Nach Aenderung eines NC-relevanten Parameters wird der bestehende NC-Code als veraltet markiert.
- Veralteter NC kann weder als *.H exportiert noch in die Zwischenablage kopiert werden.
- Der Benutzer muss bewusst neu generieren.

### Validierung

- CERATIZIT BGF M16
- Teilkreis Ø430
- 6 Positionen
- Mitte X0/Y0
- Rohteiloberkante Z0
- Bohrungsstartflaeche Z-10
- Rohteilhoehe 60 mm
- reale Simulation PASS

## 0.1.2 – 2026-08-18

### Geändert

- HEULE-BSF-Werkzeugvermessung fachlich eindeutig dargestellt.
- Werkzeuglänge wird an der unteren Werkzeug-Stirnfläche auf der Messdose vermessen.
- Die ausgeklappte Schneide liegt vom Vermesspunkt in +Z-Richtung zur Spindel.
- GUI, Hilfsgrafik und NC-Kommentare verwenden die neue eindeutige Vermesspunkt-Terminologie.

### Sicherheit

- Neuer Sicherheits- und Nutzungshinweis beim ersten Start einer Programmversion.
- NC-Programme müssen vor Maschineneinsatz geprüft werden.
- Simulation, Einzelsatz bzw. Trockenlauf werden empfohlen.
- Verwendung der erzeugten Programme erfolgt eigenverantwortlich.
- Hinweis jederzeit über Hilfe erreichbar.

### Marken

- HEULE und CERATIZIT werden als Marken bzw. eingetragene Marken ihrer jeweiligen Rechteinhaber kenntlich gemacht.
- Keine Verbindung, Freigabe oder Zertifizierung durch HEULE oder CERATIZIT wird behauptet.

### Unverändert

- BSF Bewegungs-NC
- BGF Bewegungs-NC
- ZREF
- HEULE ToolProfile-Werte
- Aktivierungssequenz
- M-Funktionen
- Prozessdrehzahlen

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
