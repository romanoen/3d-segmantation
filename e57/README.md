# E57: geometrische Punktwolken-Segmentierung

Lokal ausführbarer Prototyp: E57-Scan einlesen, Ausschnitt wählen, voxelweise
reduzieren, Ebenen iterativ mit RANSAC finden und farbig anzeigen. Optional
folgen senkrechte Zylinder und freie Punktgruppen; synthetische Szenen dienen
der überprüfbaren Evaluation. Semantik und räumliche Beziehungen sind nicht
implementiert.

Dieser Ordner ist vom [Visibility Twin](../visibility_twin/README.md)
getrennt: Dessen derzeitige Objekt-IDs stammen direkt aus der Simulation,
nicht aus dieser Segmentierung. Auch `scanner_scene.py` verwendet Raycasting
nur zur Erzeugung der Testpunkte; die Segmentierung bekommt keine Objekt-IDs.
Schnittstellen und Integrationslücken stehen in [ARCHITEKTUR.md](../ARCHITEKTUR.md).
Die großen erzeugten Ausgabeordner und rohe E57-Dateien bleiben lokal und sind
nicht Teil des Git-Repositories.

## Installation

```bash
cd e57
conda env create -f environment.yml
conda activate e57-segmentation
```

Conda verwaltet die Umgebung mit Python 3.12; die Python-Bibliotheken werden
dabei automatisch per pip aus `requirements.txt` innerhalb dieser Umgebung
installiert. In der IDE den Python-Interpreter der Conda-Umgebung
`e57-segmentation` auswählen.

Bei Änderungen an den Abhängigkeiten (ebenfalls aus dem Ordner `e57`):

```bash
conda env update -f environment.yml
```

## Synthetischer Test

Die Testszene enthält zwei räumlich getrennte Stücke derselben horizontalen
Ebene, eine vertikale Ebene und Ausreißer:

```bash
python segment_e57.py --synthetic --no-visualization --output-dir synthetic_output
```

Danach liegen `assignments.csv`, `segments.json` und (mit Open3D) `segmented.ply`
im Ausgabeordner. `0` bedeutet nicht zugeordnet; positive Werte sind
Segment-IDs. Die Zuordnungen beziehen sich auf die nach Ausschnitt und
Voxel-Downsampling verbleibenden Punkte.

## Verrauschter Raum mit vier Wänden

```bash
python segment_e57.py --room --noise 0.015 \
  --distance-tolerance 0.045 --min-segment-size 500 --output-dir room_output
```

Die vier Wände umschließen einen 6 × 4 m großen, 2,8 m hohen Raum ohne Boden
und Decke. Alle Koordinaten werden mit gaußschem Rauschen gestört (Standardabweichung
1,5 cm je Achse). 10 % der Wandpunkte fehlen zufällig; zusätzlich gibt es 800
verstreute Ausreißer. `--seed` (Standard: 7) macht die Erzeugung und RANSAC
reproduzierbar. Auch synthetische Szenen durchlaufen Ausschnitt und Voxelreduktion.
Mit `--noise 0.03` lässt sich beispielsweise stärkeres Rauschen untersuchen;
die Abstandstoleranz muss dann eventuell erhöht werden.

Im aktiven Open3D-Fenster wechseln die Zahlentasten die Kamera:

| Taste | Ansicht |
| --- | --- |
| 1 | Schrägansicht |
| 2 | Draufsicht auf den rechteckigen Umfang |
| 3 | Vorderansicht |
| 4 | Seitenansicht |
| 5 | Gegenüberliegende Schrägansicht |

Die Maus erlaubt weiterhin freies Drehen und Zoomen. In Seitenansichten können
sich gegenüberliegende Wände überdecken. Alle Ansichten zeigen dieselben Punkte
und Segmentfarben. Die Kameratasten funktionieren auch für E57-Dateien.
Für einen Test ohne Fenster `--no-visualization` ergänzen.

Beim Test mit den obigen Parametern wurden vier Wandsegmente mit jeweils etwa
1,5 cm RMSE erkannt. Das prüft die geometrische Wandsegmentierung einer einfachen
Raumform; ein geschlossenes Raummodell oder eine semantische Raumerkennung wird
dabei noch nicht berechnet.

## Raum mit Öffnungen und Rohrinstallationen

```bash
python segment_e57.py --room --installations --noise 0.01 \
  --voxel-size 0.02 --distance-tolerance 0.03 --min-segment-size 500 \
  --output-dir room_installations_output
```

