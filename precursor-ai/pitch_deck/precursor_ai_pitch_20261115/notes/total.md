# 01_title

We are PRECURSOR AI. Our idea is simple: use NASA's radar satellite to look for the slow ground movement that comes before a landslide, so we can see landslides before they happen, from space. We built it for the NASA Space Apps Challenge, Dancing with the SARs.

---

# 02_challenge

Here is the problem. The signal exists, but almost nobody can reach it. Landslides often show weak warning signs first: slow ground creep, and heavy rain on saturated soil. Most hillsides have no ground sensors, so that movement goes unseen. And radar satellite data does exist, but it is huge and technical, so decision makers rarely use it.

---

# 03_solution

So we built one platform that turns NASA radar and environmental data into a landslide early-warning map for any area. You pick an area on the map, and we do the data work. The platform finds, downloads and checks the NASA data. It measures ground movement with InSAR. Then it combines that movement with terrain, rain, soil moisture and landslide history. The last step is the risk estimate. That part is still a placeholder, and we will fill it in before the pitch.

---

# 04_how_it_works

Here is how it works. NISAR sees the ground move, and terrain and rain tell us where and when that movement matters. First we acquire NISAR, elevation, rainfall, soil moisture and landslide history. Then InSAR turns two radar passes into ground displacement. Every layer is aligned to one common grid, with its sources recorded. We analyze movement over time, slope, aspect and rainfall build-up. Risk and explain is the next stage, still a placeholder to fill in before the pitch. And everything lands on a dashboard, an interactive map with charts.

---

# 05_space_data

All of this is built on NASA data. NISAR, the L-band radar, gives us ground displacement with a twelve day repeat. NASADEM gives elevation, slope and aspect. GPM IMERG gives rainfall, and SMAP gives soil moisture. The NASA Global Landslide Catalog shows us where landslides have already happened. The line about the area covered, the number of scenes and the date range is a placeholder, and we will replace it with the real figures.

---

# 06_impact

What does this add up to? Open NASA data in, one usable map out. The first two points, the result for our test area and the accuracy or validation, are placeholders that we will fill in with real numbers before the pitch. The third one is already true: any region NISAR covers can reuse it.

---

# 07_next_steps

Our plan is to prove it where the data is lighter. Phase A is the United States, with lighter data and a well-documented landslide history. Phase B is Azerbaijan. That means terabytes of raw radar data, so it comes after the pipeline is proven. The third step is a placeholder for now: a live public dashboard and the later model upgrades.

---

# 08_team

We are a small team covering engineering, design and AI. Kanan Salmanli is our full stack developer. Sema Abdullazade is our UI and UX designer. Intiqam is our frontend designer. And Farid Gahramanov is our AI engineer.

---

# 09_thank_you

Thank you. Scan the code to try the app.
