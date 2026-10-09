# Segmentierung und Sichtbarkeitsmodell: getrennte Prototypen

## Was läuft heute?

`e57/segment_e57.py` liest genau einen E57-Scan blockweise, wendet dessen Pose
einmal an, schneidet optional einen Raumbereich aus und voxelisiert die Punkte.
Anschließend sucht `segment_planes()` mit Open3D-RANSAC Ebenen. Räumliche
Komponenten werden getrennt; optional folgen senkrechte Zylinder und freie
DBSCAN-Gruppen. `assignments.csv` enthält **geometrische Segment-IDs** für die
verarbeiteten Punkte, `segments.json` die Modellparameter. Weder Objektname noch
Scanner-Sichtbarkeit werden daraus abgeleitet. Es gibt auch synthetische
Testszenen; `e57/scanner_scene.py` nutzt Raycasting nur, um eine dichte,
teilweise verdeckte *Eingabepunktwolke* zu erzeugen. Die bekannten Objekt-IDs
werden dabei nur nachträglich zur Bewertung verwendet.

`visibility_twin/run.py` simuliert Scannerstrahlen aus mehreren Stationen.
`scan.py` liefert je Station die Punktkoordinaten, die Scannerposition und
`obj_id` als **Orakel-Label** aus der bekannten synthetischen Szene. Aus
Scannerposition und Treffpunkten markiert `voxels.py` Bereiche als frei,
belegt oder unbekannt. `fit.py` verwendet die Orakel-IDs für Geräte-/Balken-/
Trassen-Boxen sowie den Rohrfit; danach bewerten Checker und Next-Best-View
Installationsvorschläge. Hier findet derzeit **keine RANSAC-Segmentierung**
statt.

| Benötigt im Visibility Twin | Heute aus `e57` verfügbar? | Offene Lücke |
| --- | --- | --- |
| Punkte pro Scannerstandpunkt und dessen Position | Ein ausgewählter Scan mit E57-Pose | Scanursprung/Richtungen für alle Standpunkte erhalten; nicht nur eine zusammengeführte Wolke |
| Frei / belegt / unbekannt | Nein | Strahlen vom jeweiligen Ursprung zu den gemessenen Treffern für Carving nutzen |
| Geometrische Teilflächen | Ja, als Segment-IDs und Parameter | Nähe und Mehrfachzuordnung über mehrere Scans konsistent behandeln |
| Objektinstanzen wie Gerät, Rohr, Trasse | Nur Teilsegmente ohne solche Klassen | Teilflächen zu Objekten zusammenführen; Unsicherheit und Restpunkte beachten |
| Semantische Labels `DEVICE`, `BEAM`, `PIPE`, `TRAY` | Nein | Nicht aus einer Ebenen-ID ableitbar; zusätzliche Erkennung oder manuelle Zuordnung nötig |

## Sauberer Integrationspfad

1. Echte E57-Scans **je Standpunkt** mit Pose, Gültigkeit und optional RGB laden;
   Roh-/Voxel-Punktindex, Scan-ID und Scannerursprung nachvollziehbar halten.
2. Geometrische Segmente finden und ihre Qualität messen. Punkte ohne sicheres
   Segment nicht als freier Raum interpretieren.
3. Erst danach Objektinstanzen und Semantik zuweisen oder unklar lassen.
   Ein Kiosk kann mehrere Ebenensegmente haben; ein Freiformsegment ist nicht
   automatisch ein bestimmtes Objekt.
4. Die gemessenen Strahlen für das Sichtbarkeitsgitter verwenden; für Fits
   nur hinreichend verlässliche Objektgruppen übernehmen. Verdeckte Bereiche
   bleiben unbekannt, auch wenn eine Ebene in ihrer Nähe erkannt wurde.
5. Die Orakel-IDs im synthetischen Zwilling testweise durch vorhergesagte IDs
   ersetzen und Abweichungen gegen die Ground Truth messen, bevor echte
   Installationsvorschläge beurteilt werden.

Das ist ein **Plan, keine bereits implementierte Kopplung**. Insbesondere
behaupten die Ergebnisse in `visibility_twin/ERGEBNISSE.md` noch keine Leistung
der `e57`-Segmentierung auf dem Visibility-Twin-Szenario.