Diese Variante ergänzt zwei Türöffnungen (0,9 × 2,1 m), zwei Fensteröffnungen
(1,2 × 1,2 m, Unterkante 1 m) und zwei Gruppen mit jeweils drei senkrechten
Rohren von z=0 bis z=2,8 m. Die Rohre haben 12 cm Außendurchmesser,
18 cm Achsabstand (6 cm freier Zwischenraum) und stehen mit ihrer Achse 40 cm
vor der jeweiligen Wand. Das Messrauschen beträgt 1 cm je Koordinatenachse.
10 % der Wand- und Rohrpunkte fehlen zufällig; 800 Ausreißer kommen hinzu.

Türen und Fenster sind Aussparungen ohne Türblätter, Rahmen oder Glas.
Boden und Decke bleiben unmodelliert. Die Zylinderoberflächen werden ringsum
abgetastet; Sichtverdeckungen eines realen Scannerstandpunkts werden nicht simuliert.
Die Sollgeometrie wird zur Nachvollziehbarkeit in `segments.json` gespeichert,
aber der Segmentierung werden ausschließlich die Punktkoordinaten übergeben.

Mit `R` zwischen Segmentfarben und einheitlich grauer Punktwolke wechseln;
mit `2` die Rohrgruppen von oben betrachten, mit `1` und `5` die Öffnungen
aus schrägen Ansichten. Die Öffnungen sind besonders in Vorder-/Seitenansichten
durch die gegenüberliegenden Wände teilweise verdeckt.

Der Test mit Seed 7 liefert zehn Segmente: vier Wandsegmente (RMSE etwa 1 cm)
und sechs weitere Segmente aus Teilen der Rohrflächen. Letztere sind **keine
erkannten Rohre**: RANSAC passt auch an schmale gekrümmte Oberflächenstreifen
Ebenen an. Der Prototyp erkennt weder Zylinder noch Türen/Fenster als Objekte.
Das Ergebnis zeigt damit auch Fehlsegmentierungen des reinen Ebenenansatzes.

## Große Ebenen und anschließend senkrechte Rohre

```bash
python segment_e57.py --room --installations --noise 0.01 \
  --voxel-size 0.02 --distance-tolerance 0.03 --min-segment-size 500 \
  --cylinders --output-dir room_cylinders_output
```

Mit `--cylinders` akzeptiert die erste Stufe nur Ebenensegmente, deren Ausdehnung
in beiden Hauptrichtungen mindestens `--min-plane-width` (Standard: 1 m)
beträgt. Die Ausdehnung wird zwischen den 2-/98-Perzentilen gemessen. Dadurch
werden schmale Rohrstreifen nicht als Wände entfernt. Abgelehnte Ebenenkandidaten
bleiben für die Zylindersuche verfügbar, blockieren aber nicht die weitere
Ebenensuche. Diese Größenheuristik ist keine semantische Wandklassifikation.

Aus den übrigen Punkten sucht Kreis-RANSAC in XY senkrechte Zylinder. Die Achsen
müssen parallel zur globalen Z-Achse liegen. Weder Rohrzahl noch Rohrpositionen
werden vorgegeben. Standardparameter sind `--radius-range 0.03 0.12`,
`--cylinder-tolerance 0.02` und `--min-cylinder-height 1.0`; die Mindestpunktzahl
kommt aus `--min-segment-size`. Eine Verteilung über mindestens zehn von zwölf
Winkelsektoren und alle acht Höhenintervalle ist erforderlich. Das ist für die
ringsum erzeugten Rohre gedacht; einseitig sichtbare reale Rohre, geneigte Rohre
und Rohrbögen sind damit noch nicht zuverlässig abgedeckt.

Jeder Zylinder erhält eine eigene Segmentfarbe. In `segments.json` kennzeichnet
`type` die Geometrie (`plane` oder `cylinder`). Zylinder enthalten Achspunkt,
Achsrichtung, Radius sowie `z_min`, `z_max` und Höhe. Die Höhenenden sind robuste
2-/98-Perzentile der zugeordneten Punkte und unterschätzen daher die vollständige
Rohrlänge etwas. Der Zylinder-RMSE misst den radialen Abstand zur Mantelfläche;
die CSV-Zuordnungen und die PLY verwenden dieselben Segment-IDs.

