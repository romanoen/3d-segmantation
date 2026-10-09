# 3d-segmantation

Experimentelle Prototypen zur Auswertung von 3D-Punktwolken.

Aktuell enthalten: [Visibility Twin](visibility_twin/README.md) – ein synthetischer,
sichtbarkeitsbewusster digitaler Zwilling mit Voxel-Carving, Installationsprüfung
und Vorschlag für einen Nachscan. Die [Ergebnisse](visibility_twin/ERGEBNISSE.md)
beschreiben Versuch und Grenzen.

```bash
cd visibility_twin
conda env create -f environment.yml
conda activate visibility-twin
python run.py
python -m pytest tests
```

Der Lauf erzeugt die interaktiven HTML-Dateien
`visibility_twin/out/viewer_3d.html` und `visibility_twin/out/slices.html`.
Beispielausgaben sind im Repository enthalten; zum interaktiven Betrachten
die HTML-Dateien lokal im Browser öffnen.
