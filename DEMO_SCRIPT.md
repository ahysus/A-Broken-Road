# Demo script (about 5 minutes)

Start the server first (`bash run_mac.sh` or `run_windows.bat`) and open http://127.0.0.1:8000.
Click **Reopen all roads** before you begin.

## 1. What the professor is looking at (30 seconds)
> "This is Barangay Guisad Central and Guisad Surong, inside the dashed line. The roads come from
> OpenStreetMap. Roads outside Guisad are faint because they are only used to reach hospitals and
> fire stations outside the barangay. The green dots are demo locations, not verified puroks yet,
> and the banner at the top says all closures are simulated."

## 2. A normal route (1 minute)
1. Leave **Clicking the map will** on *Set the starting point*.
2. Under **Go to**, choose **Baguio General Hospital and Medical Center (BGH)**.
3. Click a spot inside Guisad Surong. A blue route appears.
4. Change **Travel mode** to *Walking*, then back to *Vehicle*.
> "There are two graphs from the same data: one for rescue vehicles, one for people on foot.
> Walkers can also use footpaths and stairs."

## 3. An officer reports a closure (1 minute)
1. Switch to *Close or reopen a road*.
2. Zoom in on the blue route. Hover until a road turns **pink**, then click it. It turns **red**.
3. The new route appears in blue, and the old route shows in orange.
> "An officer reports a blocked road by clicking it. D* Lite then updates the route. It does not
> start over. It only repairs the part of its earlier search that the closure affected. Dijkstra
> still gives the orange 'before' route, which we use to measure the added distance and time."
4. Click the red road again to reopen it.

## 4. A purok gets cut off (1 minute)
1. Switch back to *Set the starting point*.
2. Under **Demo closure**, choose **A: vehicles cut off, walking route remains**.
3. Read the message: no vehicle route, but a walking route exists. Some dots turn **red**.
> "Red dots are locations that can no longer reach any destination. This is the isolation check,
> our first research question. Here a rescue vehicle cannot get in, but people can still walk out."
4. Change **Travel mode** to *Walking* to show the walking route.

## 5. Fully cut off (30 seconds)
1. Choose **B: cut off for vehicles and on foot**.
> "Here even walking is impossible. The system tells the officer this location is fully isolated."

## 6. A detour (30 seconds)
1. Change **Travel mode** to *Vehicle*, then choose **C: road closed, detour adds travel time**.
> "One closure near Pinget sends the route on a long detour west. Orange is the old route east."

## 7. What is not real yet (1 minute)
> "The demo locations, the evacuation center and the travel speeds are placeholders. Next we will
> get verified purok locations from the barangay through our communication letter, check the roads
> in a field survey, add HazardHunterPH landslide levels, and run timed tests comparing Dijkstra,
> D* Lite and a combination of both."

Click **Reopen all roads** when done.

---

## Likely questions

**Is the system detecting landslides?**
No. An officer reports a closed road. The system works out who is cut off and the new route.

**Why D* Lite and not just Dijkstra?**
Dijkstra searches the whole graph again after every change. D* Lite reuses its earlier search and
only repairs what a new closure affected, which suits closures reported one after another.

**Is D* Lite faster here?**
In quick checks it was usually a little faster, but not always, because Guisad's network is small.
Measuring this properly is planned for the next phase, comparing Dijkstra only, D* Lite only, and both.

**How do you know D* Lite's route is correct?**
Automated tests compare it with Dijkstra after many random closures. The route times always matched.

**Why is the evacuation center labeled DEMO?**
We have no verified evacuation center data yet. It is a placeholder that we will replace.

**Why do some roads not have names?**
They have no name in OpenStreetMap. The field survey will check them.

**Why do routes stop a little short of the building?**
Each destination connects to the nearest road junction. The field survey will confirm real entrances.

**Why can I not start outside Guisad?**
Starting points stand for puroks, and the study area is Guisad Central and Guisad Surong.

**Where is landslide susceptibility?**
Not in the prototype yet. HazardHunterPH levels will be added as part of the methodology.

**What if there is no internet?**
Everything still works. Only the background street map needs internet.

**Where do the travel times come from?**
Assumed speeds: 20 km/h for vehicles, 4 km/h on foot. Slope and real speeds come later.