Der erste Test (Seed 7) erkennt vier Wände und sechs einzelne Rohre mit Radien
von rund 6,1 cm und radialem RMSE um 9 mm. Die Tür-/Fensteröffnungen bleiben
Aussparungen ohne Objektklassifikation. Geometrische Regressionstests starten mit:

```bash
python -m unittest test_segmentation -v
```

## Unregelmäßige Wandkonstruktion als freie Geometrie

```bash
python segment_e57.py --room --wall-construction --freeform --noise 0.01 \
  --voxel-size 0.02 --distance-tolerance 0.03 --min-segment-size 500 \
  --output-dir room_freeform_output
```

Die Konstruktion an der Wand y=4 besteht aus einer kleinen Platte, zwei
diagonalen Befestigungsstreben mit Wandkontakt und einem gekrümmten Teil mit
veränderlichem Querschnitt. Die Segmentierung kennt weder die Position noch
die Form dieser Konstruktion. Nach der Erkennung großer Ebenen gruppiert
`--freeform` die Restpunkte per DBSCAN nach Nähe, ohne ein Formmodell anzupassen.
`--cluster-distance` (Standard 0,08 m) steuert den Nachbarschaftsradius,
`--min-freeform-size` (Standard 150) die Mindestpunktzahl eines freien Segments.
Die ursprünglichen Punkte bleiben in CSV/PLY erhalten, auch nicht zugeordnete
graue Restpunkte. Freie Segmente erhalten eine Farbe und den Typ `freeform` in
JSON, mit Bounding Box und Schwerpunkt. Modellparameter und Anpassungsfehler
sind `null`, da kein geometrischer Fit vorgenommen wird.

Mit den obigen Parametern ergeben sich vier Wände und ein freies Segment.
Bei Seeds 7, 11 und 23 enthält dieses etwa 97 % der nach Voxelreduktion
verbleibenden Konstruktionspunkte; über 99 % seiner Punkte gehören zur
Konstruktion. Das wird im Test mit bekannten Erzeugungsdaten geprüft,
die nicht in die Segmentierung eingehen. An Wandkontaktstellen werden Teile
der Streben weiterhin der Wand zugeordnet. Größere Clusterabstände können
benachbarte Objekte verbinden; kleinere können ein Objekt zerlegen. Ein freies
Segment ist daher ein zusammenhängender Punktbereich, nicht automatisch ein
korrekt abgegrenztes Bauteil. Große ebene Teile einer Konstruktion können
weiterhin als Ebene erfasst werden.

Die Szene lässt sich mit `--installations` um die bisherigen Rohre und Öffnungen
ergänzen. Mit zusätzlichem `--cylinders` ist die Reihenfolge: große Ebenen,
senkrechte Zylinder, freie Restsegmente. Ohne Zylindersuche können dicht stehende
Rohre als gemeinsame freie Gruppe erscheinen. `R` und die Kameratasten `1`–`5`
funktionieren unverändert; zum Betrachten der Konstruktion Ansicht `1`/`5`
verwenden und mit der Maus drehen.

## Zwei benachbarte Wandkonstruktionen

Getrennte Konstruktionen mit 15 cm Abstand:

```bash
python segment_e57.py --room --two-constructions --construction-gap 0.15 \
  --freeform --noise 0.01 --voxel-size 0.02 --distance-tolerance 0.03 \
  --min-segment-size 500 --output-dir room_pair_015_output
```

Für den Gegenversuch `--construction-gap 0.05` und
`--output-dir room_pair_005_output` verwenden. `--two-constructions` ersetzt
die einzelne Konstruktion, auch wenn zusätzlich `--wall-construction` gesetzt ist.
Der Abstand bezeichnet die Lücke zwischen den X-Begrenzungen der rauschfreien
Geometrien; Rauschen kann die tatsächliche Lücke verkleinern. Beide Konstruktionen
haben unabhängiges Rauschen und jeweils Kontakt zur Wand. Das Clustering bekommt
weder die Anzahl noch ihre ursprünglichen Punktzuordnungen.

Der Abstandstest mit 1 cm Rauschen und 8 cm DBSCAN-Radius ergab:

| Abstand | Freie Segmente bei Seeds 7 / 11 / 23 |
| --- | --- |
| 2 cm | 1 / 1 / 1 (zusammengefasst) |
| 5 cm | 1 / 1 / 1 (zusammengefasst) |
| 8 cm | 1 / 1 / 1 (zusammengefasst) |
| 12 cm | 2 / 2 / 2 (getrennt) |
| 15 cm | 2 / 2 / 2 (getrennt) |
| 20 cm | 2 / 2 / 2 (getrennt) |

