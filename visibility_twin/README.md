# Sichtbarkeitsbewusster Zwilling – Mini-Prototyp

**Idee:** Eine Punktwolke unterscheidet nicht zwischen „hier ist Luft" und „hier hat der Scanner
nicht hingesehen". Per Ray-Casting von den Scannerpositionen wird jeder Voxel als
frei / belegt / unbekannt markiert. Ein Checker beurteilt Modulplatzierungen zwischen Rohr und
Decke dann als *passt / passt nicht / unsicher*. Aus den unsicheren Fällen folgt eine
aufgabenbezogene Nachscan-Empfehlung (Next-Best-View). Alles ist synthetisch: Die Wahrheit ist
bekannt, deshalb lassen sich Fehlurteile zählen.

## Start

```bash
conda env create -f environment.yml      # einmalig: numpy, plotly, pytest
conda activate visibility-twin
python run.py                            # ≈ 12 s, schreibt out/viewer_3d.html und out/slices.html
python run.py --used S0,S1,S2 --holdout S3,S4,S5 --voxel 0.05 --res 0.5 --seed 0   # alle Optionen
python -m pytest tests                   # 4 Sanity-Tests
```

Alle Parameter stehen in `config.py`.

## Ablauf (`run.py`)

scannen (`scan.py`, alle 6 Stationen) → Carving pro Station (`voxels.py`) → Zwilling aus den
genutzten Stationen: Gitter + Fits (`fit.py`) + Checker (`checker.py`) → Kennzahlentabelle →
NBV-Vorhersage nur aus dem aktuellen Gitter (`nbv.py`) → Evaluation: gewählte Station mit ihren
echten Scandaten hinzufügen und alles neu berechnen → HTML.

Die Objekt-ID pro Punkt ist eine **Orakel-Segmentierung** aus der Simulation. In echten Daten
müsste sie ersetzt werden.

## Worauf man im Viewer achten sollte

**`out/slices.html`** (y-z-Schnitt, Schieberegler über x; oben vorher, unten nachher)
- Bei x ≈ 2 m (Standard): Der **orange Keil** schräg hinter und über dem Rohr ist der Schatten
  des Rohrs von S0–S2 aus. Darin liegt die schwarz umrandete Kabeltrasse, ohne einen einzigen
  Punkt. Für eine reine Punktwolke existiert sie nicht.
- Der rote Kreis ist der Rohrfit, die gepunkteten Kreise sind das kleinste und größte plausible Rohr.
- Unten (mit S3 von der anderen Seite) verschwindet der Keil, und die Trasse wird zu belegten Voxeln.
- Bei x ≈ 2.9 m schneidet man den Unterzug, bei x > 4 m ist der Schatten leer (Rohr ja, Trasse nein).

**`out/viewer_3d.html`** (drehbar; Dropdown oben links: Vorher/Nachher; Legende schaltet Ebenen)
- Orange Voxel = unbekannt im Installationsbereich (z > 2.3 m), dunkle Voxel = belegt.
- Magenta Drahtgitter = die versteckte Trasse (Wahrheit). Sie liegt genau im unbekannten Volumen.
- Module: grün = passt, orange = unsicher, rot = passt nicht (Unsicherheitsmodell).
  **Hover** über ein Modul zeigt die Begründung und das wahre Urteil.
- Scanpunkte sind anfangs ausgeblendet (Boden und Wände verdecken sonst alles). Sie lassen sich über die Legende einblenden.
- Die empfohlene Station ist als magenta Raute markiert.

## Ergebnis mit den Standardparametern (Seed 0)

| Variante | passt | passt nicht | unsicher | falsch-passt | falsch-passt-nicht |
|---|---|---|---|---|---|
| Wahrheit | 83 | 19 | – | – | – |
| Nominal (nur Fits) | 90 | 12 | 0 | **7** | 0 |
| Fester Puffer 5 cm | 42 | 60 | 0 | 0 | **41** |
| Unsicherheitsmodell | 60 | 12 | 30 | **0** | 0 |
| Unsicherheitsmodell + S3 | 83 | 19 | 0 | 0 | 0 |

- Die 7 falsch-passt von Nominal sind die hohen Module über der unentdeckten Trasse.
- 15 der 30 unsicheren Fälle liegen im Rohrschatten (y = 0.85), die anderen 15 kollidieren nur mit dem
  größten plausiblen Rohr (y = 1.0, 1 mm Luft).
- NBV: Aufgabe und Abdeckung wählen beide S3, und S3 klärt alle 30 Fälle. S4 und S5 klären je 29.

## Anpassungen gegenüber der Vorgabe (mit Begründung)

1. **Kabeltrasse** jetzt bei y 0.74–0.84, z 2.675–2.725 statt y 0.75–0.95, z 2.78–2.86. Von
   Stationen auf 1.5 m Höhe bei y ≈ 3 fällt der Rohrschatten mit ≈ 29° Steigung **schräg** nach
   −y/oben und ist nur ≈ 13 cm hoch. Die ursprüngliche Trasse läge über dem Schatten und wäre
   sichtbar gewesen. Ihre +y-Kante liegt außerdem bewusst ≥ 1.5 cm vor der Clearance-Zone der
   Module bei y = 1.0, damit Rauschen der Trassenpunkte dort keine Fehlurteile erzeugt.
2. **Systematischer Zuschlag aufs Rohr** (`pipe_sys_margin · (1 − gesehener Umfang)`). Das
   richtungsabhängige Entfernungsrauschen erzeugt bei Teilansicht einen Bias von ≈ −0.6 mm im
   Radius (Ø 112.8 statt 114 mm). Das Bootstrap-95-%-Intervall [112.2, 113.6] mm erfasst nur die
   Streuung und **enthält den wahren Wert nicht**. Ohne Rauschen ist der Fit exakt.
3. **Hohes Modul** endet 1 mm über Rohr + Clearance (h = 322 mm), sonst greift die
   Durchmesserunsicherheit nicht.
4. Elevationsbereich −60° … 90° (Totkegel unter dem Scanner). Voxeltests nutzen die Voxel, deren
   Mittelpunkt im Modul liegt; Decke und Wände (äußerste Voxelschicht) sind ausgenommen.

## Bekannte Grenzen (Stoff für die Diskussion)

- **Teilvoxel werden zu optimistisch frei geschnitzt.** Streift ein Strahl einen Voxel, der ein
  dünnes Objekt nur teilweise enthält, wird der Voxel FREE. Bei `--voxel 0.1` liefert das
  Unsicherheitsmodell dadurch 6 falsch-passt. Die Voxelgröße muss also deutlich kleiner sein als
  die kleinsten relevanten versteckten Objekte.
- Die Rohr-Fälle hängen am Millimeter. Mit `--seed 1` verschwinden die 15 „größtes plausibles
  Rohr"-Fälle. Das Ergebnis ist knapp und nicht robust.
- Aufgabe und Abdeckung unterscheiden sich in dieser kleinen Szene kaum; S3 ist für beides
  offensichtlich gut. Für einen echten Vergleich braucht man mehrere Verdeckungsquellen bzw. mehr
  Kandidatenstationen.
- Segmentierung ist ein Orakel; Rohrachse ∥ x wird angenommen; die Boxen sind reine AABBs der
  Punkte und durch das Rauschen um ≈ 1 cm aufgebläht.
