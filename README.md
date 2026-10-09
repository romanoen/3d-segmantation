# 3d-segmantation

Experimentelle, voneinander unabhängige Prototypen für 3D-Punktwolken:

| Ordner | Aufgabe | Stand |
| --- | --- | --- |
| [`e57/`](e57/README.md) | E57-Scan lesen; große Ebenen per RANSAC, weitere Geometrie per optionaler Zylinder-/Freiform-Gruppierung segmentieren | echte E57-Dateien möglich; überwiegend synthetisch getestet |
| [`visibility_twin/`](visibility_twin/README.md) | Aus Scannerstrahlen frei/belegt/unbekannt ableiten, Installationsraum prüfen und Nachscan vorschlagen | synthetische Szene mit perfekten Objekt-IDs |

**Die beiden Pipelines sind noch nicht verbunden.** Das Raycasting im
`visibility_twin` simuliert Scans und untersucht Sichtbarkeit. Seine Objekt-IDs
stammen direkt aus der Simulation, nicht aus `e57`-RANSAC. Der dichte Test in
`e57` nutzt ebenfalls Raycasting, aber nur zur Erzeugung der Eingabepunkte;
die Segmentierung erhält keine Herkunftslabels. Die Schnittstellen und der
nötige Integrationsschritt stehen in [ARCHITEKTUR.md](ARCHITEKTUR.md).

## E57-Segmentierung

```bash
cd e57
conda env create -f environment.yml
conda activate e57-segmentation
python segment_e57.py --synthetic --no-visualization
python -m unittest test_segmentation test_rgb test_robustness test_novel_scene test_dense_scan
```

Beispiele für E57-Dateien, Raum-/Baustellenszenen und den dichten Scantest stehen
in der [E57-README](e57/README.md). Generierte Punktwolken und CSV-Ergebnisse
werden lokal erzeugt und nicht versioniert.

## Visibility Twin

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
die HTML-Dateien lokal im Browser öffnen. Die
[Ergebnisse](visibility_twin/ERGEBNISSE.md) beschreiben Versuch und Grenzen.