Dies ist keine allgemeine Grenzdistanz: Rauschen, Punktdichte, Ausreißer und
DBSCAN-Radius beeinflussen, ob verbindende Punktketten entstehen. Die beiden
Konstruktionen werden bei kleinen Abständen erhalten, aber nicht mehr einzeln
abgegrenzt. Ein kleinerer Radius kann sie trennen, gleichzeitig jedoch auch
eine einzelne Konstruktion zerlegen.

Mit `python test_construction_gaps.py` lässt sich die Messreihe wiederholen.
`construction_gap_results.csv` enthält auch den pro Konstruktion erfassten
Punktanteil und die Reinheit ihres dominanten freien Segments, ausgewertet nach
Voxelreduktion anhand der ausschließlich zur Prüfung bekannten Herkunft.
Bestehende CSV-Messwerte werden bei erneuter Ausführung ersetzt.

## Komplexe Baustellen-Testszene

```bash
python segment_e57.py --construction-site --freeform --noise 0.01 \
  --voxel-size 0.02 --distance-tolerance 0.03 --min-segment-size 500 \
  --output-dir construction_site_output
```

`--construction-site` ist eine eigene Eingabequelle, also nicht mit `--room`
kombinieren. Im 6 × 4 × 2,8-m-Raum befinden sich vier Wände mit zwei Tür- und
zwei Fensteröffnungen, ein Boden (keine Decke) und folgende Oberflächen:

- Die bisherigen zwei Gruppen eng benachbarter senkrechter Rohre.
- Vier weitere Steigleitungen, die jeweils über einen 90°-Bogen in horizontale
  Leitungen übergehen; 10 cm Durchmesser und 16 cm Abstand der parallelen Achsen.
- Drei schräge Leitungen, ein offener Installationskanal und Querhalterungen.
- Ein Gerüst mit vier Stützen, diagonalen Streben, Geländern und einer Plattform.
- Ein Gehäuse, gestapelte Materialkisten, eine angelehnte Platte,
  vier lose Rohre auf dem Boden und eine Kabelschlinge.
- Zwei unregelmäßige Wandkonstruktionen mit nur 5 cm Abstand.

Der Generator in `construction_site.py` erzeugt Oberflächenpunkte mit zufälligen
Ausfällen und Rauschen. Er ist eine baustellenähnliche Geometrieanordnung, kein
physikalisch oder baulich geprüftes Anlagenmodell. Es gibt Kontakte und
Überlagerungen zwischen Bauteilen. Scannerstandpunkte, Strahlverfolgung und
realistische Sichtverdeckungen werden weiterhin nicht simuliert. Die Benennungen
im Inventar von `segments.json` dokumentieren nur die Erzeugung; die Segmentierung
erhält keine Bauteil-Labels oder Sollzuordnungen.

Mit Seed 7 und dem obigen Befehl entstehen 107.714 Rohpunkte und 95.094 Punkte
nach Voxelreduktion. Der Testlauf lieferte neun Ebenensegmente und zehn freie
Segmente, keine verifizierten 19 Objekte: Gerüstteile können fälschlich als
Ebenen erfasst werden, Wände zerfallen teilweise in mehrere Segmente, und
eng stehende Installationen werden zusammengefasst. Das ist ausdrücklich ein
Belastungstest des bestehenden Verfahrens. Die unveränderten Punkte bleiben
einschließlich grauer Restpunkte in CSV und PLY erhalten.

Mit `R` lässt sich die ungefärbte Szene betrachten, mit `2` von oben, mit `1`
und `5` schräg. `--cylinders` kann optional ergänzt werden, sucht aber weiterhin
nur senkrechte Zylinder und erkennt keine horizontalen Rohre oder Bögen als solche.

## Eingangs-RGB zusätzlich zur Geometrie

```bash
python segment_e57.py --construction-site --freeform --use-rgb --noise 0.01 \
  --voxel-size 0.02 --distance-tolerance 0.03 --min-segment-size 500 \
  --output-dir construction_site_rgb_output
```

