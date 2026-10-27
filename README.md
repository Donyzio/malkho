# MalKho

Rapport voor AEX-, AMX- en overige aandelen met technische en fundamentele indicatoren.

- `malkho.py`: het rekenscript. Werkt in Google Colab (toont de tabellen) én op GitHub (maakt alleen bestanden).
- `.github/workflows/dagelijks.yml`: laat GitHub het script elke beursdag om 18:00 (wintertijd) draaien.
- `app/`: de Android-app (React Native met Expo).

Alles is gratis. Hieronder staat het stap voor stap.

---

## Deel A: GitHub laat het script elke beursdag draaien

### Stap 1: account en repository
1. Maak een gratis account op [github.com](https://github.com).
2. Klik rechtsboven op **+** → **New repository**.
3. Naam: `malkho`. Kies **Public** (GitHub Pages is alleen gratis voor openbare repositories; er staan alleen koersgegevens in, niets persoonlijks).
4. Klik op **Create repository**.

### Stap 2: bestanden toevoegen
1. Klik op **uploading an existing file** (of **Add file** → **Upload files**).
2. Sleep `malkho.py`, `requirements.txt` en `README.md` erin en klik op **Commit changes**.
3. De map `.github` is op veel computers verborgen, daarom maak je die met de hand:
   **Add file** → **Create new file**. Typ als naam precies: `.github/workflows/dagelijks.yml`
   Plak de inhoud van het bestand `dagelijks.yml` erin en klik op **Commit changes**.

### Stap 3: website aanzetten
1. Ga naar **Settings** → **Pages** (in het menu links).
2. Kies bij **Source**: **GitHub Actions**.

### Stap 4: de eerste keer draaien
1. Ga naar het tabblad **Actions**. Klik eventueel op de groene knop om workflows toe te staan.
2. Klik links op **MalKho dagelijks** → rechts **Run workflow** → **Run workflow**.
3. Na een paar minuten verschijnt een groen vinkje. Je dashboard staat dan op
   `https://JOUW-GEBRUIKERSNAAM.github.io/malkho/`
   en de data voor de app op
   `https://JOUW-GEBRUIKERSNAAM.github.io/malkho/data.json`

Vanaf nu draait het vanzelf op werkdagen. Gaat er iets mis, dan stuurt GitHub je een e-mail.

Goed om te weten:
- GitHub start geplande taken soms een kwartier of langer later dan de ingestelde tijd.
- Als er 60 dagen niets aan de repository verandert, zet GitHub de dagelijkse taak uit. Je krijgt dan een e-mail met een knop om hem weer aan te zetten.
- Tickers aanpassen doe je in `malkho.py` (bovenaan, bij `INDICES`): open het bestand op GitHub, klik op het potloodje, pas aan en klik op **Commit changes**.

---

## Deel B: de app op je Android-telefoon

### Stap 1: eenmalig installeren
1. Installeer **Node.js** (de LTS-versie) van [nodejs.org](https://nodejs.org).
2. Installeer de app **Expo Go** uit de Google Play Store op je telefoon.

### Stap 2: het app-project maken
Open een terminal (Windows: "Opdrachtprompt"; Mac: "Terminal") en typ deze regels één voor één:

```
npx create-expo-app@latest malkho-app --template blank
cd malkho-app
npx expo install react-native-svg react-native-pager-view react-native-safe-area-context
```

### Stap 3: de MalKho-bestanden erin zetten
1. Vervang `App.js` in de map `malkho-app` door `app/App.js` uit deze download.
2. Kopieer de map `app/src` naar `malkho-app/src`.
3. Open `malkho-app/src/config.js` en vervang `JOUW-GEBRUIKERSNAAM` door je GitHub-gebruikersnaam.

### Stap 4: starten
Typ in de terminal (in de map `malkho-app`):

```
npx expo start
```

Er verschijnt een QR-code. Open **Expo Go** op je telefoon en scan die code. Je telefoon en computer moeten op hetzelfde wifi-netwerk zitten.

In de app:
- swipe tussen **Koersen**, **AEX**, **AMX**, **Overig** en **Toelichting** (of tik op de tabs);
- tik op een aandeel voor de grafiek (week, maand, jaar) en alle indicatoren;
- trek een lijst naar beneden om te verversen.

Later kan de app ook als los installeerbaar bestand (APK) worden gemaakt, zodat je geen computer meer nodig hebt.
