# Ergebnisse des Prototyps „Sichtbarkeitsbewusster Zwilling"

## Worum geht es?

Ein Laserscanner liefert eine Punktwolke: Millionen Punkte auf den Oberflächen, die er
gesehen hat. Wo keine Punkte sind, kann das zwei Gründe haben:

1. **Dort ist wirklich nichts** (Luft).
2. **Der Scanner hat dort nicht hingesehen**, weil etwas im Weg war (Schatten).

Die Punktwolke allein unterscheidet diese beiden Fälle nicht. Für die Planung von
Installationen ist das gefährlich: Ein Planer könnte ein Bauteil in einen Bereich setzen, der
nur *scheinbar* leer ist.

Der Prototyp teilt den Raum deshalb in kleine Würfel (Voxel, 5 cm) und markiert jeden als

- **frei** – ein Laserstrahl ist hindurchgegangen,
- **belegt** – ein Laserstrahl hat dort etwas getroffen,
- **unbekannt** – kein Strahl ist dort angekommen.

## Das Experiment

Ein simulierter Technikraum (6 × 4 × 3 m) mit einem Gerät, einem Deckenbalken (Unterzug) und
einem Rohr unter der Decke. Direkt hinter dem Rohr verläuft eine **Kabeltrasse, die von den
drei Scannerpositionen aus nicht zu sehen ist**, weil das Rohr sie verdeckt.

Geprüft wird, ob Installationsmodule zwischen Rohr und Decke passen. Es gibt 102
Kandidaten: zwei Modulgrößen (flach und hoch) an vielen Positionen entlang des Rohrs. Weil die
Szene simuliert ist, kennen wir die Wahrheit: 83 Kandidaten passen tatsächlich, 19 nicht.

Drei Prüfverfahren treten gegeneinander an:

| Verfahren | Idee |
|---|---|
| **Nominal** | Nur das prüfen, was aus den Punkten erkannt wurde. Was nicht gesehen wurde, gilt als frei. |
| **Fester Puffer** | Wie Nominal, aber alle erkannten Objekte pauschal um 5 cm vergrößern („sicherheitshalber"). |
| **Unsicherheitsmodell** | Nutzt frei/belegt/unbekannt. Liegt zu viel Unbekanntes im Modul oder ist die Rohrgröße zu ungenau bekannt, lautet das Urteil **„unsicher"** statt eines falschen Ja/Nein. |

## Ergebnis 1: Nur das Unsicherheitsmodell macht keine gefährlichen Fehler

| Verfahren | passt | passt nicht | unsicher | **gefährlich falsch** | **unnötig abgelehnt** |
|---|---|---|---|---|---|
| Wahrheit | 83 | 19 | – | – | – |
| Nominal | 90 | 12 | 0 | **7** | 0 |
| Fester Puffer | 42 | 60 | 0 | 0 | **41** |
| Unsicherheitsmodell | 60 | 12 | 30 | **0** | **0** |

- **Gefährlich falsch** heißt: Das Verfahren sagt „passt", in Wirklichkeit kollidiert das
  Modul. Auf der Baustelle wäre das ein Fehler, der teuer wird.
- **Unnötig abgelehnt** heißt: Das Verfahren sagt „passt nicht", obwohl Platz wäre. Dieser Platz ist
  verschenkt.

So lassen sich die Zahlen lesen:

- **Nominal** übersieht die versteckte Kabeltrasse vollständig und erklärt 7 Module für
  passend, die mit ihr kollidieren würden.
- **Der feste Puffer** vermeidet zwar diese Fehler, verwirft aber fast die Hälfte aller
  Plätze (41), die eigentlich gut wären. Pauschale Sicherheitszuschläge sind teuer.
- **Das Unsicherheitsmodell** liegt bei allen 72 Fällen, die es entscheidet, richtig. Bei 30
  Fällen sagt es ehrlich „Ich weiß es nicht", und zwar genau dort, wo das Rohr die Sicht
  verdeckt oder die Rohrgröße zu ungenau bekannt ist.

## Ergebnis 2: Die Empfehlung für einen Nachscan ist zielgerichtet

Bei „unsicher" stellt sich die Frage: **Wo sollte man noch einmal scannen?** Der Prototyp
bewertet drei mögliche zusätzliche Scannerpositionen, ohne deren Daten vorher zu kennen. Er
berechnet nur aus dem aktuellen Modell, welche Position am meisten der *unsicheren* Bereiche
einsehen würde.

- Empfohlen wird **Station S3**, die von der anderen Seite unter das Rohr blickt.
- Wird S3 tatsächlich hinzugefügt, sind **alle 30 unsicheren Fälle geklärt**. Danach stimmt das
  Ergebnis zu 100 % mit der Wahrheit überein, und die Kabeltrasse wird erkannt.
- Die anderen beiden Positionen hätten je 29 der 30 Fälle geklärt.

Ehrlich gesagt: In dieser kleinen Szene ist S3 für jedes vernünftige Kriterium die beste
Wahl. Auch eine Strategie, die einfach „möglichst viel Unbekanntes" sehen will, wählt S3.
Den Vorteil der aufgabenbezogenen Empfehlung zeigt das Experiment also noch nicht. Dafür
braucht es eine Szene mit mehreren verdeckten Bereichen.

## Ergebnis 3: Die Rohrgröße ist ungenauer, als die Statistik behauptet

Das Rohr hat in Wirklichkeit 114 mm Durchmesser. Aus den Punkten werden **112,8 mm** geschätzt.
Die Scanner sehen nur gut die Hälfte des Rohrumfangs (56 %), und das Messrauschen verzerrt die
Schätzung dann leicht nach unten.

Das übliche statistische Verfahren (Bootstrap) gibt einen 95-%-Bereich von 112,2 bis 113,6 mm
an. **Der wahre Wert liegt außerhalb.** Das Verfahren misst nur das Zufallsrauschen und nicht diese
systematische Verzerrung. Der Prototyp schlägt deshalb einen Zuschlag auf, der umso größer ist,
je weniger vom Rohr gesehen wurde.

**Lehre:** Unsicherheitsangaben aus Teilansichten können zu optimistisch sein.

## Grenzen

- **Die Würfelgröße ist entscheidend.** Mit 10-cm-Würfeln statt 5 cm macht auch das
  Unsicherheitsmodell 6 gefährliche Fehler: Ein Würfel, der die dünne Kabeltrasse nur zum Teil
  enthält, wird von vorbeistreifenden Strahlen als „frei" markiert. Die Würfel müssen also
  deutlich kleiner sein als die kleinsten versteckten Objekte, die man finden will.
- **Die Rohr-Fälle sind knapp.** Das hohe Modul hat nur 1 mm Luft. Mit einem anderen
  Zufallsstartwert verschwinden die 15 Fälle, die wegen der Rohrgröße unsicher sind.
- **Vereinfachungen:** Die Szene ist synthetisch. Die Zuordnung „welcher Punkt gehört zu
  welchem Objekt" ist aus der Simulation bekannt (in echten Daten müsste man sie erst
  bestimmen), und das Rohr wird als achsparallel angenommen.

## Fazit in einem Satz

Wer in einem Scan-Modell zwischen „frei" und „nicht gesehen" unterscheidet, vermeidet im
Experiment alle gefährlichen Fehlplanungen, ohne wie ein pauschaler Puffer massenhaft Platz zu
verschenken, und kann gezielt sagen, wo nachgescannt werden muss.