Die Baustellenszene enthält jetzt simulierte Materialfarben mit räumlichen
Helligkeitsschwankungen und Farbrauschen. Mehrere Bauteile teilen dieselbe Farbe
(z. B. jeweils zwei benachbarte Leitungen und die Gerüstteile). Die beiden
Wandkonstruktionen haben für diesen Vergleich verschiedene Farben. Die Basis-
Raumszene einschließlich ihrer ursprünglichen Rohrgruppen ist einheitlich hell.
Diese Eingangsfarben werden **vor** der Segmentierung erzeugt; sie sind keine
Segment-IDs. Die geometrischen Punkte bleiben gegenüber dem farblosen Generator
gleich. Zum Vergleich denselben Befehl ohne `--use-rgb` und mit einem anderen
Ausgabeordner ausführen.

`--use-rgb` benötigt `--freeform`. Die freie Gruppierung nutzt als Nachbarschaft
sowohl den räumlichen Radius als auch einen maximalen euklidischen RGB-Abstand
(`--color-distance 0.18`, RGB normiert auf [0,1]). Mindestens fünf passende
Nachbarn bilden einen DBSCAN-Kernpunkt. Ebenen- und Zylinderfit bleiben rein
geometrisch; bereits dort falsch zugeordnete Punkte werden durch Farbe nicht
nachträglich korrigiert. Das einfache RGB-Maß ist nicht beleuchtungsinvariant:
starke Schatten können trennen, ähnliche Farben oder Farbübergänge verbinden.
Oberflächennormalen gehen in diese Gruppierung noch nicht ein.

Für eine echte farbige Datei funktioniert beispielsweise:

```bash
python segment_e57.py /pfad/scan.e57 --scan-index 0 --freeform --use-rgb \
  --voxel-size 0.02 --distance-tolerance 0.03 --output-dir scan_rgb_output
```

Der E57-Reader lädt RGB automatisch, sofern alle drei Attribute vorhanden sind,
auch ohne `--use-rgb`. Die Werte werden anhand von `colorLimits` normiert; ohne
diese Angaben wird 0–255 angenommen (die verwendeten Grenzen stehen im JSON).
Float-Lesepuffer vermeiden eine Beschränkung auf 8-Bit-Werte beim Einlesen.
Der gewählte erste Punkt jedes Voxels behält genau seine eigene Farbe.
`isColorInvalid` wird berücksichtigt: Solche Punkte bleiben geometrisch erhalten,
haben `NaN` in den CSV-Farbspalten und werden im RGB-Clustering nicht zugeordnet.
In der Farbanzeige erscheinen sie grau. Bei fehlendem RGB stoppt `--use-rgb`
mit einer Meldung; ohne diese Option funktioniert die geometrische Gruppierung
weiterhin. Die übrigen einfachen synthetischen Szenen haben noch kein RGB.

- `C`: Eingangs-RGB anzeigen, `R`: Segmentfarben/Grau, `1`–`5`: Kameras.
- `input_rgb.ply`: verarbeitete Punkte mit Eingangsfarben.
- `segmented.ply`: dieselben Punkte mit Ergebnisfarben.
- `assignments.csv`: bei vorhandenem RGB zusätzlich `red,green,blue` in [0,1].

Im Baustellentest (Seed 7) entstanden neun Ebenensegmente und 16 freie Segmente
mit RGB gegenüber zehn freien Segmenten ohne RGB. Mehr Segmente sind kein
Qualitätsnachweis. Der kontrollierte Test in `test_rgb.py` prüft zusätzlich:
nahe verschiedenfarbige Flächen werden getrennt, gleichfarbige bleiben verbunden;
E57-RGB bleibt über mehrere Leseblöcke, Transformation, Gültigkeitsfilter und
Ausschnitt korrekt zugeordnet; Voxel behalten passende Punkt-Farb-Paare.

```bash
python -m unittest test_rgb test_segmentation -v
```

## Flächendeckung gegen falsche Gerüst-Ebenen

Die Ebenensuche prüft jetzt standardmäßig die Flächendeckung jedes Kandidaten:
Punkte werden in ihre lokale PCA-Ebene projiziert und in ein Raster mit
`--coverage-cell-size 0.12` eingeordnet. Nach dem Abschneiden der äußeren
2 % je Koordinatenrichtung müssen mindestens `--min-plane-coverage 0.55`
der Rasterzellen im begrenzenden Rechteck belegt sein. Abgelehnte Kandidaten
bleiben als Restpunkte für Zylinder- und freie Gruppierung verfügbar.
Die gemessene Deckung steht als `plane_coverage` im Segment-JSON.

Das reduziert Gerüststreben, die zwar gemeinsam in einer Ebene liegen, aber
keine flächig gefüllte Oberfläche bilden. Tür-/Fensteröffnungen bleiben zulässig,
solange genügend Wandfläche übrig ist. Bei dünn abgetasteten oder stark verdeckten
Wänden kann auch eine echte Fläche abgelehnt werden; Rastergröße, Orientierung
des begrenzenden Rechtecks und Mindestdeckung beeinflussen diese Heuristik.
Mit `--min-plane-coverage 0` lässt sich der Filter zum Vergleich deaktivieren.

```bash
python segment_e57.py --construction-site --freeform --use-rgb --noise 0.01 \
  --voxel-size 0.02 --distance-tolerance 0.03 --min-segment-size 500 \
  --output-dir construction_site_rgb_coverage_output
```

Im früheren Seed-7-Test werden die bisherigen Gerüst-Ebenenkandidaten (Deckung etwa
40 % und 32 %) abgelehnt. 8.839 von 8.859 Gerüstpunkten landen anschließend
zusammen in einem freien RGB-Segment. 20 Punkte an den Füßen verbleiben im
Bodensegment. Der Gesamtlauf liefert sieben Ebenensegmente und 16 freie Segmente;
die oben genannten älteren Segmentzahlen dokumentieren Läufe vor diesem Filter.
Es bleiben andere Fehlsegmentierungen der Baustellenszene möglich. Der Gerüstfall
ist als Regressionstest in `test_rgb.py` hinterlegt; die bisherigen Tests für
Wände mit Öffnungen und Rohre bleiben ebenfalls bestehen. Die genannten sieben
Ebenensegmente stammen vom Stand vor der unten beschriebenen robusteren Suche.

## Robustere Ebenensuche

Ein abgelehnter RANSAC-Kandidat wird nicht erneut als Startmenge verwendet.
Seine Punkte bleiben aber für **spätere Ebenenhypothesen** verfügbar. Jede neue
Hypothese wird dazu gegen alle noch nicht zugeordneten Punkte geprüft, bevor
DBSCAN räumlich getrennte Flächen teilt und die Flächendeckung geprüft wird.
Sonst konnte etwa ein verworfener Gerüst-Kandidat echte Wandpunkte dauerhaft
aus der Ebenensuche entfernen. Das Prinzip verbindet robuste Modellschätzung
mit lokaler räumlicher Prüfung; es ist keine gelernte Segmentierung.

Mit Seed 7 und den obigen Baustellenparametern ergeben sich nun fünf
Ebenensegmente (vier Wände und eine horizontale Fläche). Der neue Test
`test_construction_site_walls_remain_whole` hält diesen konkreten Fall fest.
Bei echten Scans sind insbesondere verdeckte Wände, wechselnde Punktdichten und
nahe parallele Flächen weiterhin offene Probleme; fünf Segmente sind kein
allgemeiner Qualitätsbeleg. Methodische Hintergründe: [Efficient RANSAC for
Point-Cloud Shape Detection](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-8659.2007.01016.x)
und [PCL Region-Growing-Segmentierung](https://pcl.readthedocs.io/projects/tutorials/en/pcl-1.14.1/region_growing_segmentation.html).

### Dichte und Verdeckung messen

```bash
conda activate e57-segmentation
cd e57
python evaluate_robustness.py
python -m unittest test_robustness
```

Der Versuch erzeugt vier Wände mit Tür-/Fensteröffnungen und Ausreißern bei
drei Seeds. Er vergleicht volle, halbe und ungleiche Punktdichte sowie einen
70-cm-breiten, über die ganze Höhe fehlenden Wandstreifen. Die Ground Truth
wird nur **nach** der Segmentierung zur Auswertung benutzt. Alle Punkte werden
wie im Prototypen voxelisiert. `robustness_results.csv` enthält pro Wand und
Lauf die Zahl sichtbarer Punkte, Recall des größten passenden Segments,
Reinheit, nicht zugeordnete Punkte und den Anteil sichtbarer Punkte gegenüber
dem Basisfall. Fehlende Scanpunkte sind dabei nicht als falsch segmentiert
gezählt: `recall_visible` bewertet nur vorhandene Punkte.

Bei Seed 7/11/23 und 2-cm-Voxeln, 3-cm-RANSAC-Toleranz und mindestens 500
Punkten pro Ebene ergab sich folgender Mittelwert über zwölf Wandfälle:

| Szenario | Ebenen-DBSCAN-Radius | Recall sichtbarer Punkte |
| --- | ---: | ---: |
| Basis | 7,5 cm | 98,3 % |
| halbe Dichte | 7,5 cm | 0 % |
| halbe Dichte | 12 cm | 98,2 % |
| ungleiche Dichte | 12 cm | 72,6 % |
| ungleiche Dichte | 18 cm | 98,4 % |
| verdeckter Streifen | 18 cm | 94,0 % |
| ungleiche Dichte + Verdeckung | 18 cm | 87,6 % |

Der Radienvergleich zeigt: Die Ebenen selbst sind bei halber Dichte noch
auffindbar, aber die räumliche DBSCAN-Aufteilung zerlegt sie mit zu kleinem
Radius in Stücke unterhalb der Mindestgröße. Deshalb ist dieser Radius nun
unabhängig von der RANSAC-Abstandstoleranz einstellbar, z. B.
`--plane-cluster-distance 0.12`. Der bisherige Standard bleibt unverändert.
Ein größerer Radius kann nahe koplanare Objekte fälschlich verbinden; er muss
an echten Scans geprüft werden. In der komplexeren synthetischen Baustellenszene
stieg die Zahl der Ebenensegmente bei 18 cm von fünf auf sechs; der Radius ist
also kein pauschal besserer Standardwert. Bei der verdeckten Wand liegt ein sichtbares
Teilsegment unter 500 Punkten und bleibt deshalb unzugeordnet. Der Versuch
simuliert Punktverlust, keinen physikalisch korrekten Laserscanner mit
Sichtstrahlen und Mehrfachreflexionen.

### Zweite Szene: Laderampe statt Rauminstallation

Die zusätzliche Szene in `novel_scene.py` enthält eine geneigte Rampe, einen
quaderförmigen Kiosk, ein ellipsoidförmiges Gehäuse, eine Treppe und ein
gefaltetes Blech auf einer grob abgetasteten Bodenplatte. Es gibt keine
Raumwände, Rohre oder Gerüste. Die Oberflächen haben unterschiedliche
Punktabstände (etwa 4–11 cm), Ausdünnung, 1 cm Messrauschen und Ausreißer.
Objektnamen werden ausschließlich nach dem Lauf zur Auswertung verwendet.

```bash
python segment_e57.py --novel-scene --freeform --use-rgb --noise 0.01 \
  --voxel-size 0.03 --distance-tolerance 0.03 --min-segment-size 300 \
  --plane-cluster-distance 0.12 --cluster-distance 0.12 \
  --min-freeform-size 100 --output-dir novel_scene_rgb_output
python evaluate_novel_scene.py novel_scene_rgb_output
```

Für einen Lauf ohne Fenster `--no-visualization` ergänzen. `R` zeigt die
Segmentfarben, `C` die Eingangsfarben, `1`–`5` wechseln die Perspektive.
Die Auswertung schreibt `object_metrics.csv` in den Ausgabeordner und prüft,
dass die exportierten Punkte zur erzeugten Szene passen.

Bei Seed 7 sind Rampe (97 %), ellipsoidförmiges Gehäuse (nahezu 100 %), Treppe
(99 %) und Faltblech (nahezu 100 %) jeweils überwiegend in einem Segment.
Die Bodenplatte erreicht nur 81 % sichtbaren Punkt-Recall; etwa 19 % bleiben
unzugeordnet. Der Kiosk wird auf mehrere Flächen verteilt: Das größte Segment
enthält nur 22 % seiner Punkte, weitere 38 % bleiben unzugeordnet. Das ist der
Unterschied zwischen **Geometrie-** und **Objektsegmentierung**. RGB verändert
die Zuordnungen in dieser Szene nicht, da die freien Objekte bereits räumlich
getrennt sind. Die Szene ist synthetisch und kein Ersatz für einen echten Scan.

### Dichterer, sichtbarkeitsabhängiger Scan derselben Geometrie

`scanner_scene.py` tastet dieselben sechs Hauptobjekte aus einem festen
Scannerstandpunkt mit Winkelstrahlen ab. Pro Strahl zählt nur der erste
Schnittpunkt; dahinter liegende Flächen werden verdeckt. Der Winkelabstand
von 1,2 mrad entspricht rechnerisch etwa 3,6 mm Querabstand bei 3 m und
12 mm bei 10 m. Dazu kommen 2 mm Standardabweichung im Entfernungswert und
8 % zufällige Ausfälle. Das liegt größenordnungsmäßig bei niedrigen
terrestrischen Auflösungseinstellungen; etwa der [Leica RTC360](https://shop.leica-geosystems.com/reality-capture/rtc/leica-rtc360-laser-scanner/buy)
nennt 3/6/12 mm bei 10 m und der [Trimble X7](https://help.fieldsystems.trimble.com/x7/setup-scan-settings.htm)
je nach Modus 4–11 mm bei 10 m. Der Simulator bildet weder
Reflexionseigenschaften noch Registrierung mehrerer Standpunkte ab.

```bash
python run_dense_experiment.py --output-dir dense_scan_12mrad_output
python run_dense_experiment.py --output-dir dense_scan_12mrad_output --show 10
python -m unittest test_dense_scan
```

Der erste Befehl speichert die Messwerte in `density_metrics.csv` und für 5,
10 und 20 mm Voxelgröße je `assignments.csv`, `segments.json`, `segmented.ply`
und `input_rgb.ply`. Der zweite wiederholt den Lauf und öffnet die 10-mm-Szene
interaktiv (`R` Segmentfarben, `C` Scanfarben, `1`–`5` Perspektiven).
Die bekannten Herkunftslabels fließen **nicht** in die Segmentierung ein.
Auch RGB wird in diesem Dichtevergleich nur angezeigt, nicht für die
freie Clusterbildung verwendet.
Abstandstoleranz (8 mm), Ebenen-Nachbarschaft (4 cm) und freie Nachbarschaft
(6 cm) bleiben beim Vergleich der drei Voxelgrößen konstant.

| Voxel | Punkte | Ebenen / freie Segmente | Kiosk: größtes Segment |
| --- | ---: | ---: | ---: |
| 5 mm | 332.829 | 3 / 5 | 79 % |
| 10 mm | 255.381 | 3 / 5 | 74 % |
| 20 mm | 125.371 | 3 / 5 | 60 % |

Die direkt gemessenen Median-Abstände benachbarter Punkte auf der Bodenplatte
betragen im Rohscan ungefähr 5,3 mm bei 3–5 m und 9,4 mm bei 7–9 m. Die
Ellipsoid-Hülle bleibt in allen drei Auflösungen nahezu vollständig ein freies
Segment. Die Bodenplatte landet dagegen trotz vieler Punkte überwiegend in
einem **freien** Segment: Ihre durch Verdeckung eingeschränkte Flächendeckung
liegt bei etwa 0,5 und unterschreitet die Standardgrenze von 0,55. Eine
Grenze von 0,4 findet die Boden-Ebene, akzeptiert aber auch eine zusätzliche
Ebene. Dies ist ein konkreter Zielkonflikt des aktuellen Filters und kein
Nachweis allgemeiner Robustheit.

## Öffentliche oder lokale E57-Datei

Eine Datei aus dem Abschnitt **Terrestrial LiDAR** der Agisoft-Sample-Daten
herunterladen: <https://www.agisoft.com/downloads/sample-data/>. Danach den
lokalen Pfad verwenden:

```bash
python segment_e57.py /pfad/zur/datei.e57 \
  --scan-index 0 \
  --voxel-size 0.03 \
  --distance-tolerance 0.025 \
  --min-segment-size 150 \
  --bbox 0 0 0 10 10 5 \
  --output-dir output
```

`--bbox` ist optional und wird in den globalen Koordinaten nach der E57-Pose
angewendet. `--scan-index` lädt genau einen Scan. Der Reader liest diesen Scan
blockweise (`--chunk-size`), wendet Rotation und Translation genau einmal an
und führt erst danach das Voxel-Downsampling aus. Die Standardwerte sind nur
Startpunkte; besonders `--voxel-size`, `--distance-tolerance` und
`--min-segment-size` müssen an Punktdichte und Maßeinheit angepasst werden.

## Ausgaben

- `assignments.csv`: Punktkoordinate und Segment-ID für jeden verarbeiteten Punkt.
- `segments.json`: Ebenenparameter `a,b,c,d` für `a*x+b*y+c*z+d=0`, Punktzahl,
  RMSE und mittlerer absoluter Anpassungsfehler.
- `segmented.ply`: Open3D-Punktwolke mit Segmentfarben und grauen Restpunkten.

Die Ebenen werden iterativ mit Open3D-RANSAC gesucht. Die Inlier jeder Ebene
werden anschließend mit DBSCAN räumlich geteilt, damit getrennte Flächenstücke
nicht zwangsläufig ein gemeinsames Segment bilden.
