"""MalKho: overzicht van aandelen met technische en fundamentele indicatoren.

Versie 1.3 (27-10-2026, zonder backtest)
  - waardering t.o.v. de eigen geschiedenis: K/W, koers/boekwaarde, EV/EBITDA en
    dividendrendement vergeleken met eerdere jaren; kolom "Waardering hist."
Versie 1.1 (27-10-2026)
  - grafieken in de app: YTD, 1D, 1W, 1M, 3M, 6M, 1Y, 3Y, 5Y en Max
  - koersblok in de app: slotkoers, dag hoog/laag, 12 maanden hoog/laag, YTD
Versie 1.0 (27-10-2026)
  - draait ook op GitHub en maakt het dashboard en data.json voor de app
"""

MALKHO_VERSIE = "1.3"
MALKHO_DATUM = "27-10-2026"

import json
import logging
import math
import os
import sys
import time
from typing import NamedTuple

import numpy as np
import pandas as pd
import yfinance as yf

# In Colab worden de tabellen getoond; op GitHub (zonder notebook) worden alleen bestanden gemaakt.
try:
    from IPython import get_ipython
    from IPython.display import Markdown, display
    IN_NOTEBOOK = get_ipython() is not None
except ImportError:
    IN_NOTEBOOK = False

if not IN_NOTEBOOK:
    class _GeenWeergave:
        """Doet niets: vervangt de notebook-weergave buiten Colab."""
        def update(self, *args, **kwargs) -> None:
            pass

    def display(*args, **kwargs) -> _GeenWeergave:  # noqa: F811
        return _GeenWeergave()

    def Markdown(tekst: str) -> str:  # noqa: F811
        return tekst

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s", force=True)
log = logging.getLogger("malkho")


# =============================================================================
# 1. CONFIGURATIE (hier pas je dingen aan, de rest hoeft niet te veranderen)
# =============================================================================

INDICES: dict[str, dict[str, str]] = {
    "AEX": {
        "ABN AMRO Bank": "ABN.AS", "Aalberts": "AALB.AS", "Adyen": "ADYEN.AS", "Aegon": "AGN.AS",
        "Ahold Delhaize": "AD.AS", "AkzoNobel": "AKZA.AS", "ArcelorMittal": "MT.AS",
        "ASM International": "ASM.AS", "ASML Holding": "ASML.AS", "ASR Nederland": "ASRNL.AS",
        "BESI": "BESI.AS", "DSM-Firmenich": "DSFIR.AS", "Heineken": "HEIA.AS", "IMCD": "IMCD.AS",
        "ING Groep": "INGA.AS", "InPost": "INPST.AS", "NN Group": "NN.AS", "Philips": "PHIA.AS",
        "Prosus": "PRX.AS", "RELX": "REN.AS", "SBM Offshore": "SBMO.AS", "Shell": "SHELL.AS",
        "Unilever": "UNA.AS", "Universal Music Group": "UMG.AS", "WDP": "WDP.BR",
        "Wolters Kluwer": "WKL.AS",
    },
    "AMX": {
        # Vul hier de AMX-fondsen in, in het formaat "Naam": "CODE.AS",
        # De officiële lijst staat op live.euronext.com (zoek op "AMX", kies "Samenstelling").
        "Air France-KLM": "AF.PA", "Allfunds Group": "ALLFG.AS", "AMG Critical Materials": "AMG.AS", "Aperam": "APAM.AS",
        "Arcadis": "ARCAD.AS", "BAM Groep": "BAMNB.AS", "Basic-Fit": "BFIT.AS", "CSG": "CSG.AS",
        "CTP": "CTPNV.AS", "Fugro": "FUR.AS", "PostNL": "PNL.AS", "Eurocommercial Properties": "ECMPA.AS",
        "Randstad": "RAND.AS", "SBM Offshore": "SBMO.AS", "Signify": "LIGHT.AS", "TKH Group": "TWEKA.AS",
        "Vopak": "VPK.AS", "WDP": "WDP.BR"
    },
    "Overig": {
        # Fondsen die je volgt maar die niet in de AEX of AMX zitten
        "BAM Groep": "BAMNB.AS", "Nike": "NKE", "Shurgard": "SHUR.BR",
        "Van Lanschot Kempen": "VLK.AS", "Volkswagen": "VOW3.DE", "Wereldhave": "WHA.AS",
    },
}

# Handmatige cijfers per aandeel (euro per aandeel). None = Yahoo-benadering gebruiken.
# Vastgoedfondsen (sector 'Real Estate' bij Yahoo) worden sowieso als vastgoed behandeld.
HANDMATIGE_CIJFERS: dict[str, dict[str, float | None]] = {
    "WDP.BR": {"affo": None, "nav": None},
}

# Banken en verzekeraars: EBITDA, FCF-rendement en Net Debt/EBITDA zijn daar niet zinvol.
GEEN_EBITDA: set[str] = {"ABN.AS", "AGN.AS", "ASRNL.AS", "INGA.AS", "NN.AS"}

SECTOR_NL: dict[str, str] = {
    "Technology": "Technologie",
    "Financial Services": "Financiële diensten",
    "Energy": "Energie",
    "Consumer Defensive": "Defensieve consumptie",
    "Consumer Cyclical": "Cyclische consumptie",
    "Healthcare": "Gezondheidszorg",
    "Industrials": "Industrie",
    "Basic Materials": "Basismaterialen",
    "Real Estate": "Vastgoed",
    "Communication Services": "Communicatie",
    "Utilities": "Nutsbedrijven",
}

# Parameters technische indicatoren
HISTORIE_PERIODE = "max"       # alle koersgeschiedenis (voor de grafieken 3Y, 5Y en Max)
RSI_PERIODE = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
RSI_OMKEER_DAGEN = 5           # hoeveel dagen terug mag de RSI onder 30 zijn geweest
SMA_PERIODE = 200
MACD_SNEL, MACD_TRAAG, MACD_SIGNAAL = 12, 26, 9
BOLLINGER_PERIODE = 20
BOLLINGER_AANTAL_SD = 2
BOLLINGER_LAAG = 20            # %B onder dit niveau: koers dicht bij of onder de onderband
BOLLINGER_HOOG = 80            # %B boven dit niveau: koers dicht bij of boven de bovenband
VOLUME_PERIODE = 20
VOLUME_DREMPEL = 1.0           # relatief volume boven 1 = boven het gemiddelde
HANDELSDAGEN_JAAR = 252        # aantal beursdagen in 52 weken
HOOG_NABIJ = -5                # minder dan 5% onder het 52-weeks hoog = bij de top (groen)
HOOG_VER = -30                 # meer dan 30% onder het 52-weeks hoog = zware daling (rood)

# Waarden van de kolom RSI-omkeer
FASE_OMKEER = "ja"
FASE_DALEND = "nog dalend"
FASE_GEEN = "nee"

PAUZE_TUSSEN_AANVRAGEN = 0.5   # seconden, om Yahoo niet te overbelasten
AANTAL_TOP = 5                 # aantal grootste stijgers en dalers per index in de koerstabel
VERVERS_SECONDEN = 60          # pauze tussen twee verversingen van de koerstabel
MAX_VERVERSINGEN = 30          # na dit aantal keer stopt het verversen (30 x 1 min = 30 min)
LIVE_PAUZE = 0.2               # seconden tussen de aanvragen per aandeel

# Dashboard: een opgemaakte webpagina die je op je telefoon of computer kunt openen
DASHBOARD_MAKEN = True
DASHBOARD_MAP_DRIVE = "/content/drive/MyDrive/MalKho"   # map in je Google Drive (Colab)
DASHBOARD_MAP_LOKAAL = "."                              # buiten Colab (later: GitHub)
DASHBOARD_BESTAND = "malkho-dashboard.html"

# Databestand voor de app (koersen, indicatoren, kleuren en koershistorie voor grafieken)
DATA_BESTAND = "data.json"
HISTORIE_DAGEN_APP = 400       # kalenderdagen dagkoersen voor de app (genoeg voor 1Y en YTD)
HISTORIE_MAP = "historie"      # submap met per aandeel een bestand met koersgeschiedenis

# Op GitHub zet het workflow-bestand MALKHO_UITVOER; dan komt alles in die map
# (het dashboard als index.html, zodat het de startpagina van de website wordt).
UITVOER_MAP = os.environ.get("MALKHO_UITVOER")

# Waardering t.o.v. de eigen geschiedenis
WAARDERING_MAKEN = True
WAARDERING_VERTRAGING = 90        # jaarcijfers gelden pas zoveel dagen na het boekjaareinde als bekend
WAARDERING_JAREN_DIVIDEND = 10    # dividendrendement vergelijken met de laatste 10 jaar
WAARDERING_MIN_DAGEN = 500        # minstens ongeveer 2 jaar geschiedenis nodig
WAARDERING_GOEDKOOP = 80          # goedkoopte-score 80+ = goedkoop, 20 of lager = duur


class Drempels(NamedTuple):
    """Kleurgrenzen in procenten. Waarden tussen de zones blijven ongekleurd."""
    rood_onder: float
    groen_van: float
    groen_tot: float
    donker_boven: float


ROE_NORMEN: dict[str, Drempels] = {
    "Technologie":           Drempels(15, 15, 25, 25),
    "Financiële diensten":   Drempels(8, 8, 12, 14),
    "Defensieve consumptie": Drempels(12, 12, 20, 22),
    "Cyclische consumptie":  Drempels(12, 12, 20, 22),
    "Vastgoed":              Drempels(5, 6, 10, 14),
    "Industrie":             Drempels(10, 12, 18, 20),
    "Basismaterialen":       Drempels(10, 12, 18, 20),
}

FCF_STANDAARD = Drempels(2, 4, 5, 7)  # "Brede markt", voor branches zonder eigen norm
FCF_NORMEN: dict[str, Drempels] = {
    "Energie":               Drempels(6, 8, 15, 15),
    "Defensieve consumptie": Drempels(4, 6, 12, 12),
    "Cyclische consumptie":  Drempels(4, 6, 12, 12),
    "Nutsbedrijven":         Drempels(3, 4, 6, 7),
    "Vastgoed":              Drempels(3, 4, 6, 7),
    "Gezondheidszorg":       Drempels(1, 3, 7, 8),
    "Technologie":           Drempels(0, 1, 3, 5),
}

GROEN = "background-color: #c6efce; color: #006100"
GEEL = "background-color: #ffeb9c; color: #9c5700"
ROOD = "background-color: #ffc7ce; color: #9c0006"
DONKERGROEN = "background-color: #2e7d32; color: #ffffff"

# Kolomnamen op één plek, zodat een typfout niet stilletjes een lege kolom geeft.
KOL_BRANCHE = "Branche"
KOL_AANDEEL = "Aandeel"
KOL_TICKER = "Ticker"
KOL_VALUTA = "Valuta"
KOL_INDEX = "Beursindex"
KOL_KOERS = "Koers"
KOL_DAGVERSCHIL = "Verschil vorige dag (%)"
KOL_RSI = "RSI"
KOL_GEM_RSI = "Branche gem. RSI"
KOL_SIGNAAL = "Signaal"
KOL_OMKEER = "RSI-omkeer"
KOL_SMA = "Koers vs 200d gem. (%)"
KOL_MACD = "MACD"
KOL_BOLLINGER = "Bollinger %B"
KOL_VOLUME = "Rel. volume"
KOL_HOOG = "Afstand 52w hoog (%)"
KOL_INSTAP = "Instapsignaal"
KOL_KW = "K/W"
KOL_KW_VERWACHT = "K/W verwacht"
KOL_GEM_KW = "Branche gem. K/W"
KOL_AFFO = "Koers/AFFO"
KOL_NAV = "Koers vs NAV (%)"
KOL_BRON = "Bron AFFO/NAV"
KOL_EBITDA = "EBITDA (mln)"
KOL_ROE = "ROE (%)"
KOL_FCF = "FCF-rendement (%)"
KOL_SCHULD = "Netto schuld/EBITDA"
KOL_DIVIDEND = "Dividend (%)"
KOL_WAARDERING = "Waardering hist."

NUMERIEKE_KOLOMMEN = [KOL_KOERS, KOL_DAGVERSCHIL, KOL_RSI, KOL_SMA, KOL_BOLLINGER, KOL_VOLUME,
                      KOL_HOOG, KOL_KW, KOL_KW_VERWACHT, KOL_AFFO, KOL_NAV, KOL_EBITDA, KOL_ROE, KOL_FCF,
                      KOL_SCHULD, KOL_DIVIDEND]

# Indeling van de kolommen in de tabel
TECHNISCH = [KOL_KOERS, KOL_DAGVERSCHIL, KOL_RSI, KOL_GEM_RSI, KOL_SIGNAAL, KOL_OMKEER,
             KOL_SMA, KOL_MACD, KOL_BOLLINGER, KOL_VOLUME, KOL_HOOG, KOL_INSTAP]
FUNDAMENTEEL = [KOL_KW, KOL_KW_VERWACHT, KOL_GEM_KW, KOL_AFFO, KOL_NAV, KOL_BRON,
                KOL_EBITDA, KOL_ROE, KOL_FCF, KOL_SCHULD, KOL_DIVIDEND, KOL_WAARDERING]
GROEP_TECHNISCH = "Technisch"
GROEP_FUNDAMENTEEL = "Fundamenteel"

TOELICHTING = """
**Toelichting: technische kolommen**

- **Koers**: laatste slotkoers.
- **Verschil vorige dag (%)**: procentuele koersverandering ten opzichte van de slotkoers van de vorige beursdag. Groen bij een stijging, rood bij een daling.
- **RSI**: Relative Strength Index (0 tot 100). Onder 30 is *oversold* (mogelijke instapkans), boven 70 *overbought* (mogelijk risico).
- **Branche gem. RSI**: gemiddelde RSI van de aandelen in dezelfde branche.
- **Signaal**: vertaling van de RSI van vandaag: oversold (groen), neutraal (geel), overbought (rood).
- **RSI-omkeer**: *ja* (groen) als de RSI de laatste 5 beursdagen onder 30 kwam en nu weer stijgt: de daling lijkt te stoppen. *Nog dalend* (geel) als de RSI recent onder 30 kwam maar nog niet stijgt. Anders *nee*.
- **Koers vs 200d gem. (%)**: hoeveel procent de koers boven (+) of onder (-) het 200-daags gemiddelde ligt. Boven = intacte opwaartse trend (groen), onder = neerwaartse trend (rood).
- **MACD**: *positief* als het MACD-momentum (12/26 dagen) boven zijn signaallijn (9 dagen) ligt, anders *negatief*.
- **Bollinger %B**: positie van de koers binnen de Bollinger-banden (20 dagen, 2 standaarddeviaties). 0 = onderband, 100 = bovenband. Onder 20 is groen, boven 80 rood.
- **Rel. volume**: volume van de laatste dag gedeeld door het gemiddelde van de 20 dagen ervoor. Boven 1 is groen (meer handel dan normaal).
- **Afstand 52w hoog (%)**: hoeveel procent de slotkoers onder het hoogste slot van de afgelopen 52 weken ligt (0 = op het hoogste punt). Groen als het aandeel minder dan 5% onder de top staat, rood bij meer dan 30% eronder. Gebaseerd op slotkoersen (gecorrigeerd voor dividend en splitsingen), dus het kan iets afwijken van het 52-weeks hoog op beurssites.
- **Instapsignaal**: *ja* (donkergroen) als **alle drie** gelden: RSI-omkeer *ja*, koers boven het 200-daags gemiddelde en relatief volume boven 1. *Bijna* (geel) als de RSI recent oversold was (omkeer of nog dalend) en minstens één van de twee andere voorwaarden geldt. *Onbekend* bij te weinig koersgeschiedenis of volumedata.

**Toelichting: fundamentele kolommen**

- **K/W**: koers-winstverhouding: de huidige koers gedeeld door de winst per aandeel van de afgelopen 12 maanden. Het is dus het aantal jaren winst dat je voor het aandeel betaalt; lager is goedkoper. Bij verlies of ontbrekende gegevens staat een streepje. Niet gebruikt bij vastgoed.
- **K/W verwacht**: de huidige koers gedeeld door de verwachte winst per aandeel (consensus van analisten, volgens Yahoo). Ligt deze lager dan de gewone K/W, dan verwachten analisten winstgroei. Is er geen schatting beschikbaar of is de verwachte winst negatief, dan staat er een streepje. Niet gebruikt bij vastgoed.
- **Koers/AFFO**: koers gedeeld door de gecorrigeerde operationele kasstroom per aandeel (de "K/W" voor vastgoed). Bij de Yahoo-benadering een grove schatting.
- **Koers vs NAV (%)**: hoeveel procent de koers boven (+) of onder (-) de netto vermogenswaarde per aandeel ligt. Negatief is een korting.
- **Bron AFFO/NAV**: laat zien of AFFO en NAV handmatig zijn ingevuld of uit Yahoo zijn benaderd.
- **EBITDA (mln)**: bedrijfsresultaat vóór rente, belasting en afschrijvingen, in de rapportagevaluta. Niet getoond bij banken en verzekeraars.
- **ROE (%)**: rendement op eigen vermogen. Hoger is efficiënter; de kleur hangt af van de branche.
- **FCF-rendement (%)**: vrije kasstroom gedeeld door de beurswaarde. Hoger is aantrekkelijker; de kleur hangt af van de branche.
- **Netto schuld/EBITDA**: in hoeveel jaar de netto schuld uit de EBITDA terugbetaald kan worden. Boven ongeveer 3 à 4 wordt vaak als hoog gezien; negatief betekent meer kas dan schuld.
- **Dividend (%)**: verwacht jaardividend als percentage van de koers (bruto, vóór dividendbelasting).
- **Waardering hist.**: is het aandeel nu goedkoop of duur vergeleken met de eigen geschiedenis? Per branche worden de kengetallen gebruikt die daar passen (bijv. koers/boekwaarde bij banken, EV/EBITDA bij energie). *Goedkoop* (groen) als het aandeel goedkoper is dan in ongeveer 80% van de gemeten periode, *duur* (rood) als het duurder is. Jaarcijfers van Yahoo gaan zo'n 4 à 5 jaar terug, het dividendrendement 10 jaar. Let op: bij cyclische bedrijven kan "goedkoop" ook betekenen dat de winst op een piek staat.
"""


# =============================================================================
# 2. HULPFUNCTIES
# =============================================================================

def als_getal(waarde) -> float | None:
    """Geeft de waarde als float terug, of None als die ontbreekt of geen eindig getal is."""
    try:
        getal = float(waarde)
    except (TypeError, ValueError):
        return None
    return getal if math.isfinite(getal) else None


def valuta_gelijk(info: dict, ontbrekend_ok: bool = False) -> bool:
    """Is de rapportagevaluta gelijk aan de beursvaluta? Zo niet, dan kloppen ratio's niet."""
    rapportage = info.get("financialCurrency")
    if rapportage is None:
        return ontbrekend_ok
    return rapportage == info.get("currency")


# =============================================================================
# 3. BEREKENINGEN: TECHNISCH
# =============================================================================

def haal_marktdata(ticker: str) -> pd.DataFrame:
    """Haalt de koersgeschiedenis op. Kolommen:
    'koers'  slotkoers gecorrigeerd voor dividend (voor de indicatoren),
    'slot'   gewone slotkoers zoals op beurssites (voor grafieken, dag- en 12-maandscijfers),
    'hoog' / 'laag'  hoogste en laagste koers van de dag, 'volume'."""
    data = yf.download(ticker, period=HISTORIE_PERIODE, auto_adjust=False, progress=False)
    if data.empty:
        raise ValueError("geen koersdata gevonden")
    markt = pd.DataFrame({
        "koers": data["Adj Close"].squeeze(),
        "slot": data["Close"].squeeze(),
        "hoog": data["High"].squeeze(),
        "laag": data["Low"].squeeze(),
        "volume": data["Volume"].squeeze(),
    })
    return markt.dropna(subset=["koers"])


def bereken_rsi(koers: pd.Series, periode: int = RSI_PERIODE) -> pd.Series:
    """Relative Strength Index (0 tot 100) volgens de exponentiële methode van Wilder."""
    verschil = koers.diff()
    winst = verschil.clip(lower=0)
    verlies = -verschil.clip(upper=0)
    gem_winst = winst.ewm(alpha=1 / periode, adjust=False).mean()
    gem_verlies = verlies.ewm(alpha=1 / periode, adjust=False).mean()
    return 100 - (100 / (1 + gem_winst / gem_verlies))


def bepaal_signaal(rsi: float) -> str:
    if rsi < RSI_OVERSOLD:
        return "oversold"
    if rsi > RSI_OVERBOUGHT:
        return "overbought"
    return "neutraal"

def bereken_dagverschil(koers: pd.Series) -> float | None:
    """Procentuele koersverandering ten opzichte van de vorige beursdag."""
    if len(koers) < 2:
        return None
    vorige = als_getal(koers.iloc[-2])
    if not vorige:
        return None
    return round((float(koers.iloc[-1]) / vorige - 1) * 100, 2)

def bepaal_rsi_omkeer(rsi: pd.Series) -> str:
    """'ja' als de RSI recent onder 30 kwam en nu stijgt; 'nog dalend' als hij recent onder
    30 kwam maar nog niet stijgt; anders 'nee'."""
    if len(rsi) < 2:
        return FASE_GEEN
    recent_oversold = rsi.tail(RSI_OMKEER_DAGEN).min() < RSI_OVERSOLD
    if not recent_oversold:
        return FASE_GEEN
    return FASE_OMKEER if rsi.iloc[-1] > rsi.iloc[-2] else FASE_DALEND


def bereken_afstand_sma(koers: pd.Series, periode: int = SMA_PERIODE) -> float | None:
    """Procentuele afstand van de koers tot het voortschrijdend gemiddelde."""
    gemiddelde = als_getal(koers.rolling(periode).mean().iloc[-1])
    if not gemiddelde:
        return None  # te weinig koersgeschiedenis
    return round((float(koers.iloc[-1]) / gemiddelde - 1) * 100, 1)


def bereken_afstand_hoog(koers: pd.Series, dagen: int = HANDELSDAGEN_JAAR) -> float | None:
    """Procentuele afstand van de koers tot het hoogste slot van de afgelopen 52 weken."""
    hoogste = als_getal(koers.tail(dagen).max())
    if not hoogste:
        return None
    return round((float(koers.iloc[-1]) / hoogste - 1) * 100, 1)


def bepaal_macd_status(koers: pd.Series) -> str:
    """'positief' als de MACD-lijn boven de signaallijn ligt, anders 'negatief'."""
    macd = (koers.ewm(span=MACD_SNEL, adjust=False).mean()
            - koers.ewm(span=MACD_TRAAG, adjust=False).mean())
    signaallijn = macd.ewm(span=MACD_SIGNAAL, adjust=False).mean()
    return "positief" if macd.iloc[-1] > signaallijn.iloc[-1] else "negatief"


def bereken_bollinger_pct_b(koers: pd.Series) -> float | None:
    """Positie van de koers in de Bollinger-banden: 0 = onderband, 100 = bovenband."""
    gemiddelde = koers.rolling(BOLLINGER_PERIODE).mean()
    spreiding = koers.rolling(BOLLINGER_PERIODE).std()
    onder = gemiddelde - BOLLINGER_AANTAL_SD * spreiding
    breedte = als_getal(2 * BOLLINGER_AANTAL_SD * spreiding.iloc[-1])
    if not breedte:
        return None
    return round((float(koers.iloc[-1]) - onder.iloc[-1]) / breedte * 100, 1)


def bereken_relatief_volume(volume: pd.Series, periode: int = VOLUME_PERIODE) -> float | None:
    """Volume van de laatste dag gedeeld door het gemiddelde van de dagen ervoor."""
    gemiddelde = als_getal(volume.iloc[:-1].tail(periode).mean())
    laatste = als_getal(volume.iloc[-1])
    if not gemiddelde or laatste is None:
        return None
    return round(laatste / gemiddelde, 2)


def bepaal_instapsignaal(omkeer: str, afstand_sma: float | None, rel_volume: float | None) -> str:
    """'ja' als de RSI omkeert, de trend intact is en het volume boven gemiddeld ligt.
    'bijna' als de RSI recent oversold was en minstens één van de twee andere geldt."""
    if afstand_sma is None or rel_volume is None:
        return "onbekend"
    trend_ok = afstand_sma > 0
    volume_ok = rel_volume > VOLUME_DREMPEL
    if omkeer == FASE_OMKEER and trend_ok and volume_ok:
        return "ja"
    if omkeer != FASE_GEEN and (trend_ok or volume_ok):
        return "bijna"
    return "nee"


# =============================================================================
# 4. BEREKENINGEN: FUNDAMENTEEL
# =============================================================================

def bereken_kengetallen(info: dict, ticker: str) -> dict:
    """EBITDA, ROE, FCF-rendement en Net debt/EBITDA uit de Yahoo-gegevens."""
    ebitda = als_getal(info.get("ebitda"))
    roe = als_getal(info.get("returnOnEquity"))
    fcf = als_getal(info.get("freeCashflow"))
    marktwaarde = als_getal(info.get("marketCap"))
    schuld = als_getal(info.get("totalDebt"))
    kas = als_getal(info.get("totalCash"))

    ebitda_mln = fcf_rendement = netto_schuld_ebitda = None
    if ticker not in GEEN_EBITDA:
        if ebitda:
            ebitda_mln = round(ebitda / 1e6)
        if ebitda and ebitda > 0 and schuld is not None and kas is not None:
            netto_schuld_ebitda = round((schuld - kas) / ebitda, 1)
        if fcf is not None and marktwaarde and valuta_gelijk(info):
            fcf_rendement = round(fcf / marktwaarde * 100, 1)

    return {
        KOL_EBITDA: ebitda_mln,
        KOL_ROE: round(roe * 100, 1) if roe is not None else None,
        KOL_FCF: fcf_rendement,
        KOL_SCHULD: netto_schuld_ebitda,
    }


def bereken_dividendrendement(info: dict, koers_nu: float) -> float | None:
    """Verwacht jaardividend per aandeel als percentage van de koers."""
    dividend = als_getal(info.get("dividendRate"))
    if dividend is None:
        dividend = als_getal(info.get("trailingAnnualDividendRate"))
    if dividend is None or koers_nu <= 0:
        return None
    return round(dividend / koers_nu * 100, 1)


def bereken_kw(info: dict, koers_nu: float) -> float | None:
    """K/W = huidige koers / winst per aandeel van de afgelopen 12 maanden.
    Bij een valutaverschil tussen koers en winst gebruiken we de K/W van Yahoo zelf.
    Geen K/W bij verlies of ontbrekende gegevens."""
    winst = als_getal(info.get("trailingEps"))
    if winst is not None and valuta_gelijk(info, ontbrekend_ok=True):
        return round(koers_nu / winst, 1) if winst > 0 else None
    return als_getal(info.get("trailingPE"))  # terugval op Yahoo's eigen berekening

    
def bereken_kw_verwacht(info: dict, koers_nu: float) -> float | None:
    """Verwachte K/W = huidige koers / verwachte winst per aandeel (consensus van analisten).
    Bij een valutaverschil tussen koers en winst gebruiken we Yahoo's eigen verwachte K/W."""
    winst = als_getal(info.get("forwardEps"))
    if winst is not None and valuta_gelijk(info, ontbrekend_ok=True):
        return round(koers_nu / winst, 1) if winst > 0 else None
    return als_getal(info.get("forwardPE"))


def bereken_vastgoed(info: dict, ticker: str, koers_nu: float) -> tuple[float | None, float | None, str]:
    """Koers/AFFO en koers t.o.v. NAV. Handmatige cijfers gaan voor de Yahoo-benadering."""
    handmatig = HANDMATIGE_CIJFERS.get(ticker, {})
    affo_ps = handmatig.get("affo")
    nav_ps = handmatig.get("nav")
    affo_bron = "handmatig" if affo_ps else "-"
    nav_bron = "handmatig" if nav_ps else "-"

    if valuta_gelijk(info, ontbrekend_ok=True):
        if not affo_ps:
            kasstroom = als_getal(info.get("operatingCashflow"))
            aandelen = als_getal(info.get("sharesOutstanding"))
            if kasstroom and aandelen:
                affo_ps = kasstroom / aandelen
                affo_bron = "Yahoo (benadering)"
        if not nav_ps:
            boekwaarde = als_getal(info.get("bookValue"))
            koers_boek = als_getal(info.get("priceToBook"))
            if not boekwaarde and koers_boek:
                boekwaarde = koers_nu / koers_boek
            if boekwaarde:
                nav_ps = boekwaarde
                nav_bron = "Yahoo (benadering)"

    koers_affo = round(koers_nu / affo_ps, 1) if affo_ps and affo_ps > 0 else None
    nav_verschil = round((koers_nu / nav_ps - 1) * 100, 1) if nav_ps and nav_ps > 0 else None
    return koers_affo, nav_verschil, f"AFFO: {affo_bron} | NAV: {nav_bron}"


# =============================================================================
# 4b. WAARDERING TEN OPZICHTE VAN DE EIGEN GESCHIEDENIS
# =============================================================================
#
# Voor elke beursdag in het verleden: koers gedeeld door de jaarcijfers die op die dag al bekend
# waren. Zo ontstaat per aandeel een reeks K/W, koers/boekwaarde, EV/EBITDA en dividendrendement.
# Daarna kijken we waar de huidige waarde in die reeks valt (het percentiel).

# Welke kengetallen passen bij welke branche (de eerste is de belangrijkste)
KG_KW = "K/W"
KG_KB = "Koers/boekwaarde"
KG_EV = "EV/EBITDA"
KG_DIV = "Dividendrendement (%)"

WAARDERING_PER_BRANCHE: dict[str, list[str]] = {
    "Financiële diensten": [KG_KB, KG_DIV],
    "Vastgoed": [KG_DIV, KG_KB],
    "Energie": [KG_EV, KG_KB],
    "Basismaterialen": [KG_EV, KG_KB],
    "Industrie": [KG_EV, KG_KW],
}
WAARDERING_STANDAARD = [KG_KW, KG_EV]


def kies_waarderingskengetallen(branche: str, ticker: str) -> list[str]:
    kengetallen = WAARDERING_PER_BRANCHE.get(branche, WAARDERING_STANDAARD)
    if ticker in GEEN_EBITDA:  # banken en verzekeraars: EV/EBITDA zegt niets
        kengetallen = [k for k in kengetallen if k != KG_EV] or [KG_KB, KG_DIV]
    return kengetallen


def zoek_regel(tabel: pd.DataFrame | None, namen: list[str]) -> pd.Series | None:
    """Eerste regel uit een jaarcijfertabel van Yahoo die bestaat en waarden heeft."""
    if tabel is None or tabel.empty:
        return None
    for naam in namen:
        if naam in tabel.index:
            regel = pd.to_numeric(tabel.loc[naam], errors="coerce").dropna()
            if not regel.empty:
                regel.index = pd.to_datetime(regel.index).tz_localize(None)
                return regel.sort_index()
    return None


def per_dag(jaarwaarden: pd.Series | None, dagen: pd.DatetimeIndex) -> pd.Series:
    """Zet jaarcijfers om naar een dagelijkse reeks: elke dag geldt het laatst gepubliceerde jaar.
    Jaarcijfers worden pas WAARDERING_VERTRAGING dagen na het boekjaareinde als bekend beschouwd."""
    if jaarwaarden is None or jaarwaarden.empty:
        return pd.Series(np.nan, index=dagen)
    bekend = jaarwaarden.copy()
    bekend.index = bekend.index + pd.Timedelta(days=WAARDERING_VERTRAGING)
    bekend = bekend[~bekend.index.duplicated(keep="last")].sort_index()
    return bekend.reindex(bekend.index.union(dagen)).ffill().reindex(dagen)


_WISSELKOERSEN: dict[str, pd.Series | None] = {}


def wisselkoers(van: str, naar: str, dagen: pd.DatetimeIndex) -> pd.Series | None:
    """Wisselkoers per dag (1 'van' = x 'naar'), bijv. USD naar EUR voor Shell."""
    if van == naar:
        return pd.Series(1.0, index=dagen)
    paar = f"{van}{naar}=X"
    if paar not in _WISSELKOERSEN:
        try:
            data = yf.download(paar, period="max", auto_adjust=False, progress=False)
            reeks = data["Close"].squeeze().dropna() if not data.empty else None
            if reeks is not None:
                reeks.index = pd.to_datetime(reeks.index).tz_localize(None)
            _WISSELKOERSEN[paar] = reeks
        except Exception as fout:  # yfinance geeft uiteenlopende fouttypen
            log.warning("Wisselkoers %s mislukt: %s", paar, fout)
            _WISSELKOERSEN[paar] = None
    reeks = _WISSELKOERSEN[paar]
    if reeks is None or reeks.empty:
        return None
    return reeks.reindex(reeks.index.union(dagen)).ffill().reindex(dagen)


def bereken_waarderingsreeksen(aandeel, markt: pd.DataFrame, info: dict) -> dict[str, pd.Series]:
    """Dagelijkse reeksen van K/W, koers/boekwaarde, EV/EBITDA en dividendrendement."""
    slot = markt["slot"].dropna()
    slot.index = pd.to_datetime(slot.index).tz_localize(None)
    dagen = slot.index
    reeksen: dict[str, pd.Series] = {}

    # Dividendrendement: dividenden van de afgelopen 12 maanden gedeeld door de koers.
    # Dividenden staan bij Yahoo in de handelsvaluta, dus geen omrekening nodig.
    try:
        dividenden = aandeel.dividends
    except Exception:  # yfinance geeft uiteenlopende fouttypen
        dividenden = None
    if dividenden is not None and len(dividenden) > 0:
        dividenden = dividenden.copy()
        dividenden.index = pd.to_datetime(dividenden.index).tz_localize(None).normalize()
        per_dag_uitgekeerd = dividenden.groupby(level=0).sum()
        dagelijks = per_dag_uitgekeerd.reindex(per_dag_uitgekeerd.index.union(dagen), fill_value=0)
        twaalf_maanden = dagelijks.rolling("365D").sum().reindex(dagen)
        rendement = twaalf_maanden / slot * 100
        # pas meten vanaf een jaar na het eerste dividend, anders is het 12-maandstotaal te laag
        rendement[dagen < per_dag_uitgekeerd.index.min() + pd.Timedelta(days=365)] = np.nan
        reeksen[KG_DIV] = rendement

    # Kengetallen op basis van jaarcijfers (rapportagevaluta, zo nodig omgerekend)
    try:
        winst_tabel, balans = aandeel.income_stmt, aandeel.balance_sheet
    except Exception as fout:  # yfinance geeft uiteenlopende fouttypen
        log.warning("Jaarcijfers mislukt: %s", fout)
        return reeksen

    rapportage, handel = info.get("financialCurrency"), info.get("currency")
    if not rapportage or not handel:
        return reeksen
    omrekening = wisselkoers(rapportage, handel, dagen)
    if omrekening is None:
        log.warning("Geen wisselkoers %s naar %s: alleen dividendrendement.", rapportage, handel)
        return reeksen

    aandelen = zoek_regel(balans, ["Ordinary Shares Number", "Share Issued"])
    if aandelen is None:
        aandelen = zoek_regel(winst_tabel, ["Diluted Average Shares", "Basic Average Shares"])
    winst_per_aandeel = zoek_regel(winst_tabel, ["Diluted EPS", "Basic EPS"])
    if winst_per_aandeel is None:
        nettowinst = zoek_regel(winst_tabel, ["Net Income Common Stockholders", "Net Income"])
        if nettowinst is not None and aandelen is not None:
            winst_per_aandeel = (nettowinst / aandelen.reindex(nettowinst.index)).dropna()
    eigen_vermogen = zoek_regel(balans, ["Common Stock Equity", "Stockholders Equity"])
    ebitda = zoek_regel(winst_tabel, ["EBITDA", "Normalized EBITDA"])
    schuld = zoek_regel(balans, ["Total Debt"])
    kas = zoek_regel(balans, ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"])

    aandelen_d = per_dag(aandelen, dagen)

    wpa = per_dag(winst_per_aandeel, dagen) * omrekening
    reeksen[KG_KW] = (slot / wpa).where(wpa > 0)  # geen K/W bij verlies

    if eigen_vermogen is not None:
        boekwaarde = per_dag(eigen_vermogen, dagen) * omrekening / aandelen_d
        reeksen[KG_KB] = (slot / boekwaarde).where(boekwaarde > 0)

    if ebitda is not None:
        netto_schuld = (per_dag(schuld, dagen).fillna(0) - per_dag(kas, dagen).fillna(0)) * omrekening
        ondernemingswaarde = slot * aandelen_d + netto_schuld
        ebitda_d = per_dag(ebitda, dagen) * omrekening
        reeksen[KG_EV] = (ondernemingswaarde / ebitda_d).where(ebitda_d > 0)

    return reeksen


def vat_reeks_samen(reeks: pd.Series, hoog_is_goedkoop: bool, laatste_dag: pd.Timestamp) -> dict | None:
    """Huidige waarde, gemiddelde, uitersten en percentiel binnen de eigen geschiedenis.
    Geen uitkomst als er vandaag geen waarde is (bijv. verlies, dus geen K/W) of te weinig geschiedenis."""
    reeks = reeks.replace([np.inf, -np.inf], np.nan).dropna()
    if reeks.empty or reeks.index[-1] < laatste_dag or len(reeks) < WAARDERING_MIN_DAGEN:
        return None
    if hoog_is_goedkoop:  # dividendrendement: alleen de laatste jaren
        reeks = reeks[reeks.index >= reeks.index[-1] - pd.DateOffset(years=WAARDERING_JAREN_DIVIDEND)]
    nu = float(reeks.iloc[-1])
    # gelijke waarden tellen voor de helft, zodat een vlakke reeks op 50 uitkomt en niet op 0
    percentiel = float(((reeks < nu).mean() + 0.5 * (reeks == nu).mean()) * 100)
    goedkoopte = percentiel if hoog_is_goedkoop else 100 - percentiel
    gemiddelde = float(reeks.mean())
    return {
        "nu": round(nu, 2),
        "gem": round(gemiddelde, 2),
        "mediaan": round(float(reeks.median()), 2),
        "min": round(float(reeks.min()), 2),
        "max": round(float(reeks.max()), 2),
        "verschil_gem": round((nu / gemiddelde - 1) * 100, 1) if gemiddelde else None,
        "percentiel": round(percentiel),
        "goedkoopte": round(goedkoopte),
        "oordeel": oordeel(goedkoopte),
        "hoog_is_goedkoop": hoog_is_goedkoop,
        "sinds": reeks.index[0].strftime("%Y-%m-%d"),
    }


def oordeel(goedkoopte: float | None) -> str | None:
    if goedkoopte is None:
        return None
    if goedkoopte >= WAARDERING_GOEDKOOP:
        return "goedkoop"
    if goedkoopte <= 100 - WAARDERING_GOEDKOOP:
        return "duur"
    return "normaal"


def bereken_waardering(aandeel, markt: pd.DataFrame, info: dict, branche: str, ticker: str) -> dict | None:
    """Waardering t.o.v. de eigen geschiedenis: per kengetal en een totaaloordeel voor de branche."""
    reeksen = bereken_waarderingsreeksen(aandeel, markt, info)
    laatste_dag = pd.to_datetime(markt["slot"].dropna().index[-1]).tz_localize(None)
    if branche == "Vastgoed" or ticker in GEEN_EBITDA:
        reeksen.pop(KG_EV, None)
    if branche == "Vastgoed":
        reeksen.pop(KG_KW, None)  # bij vastgoed zegt de K/W weinig
    kengetallen = {}
    for naam, reeks in reeksen.items():
        samenvatting = vat_reeks_samen(reeks, hoog_is_goedkoop=(naam == KG_DIV), laatste_dag=laatste_dag)
        if samenvatting:
            kengetallen[naam] = samenvatting
    if not kengetallen:
        return None

    passend = [k for k in kies_waarderingskengetallen(branche, ticker) if k in kengetallen]
    basis = passend or list(kengetallen)
    score = round(sum(kengetallen[k]["goedkoopte"] for k in basis) / len(basis))
    return {"oordeel": oordeel(score), "score": score, "basis": basis, "kengetallen": kengetallen}


# Resultaten per ticker (voor data.json); de tabel krijgt alleen het oordeel
WAARDERING: dict[str, dict] = {}


# =============================================================================
# 5. TABEL OPBOUWEN
# =============================================================================

# Slotkoersen per ticker, bewaard tijdens het ophalen; de app gebruikt ze voor de grafieken.
KOERSHISTORIE: dict[str, pd.DataFrame] = {}


def maak_rij(naam: str, ticker: str) -> dict:
    """Verzamelt alle gegevens van één aandeel in één tabelrij."""
    markt = haal_marktdata(ticker)
    koers = markt["koers"]
    KOERSHISTORIE[ticker] = markt
    koers_nu = float(koers.iloc[-1])
    rsi_reeks = bereken_rsi(koers)
    rsi_nu = float(rsi_reeks.iloc[-1])
    omkeer = bepaal_rsi_omkeer(rsi_reeks)
    afstand_sma = bereken_afstand_sma(koers)
    rel_volume = bereken_relatief_volume(markt["volume"])

    aandeel = yf.Ticker(ticker)
    info = aandeel.info
    sector_en = info.get("sector", "Onbekend")
    is_vastgoed = sector_en == "Real Estate" or ticker in HANDMATIGE_CIJFERS
    branche = "Vastgoed" if is_vastgoed else SECTOR_NL.get(sector_en, sector_en)

    kw = bereken_kw(info, koers_nu)
    kw_verwacht = bereken_kw_verwacht(info, koers_nu)
    koers_affo = nav_verschil = bron = None
    if is_vastgoed:
        kw = None  # bij vastgoed zegt de K/W weinig
        kw_verwacht = None
        koers_affo, nav_verschil, bron = bereken_vastgoed(info, ticker, koers_nu)

    return {
        KOL_BRANCHE: branche,
        KOL_AANDEEL: naam,
        KOL_TICKER: ticker,
        KOL_VALUTA: info.get("currency"),
        KOL_KOERS: round(koers_nu, 2),
        KOL_DAGVERSCHIL: bereken_dagverschil(koers),
        KOL_RSI: round(rsi_nu, 1),
        KOL_SIGNAAL: bepaal_signaal(rsi_nu),
        KOL_OMKEER: omkeer,
        KOL_SMA: afstand_sma,
        KOL_MACD: bepaal_macd_status(koers),
        KOL_BOLLINGER: bereken_bollinger_pct_b(koers),
        KOL_VOLUME: rel_volume,
        KOL_HOOG: bereken_afstand_hoog(koers),
        KOL_INSTAP: bepaal_instapsignaal(omkeer, afstand_sma, rel_volume),
        KOL_KW: round(kw, 1) if kw else None,
        KOL_KW_VERWACHT: round(kw_verwacht, 1) if kw_verwacht else None,
        KOL_AFFO: koers_affo,
        KOL_NAV: nav_verschil,
        KOL_BRON: bron,
        **bereken_kengetallen(info, ticker),
        KOL_DIVIDEND: bereken_dividendrendement(info, koers_nu),
        KOL_WAARDERING: waardering_voor_tabel(aandeel, markt, info, branche, ticker),
    }


def waardering_voor_tabel(aandeel, markt: pd.DataFrame, info: dict, branche: str, ticker: str) -> str | None:
    """Berekent de waardering t.o.v. de eigen geschiedenis; bewaart de details voor de app."""
    if not WAARDERING_MAKEN:
        return None
    try:
        resultaat = bereken_waardering(aandeel, markt, info, branche, ticker)
    except Exception as fout:  # een fout hier mag de rest van de rij niet blokkeren
        log.warning("Waardering mislukt voor %s: %s", ticker, fout)
        return None
    if not resultaat:
        return None
    WAARDERING[ticker] = resultaat
    return resultaat["oordeel"]


def verzamel_rijen(tickers: dict[str, str]) -> list[dict]:
    """Haalt alle aandelen op; een mislukt aandeel wordt gemeld maar stopt de rest niet."""
    rijen = []
    for naam, ticker in tickers.items():
        try:
            rijen.append(maak_rij(naam, ticker))
        except Exception as fout:  # yfinance geeft uiteenlopende fouttypen
            log.warning("Mislukt voor %s (%s): %s", naam, ticker, fout)
        time.sleep(PAUZE_TUSSEN_AANVRAGEN)
    return rijen


def maak_overzicht(rijen: list[dict]) -> pd.DataFrame:
    """Zet de rijen om in een tabel, gegroepeerd per branche, met branchegemiddelden."""
    overzicht = pd.DataFrame(rijen)
    overzicht[NUMERIEKE_KOLOMMEN] = overzicht[NUMERIEKE_KOLOMMEN].apply(pd.to_numeric, errors="coerce")
    overzicht = overzicht.sort_values([KOL_BRANCHE, KOL_RSI])

    per_branche = overzicht.groupby(KOL_BRANCHE)
    overzicht[KOL_GEM_RSI] = per_branche[KOL_RSI].transform("mean").round(1)
    overzicht[KOL_GEM_KW] = per_branche[KOL_KW].transform("mean").round(1)
    return overzicht.set_index([KOL_BRANCHE, KOL_AANDEEL])

def kies_uitersten(groep: pd.DataFrame, aantal: int = AANTAL_TOP) -> pd.DataFrame:
    """Eerst de grootste stijgers (hoogste bovenaan), daarna de grootste dalers
    (laagste bovenaan). Zijn er 2 x aantal fondsen of minder, dan blijven ze allemaal staan."""
    bekend = (groep.dropna(subset=[KOL_DAGVERSCHIL])
              .sort_values(KOL_DAGVERSCHIL, ascending=False))

    aantal_dalers = min(aantal, len(bekend) // 2)
    aantal_stijgers = min(aantal, len(bekend) - aantal_dalers)

    stijgers = bekend.head(aantal_stijgers)
    dalers = bekend.tail(aantal_dalers).iloc[::-1]  # omgekeerd: laagste bovenaan

    delen = [stijgers, dalers]
    if len(bekend) <= 2 * aantal:
        delen.append(groep[groep[KOL_DAGVERSCHIL].isna()])  # fondsen zonder dagverschil onderaan
    return pd.concat(delen)

def maak_koerstabel(rijen_per_index: dict[str, list[dict]]) -> pd.DataFrame:
    """Per index de grootste stijgers en dalers, met de indices naast elkaar."""
    blokken = {}
    gezien = set()
    for index_naam, rijen in rijen_per_index.items():
        regels = []
        for rij in rijen:
            if rij[KOL_TICKER] in gezien:
                continue  # fonds staat in meerdere lijsten: maar één keer tonen
            gezien.add(rij[KOL_TICKER])
            regels.append({
                KOL_AANDEEL: rij[KOL_AANDEEL],
                KOL_KOERS: rij[KOL_KOERS],
                KOL_VALUTA: rij[KOL_VALUTA],
                KOL_DAGVERSCHIL: rij[KOL_DAGVERSCHIL],
            })
        if not regels:
            continue
        groep = pd.DataFrame(regels)
        cijfers = [KOL_KOERS, KOL_DAGVERSCHIL]
        groep[cijfers] = groep[cijfers].apply(pd.to_numeric, errors="coerce")
        blokken[index_naam] = kies_uitersten(groep).reset_index(drop=True)

    # Naast elkaar plakken: de indexnaam wordt de bovenste kolomkop
    tabel = pd.concat(blokken, axis=1)
    tabel.index = tabel.index + 1
    tabel.index.name = "#"
    return tabel


# =============================================================================
# 6. OPMAAK (kleuren)
# =============================================================================

def kleur_rsi(waarde: float) -> str:
    if pd.isna(waarde):
        return ""
    if waarde < RSI_OVERSOLD:
        return GROEN
    if waarde > RSI_OVERBOUGHT:
        return ROOD
    return ""


def kleur_signaal(waarde: str) -> str:
    return {"oversold": GROEN, "neutraal": GEEL, "overbought": ROOD}.get(waarde, "")


def kleur_omkeer(waarde: str) -> str:
    return {FASE_OMKEER: GROEN, FASE_DALEND: GEEL}.get(waarde, "")


def kleur_trend(waarde: float) -> str:
    """Koers boven het 200-daags gemiddelde is groen, eronder rood."""
    if pd.isna(waarde) or waarde == 0:
        return ""
    return GROEN if waarde > 0 else ROOD


def kleur_macd(waarde: str) -> str:
    return {"positief": GROEN, "negatief": ROOD}.get(waarde, "")


def kleur_bollinger(waarde: float) -> str:
    if pd.isna(waarde):
        return ""
    if waarde < BOLLINGER_LAAG:
        return GROEN
    if waarde > BOLLINGER_HOOG:
        return ROOD
    return ""


def kleur_volume(waarde: float) -> str:
    return GROEN if pd.notna(waarde) and waarde > VOLUME_DREMPEL else ""


def kleur_hoog(waarde: float) -> str:
    """Dicht bij het 52-weeks hoog is groen, ver eronder rood."""
    if pd.isna(waarde):
        return ""
    if waarde >= HOOG_NABIJ:
        return GROEN
    if waarde <= HOOG_VER:
        return ROOD
    return ""


def kleur_instap(waarde: str) -> str:
    return {"ja": DONKERGROEN, "bijna": GEEL}.get(waarde, "")


def kleur_nav(waarde: float) -> str:
    """Korting op de NAV (negatief) is groen, premie (positief) is rood."""
    if pd.isna(waarde) or waarde == 0:
        return ""
    return GROEN if waarde < 0 else ROOD


def kleur_waardering(waarde: str) -> str:
    return {"goedkoop": GROEN, "duur": ROOD}.get(waarde, "")


def kleur_kw(rij: pd.Series) -> pd.Series:
    """K/W lager dan het branchegemiddelde is groen, hoger is rood."""
    stijlen = pd.Series("", index=rij.index)
    kw, gem = rij[KOL_KW], rij[KOL_GEM_KW]
    if pd.notna(kw) and pd.notna(gem) and kw != gem:
        stijlen[KOL_KW] = GROEN if kw < gem else ROOD
    return stijlen


def kleur_volgens_drempels(waarde: float, d: Drempels) -> str:
    if pd.isna(waarde):
        return ""
    if waarde < d.rood_onder:
        return ROOD
    if waarde > d.donker_boven:
        return DONKERGROEN
    if d.groen_van <= waarde <= d.groen_tot:
        return GROEN
    return ""


def kleur_per_branche(kolom: str, normen: dict[str, Drempels], standaard: Drempels | None = None):
    """Maakt een kleurfunctie die per branche andere drempels gebruikt (voor ROE en FCF)."""
    def stijl(rij: pd.Series) -> pd.Series:
        stijlen = pd.Series("", index=rij.index)
        drempels = normen.get(rij.name[0], standaard)  # rij.name = (branche, aandeel)
        if drempels is not None:
            stijlen[kolom] = kleur_volgens_drempels(rij[kolom], drempels)
        return stijlen
    return stijl


def bouw_stijlen(tabel: pd.DataFrame) -> pd.DataFrame:
    """Berekent per cel de kleur, op de gewone tabel (met platte kolomnamen)."""
    stijlen = pd.DataFrame("", index=tabel.index, columns=tabel.columns)

    kolom_regels = {
        KOL_RSI: kleur_rsi,
        KOL_DAGVERSCHIL: kleur_trend,
        KOL_SIGNAAL: kleur_signaal,
        KOL_OMKEER: kleur_omkeer,
        KOL_SMA: kleur_trend,
        KOL_MACD: kleur_macd,
        KOL_BOLLINGER: kleur_bollinger,
        KOL_VOLUME: kleur_volume,
        KOL_HOOG: kleur_hoog,
        KOL_INSTAP: kleur_instap,
        KOL_NAV: kleur_nav,
        KOL_WAARDERING: kleur_waardering,
    }
    for kolom, regel in kolom_regels.items():
        stijlen[kolom] = tabel[kolom].map(regel)

    rij_regels = (
        kleur_kw,
        kleur_per_branche(KOL_ROE, ROE_NORMEN),
        kleur_per_branche(KOL_FCF, FCF_NORMEN, FCF_STANDAARD),
    )
    for regel in rij_regels:
        resultaat = tabel.apply(regel, axis=1)
        stijlen = stijlen.mask(resultaat != "", resultaat)
    return stijlen


def maak_overzicht_styler(tabel: pd.DataFrame):
    """Maakt de opgemaakte hoofdtabel (technisch + fundamenteel), klaar om te tonen."""
    kolommen = TECHNISCH + FUNDAMENTEEL
    stijlen = bouw_stijlen(tabel)[kolommen]
    weergave = tabel[kolommen].copy()

    # Dubbele kolomkop: het bovenste niveau is het soort analyse
    kopjes = ([(GROEP_TECHNISCH, k) for k in TECHNISCH]
              + [(GROEP_FUNDAMENTEEL, k) for k in FUNDAMENTEEL])
    weergave.columns = pd.MultiIndex.from_tuples(kopjes)
    stijlen.columns = weergave.columns

    return (
        weergave.style
        .apply(lambda _: stijlen, axis=None)
        .format(
            {(GROEP_TECHNISCH, KOL_KOERS): "{:.2f}",
             (GROEP_TECHNISCH, KOL_DAGVERSCHIL): "{:+.2f}",
             (GROEP_FUNDAMENTEEL, KOL_EBITDA): "{:,.0f}"},
            na_rep="–", precision=1,
        )
        .set_table_styles([
            {"selector": "th.col_heading.level0",
             "props": [("text-align", "center"), ("border-bottom", "2px solid #888")]},
        ])
    )


def toon_overzicht(tabel: pd.DataFrame) -> None:
    display(maak_overzicht_styler(tabel))


def maak_koers_styler(tabel: pd.DataFrame, bijgewerkt: str = ""):
    """Maakt de opgemaakte koerstabel (indices naast elkaar), klaar om te tonen."""
    indexen = tabel.columns.get_level_values(0).unique()
    stijlen = pd.DataFrame("", index=tabel.index, columns=tabel.columns)
    formaat = {}
    for naam in indexen:
        stijlen[(naam, KOL_AANDEEL)] = "border-left: 2px solid #888"  # scheiding tussen blokken
        stijlen[(naam, KOL_DAGVERSCHIL)] = tabel[(naam, KOL_DAGVERSCHIL)].map(kleur_trend)
        formaat[(naam, KOL_KOERS)] = "{:.2f}"
        formaat[(naam, KOL_DAGVERSCHIL)] = "{:+.2f}"

    return (
        tabel.style
        .set_caption("Koersen en dagverschil: grootste stijgers en dalers per index"
                     + (f" (bijgewerkt {bijgewerkt}, 15 min vertraagd)" if bijgewerkt else ""))
        .apply(lambda _: stijlen, axis=None)
        .format(formaat, na_rep="–")
        .set_table_styles([
            {"selector": "caption",
             "props": [("font-size", "1.3em"), ("font-weight", "bold"),
                       ("text-align", "left"), ("padding-bottom", "8px")]},
            {"selector": "th.col_heading.level0",
             "props": [("text-align", "center"), ("border-bottom", "2px solid #888")]},
        ])
    )


# =============================================================================
# 7. BIJNA REAL-TIME KOERSEN
# =============================================================================

def beurs_open() -> bool:
    """Euronext Amsterdam is open op werkdagen van 09:00 tot 17:30 (Amsterdamse tijd).
    Feestdagen worden niet herkend."""
    nu = pd.Timestamp.now(tz="Europe/Amsterdam")
    minuten = nu.hour * 60 + nu.minute
    return nu.weekday() < 5 and 9 * 60 <= minuten <= 17 * 60 + 30


def haal_live_prijs(ticker: str) -> tuple[float | None, float | None]:
    """Laatste koers en dagverschil (%) t.o.v. de vorige slotkoers (bij Yahoo 15 min vertraagd)."""
    try:
        snel = yf.Ticker(ticker).fast_info
        laatste = als_getal(snel["lastPrice"])
        vorige = als_getal(snel["previousClose"])
    except Exception as fout:  # yfinance geeft uiteenlopende fouttypen
        log.warning("Live koers mislukt voor %s: %s", ticker, fout)
        return None, None
    if laatste is None or not vorige:
        return None, None
    return round(laatste, 2), round((laatste / vorige - 1) * 100, 2)


def pas_live_koersen_toe(rijen_per_index: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Geeft een kopie van de rijen terug met de nieuwste koers en het nieuwste dagverschil."""
    prijzen: dict[str, tuple[float | None, float | None]] = {}
    nieuw = {}
    for index_naam, rijen in rijen_per_index.items():
        bijgewerkt = []
        for rij in rijen:
            ticker = rij[KOL_TICKER]
            if ticker not in prijzen:  # een fonds in meerdere lijsten maar één keer ophalen
                prijzen[ticker] = haal_live_prijs(ticker)
                time.sleep(LIVE_PAUZE)
            koers, verschil = prijzen[ticker]
            nieuwe_rij = dict(rij)
            if koers is not None:
                nieuwe_rij[KOL_KOERS] = koers
                nieuwe_rij[KOL_DAGVERSCHIL] = verschil
            bijgewerkt.append(nieuwe_rij)
        nieuw[index_naam] = bijgewerkt
    return nieuw


def ververs_koerstabel(plek, rijen_per_index: dict[str, list[dict]]) -> None:
    """Werkt de koerstabel bovenaan periodiek bij zolang de beurs open is."""
    for _ in range(MAX_VERVERSINGEN):
        if not beurs_open():
            log.warning("De beurs is gesloten: automatisch verversen gestopt.")
            return
        time.sleep(VERVERS_SECONDEN)
        nieuw = pas_live_koersen_toe(rijen_per_index)
        tijd = pd.Timestamp.now(tz="Europe/Amsterdam").strftime("%H:%M:%S")
        plek.update(maak_koers_styler(maak_koerstabel(nieuw), tijd))


# =============================================================================
# 8. DASHBOARD (webpagina)
# =============================================================================

DASHBOARD_CSS = """
:root { --bg:#f6f7f9; --kaart:#ffffff; --tekst:#1c2430; --zacht:#5f6b7a; --rand:#dde2e8;
        --accent:#1f5f99; --kop:#eef1f5; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#12161c; --kaart:#1b2129; --tekst:#e6eaf0; --zacht:#9aa6b4; --rand:#2e3743;
          --accent:#7fb3e6; --kop:#232b35; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--tekst);
       font:15px/1.45 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
header { padding:20px 16px 8px; max-width:1400px; margin:0 auto; }
h1 { margin:0; font-size:1.5rem; letter-spacing:-0.01em; }
.sub { color:var(--zacht); font-size:.9rem; margin-top:2px; }
nav { position:sticky; top:0; z-index:5; background:var(--bg); border-bottom:1px solid var(--rand);
      display:flex; gap:4px; overflow-x:auto; padding:8px 16px; max-width:1400px; margin:0 auto; }
nav button { border:1px solid var(--rand); background:var(--kaart); color:var(--tekst);
             border-radius:999px; padding:6px 14px; font:inherit; cursor:pointer; white-space:nowrap; }
nav button.actief { background:var(--accent); color:#fff; border-color:var(--accent); }
main { max-width:1400px; margin:0 auto; padding:12px 16px 40px; }
section { display:none; } section.actief { display:block; }
.kaart { background:var(--kaart); border:1px solid var(--rand); border-radius:10px;
         padding:14px; margin-bottom:14px; }
.kaart h2 { margin:0 0 10px; font-size:1.05rem; }
.signalen { display:flex; flex-wrap:wrap; gap:8px; }
.chip { border-radius:8px; padding:6px 10px; font-size:.9rem; }
.chip.ja { background:#2e7d32; color:#fff; } .chip.bijna { background:#ffeb9c; color:#9c5700; }
.chip.oversold { background:#c6efce; color:#006100; }
.leeg { color:var(--zacht); }
.scroll { overflow-x:auto; -webkit-overflow-scrolling:touch; }
table { border-collapse:collapse; font-size:.85rem; white-space:nowrap; }
th, td { padding:5px 8px; border-bottom:1px solid var(--rand); text-align:right; }
th { background:var(--kop); position:sticky; top:0; }
th.row_heading, th.blank { text-align:left; }
th.row_heading.level1 { position:sticky; left:0; z-index:1; }
caption { display:none; }
.toelichting li { margin-bottom:6px; } .toelichting p { margin:12px 0 6px; }
footer { color:var(--zacht); font-size:.8rem; max-width:1400px; margin:0 auto; padding:0 16px 30px; }
"""

DASHBOARD_JS = """
document.querySelectorAll('nav button').forEach(function (knop) {
  knop.addEventListener('click', function () {
    document.querySelectorAll('nav button, section').forEach(function (el) {
      el.classList.remove('actief');
    });
    knop.classList.add('actief');
    document.getElementById(knop.dataset.tab).classList.add('actief');
    window.scrollTo(0, 0);
  });
});
"""


def markdown_naar_html(tekst: str) -> str:
    """Eenvoudige omzetting van de toelichting (vet, cursief, opsommingen) naar HTML."""
    import html
    import re

    def inline(regel: str) -> str:
        regel = html.escape(regel)
        regel = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", regel)
        return re.sub(r"\*(.+?)\*", r"<em>\1</em>", regel)

    delen, in_lijst = [], False
    for regel in tekst.strip().splitlines():
        regel = regel.strip()
        if regel.startswith("- "):
            if not in_lijst:
                delen.append("<ul>")
                in_lijst = True
            delen.append(f"<li>{inline(regel[2:])}</li>")
            continue
        if in_lijst:
            delen.append("</ul>")
            in_lijst = False
        if regel:
            delen.append(f"<p>{inline(regel)}</p>")
    if in_lijst:
        delen.append("</ul>")
    return "\n".join(delen)


def bepaal_signalen(rijen_per_index: dict[str, list[dict]]) -> list[dict]:
    """Aandelen met een instapsignaal ('ja' of 'bijna') of een oversold-RSI, belangrijkste eerst."""
    signalen, gezien = [], set()
    alle_rijen = [rij for rijen in rijen_per_index.values() for rij in rijen]
    volgorde = {"ja": 0, "bijna": 1}
    for rij in sorted(alle_rijen, key=lambda r: (volgorde.get(r[KOL_INSTAP], 2), r[KOL_RSI])):
        if rij[KOL_TICKER] in gezien:
            continue
        gezien.add(rij[KOL_TICKER])
        if rij[KOL_INSTAP] in ("ja", "bijna"):
            soort, tekst = rij[KOL_INSTAP], f"instap {rij[KOL_INSTAP]}"
        elif rij[KOL_SIGNAAL] == "oversold":
            soort, tekst = "oversold", "oversold"
        else:
            continue
        signalen.append({"aandeel": rij[KOL_AANDEEL], "ticker": rij[KOL_TICKER],
                         "soort": soort, "tekst": tekst, "rsi": round(rij[KOL_RSI])})
    return signalen


def maak_signalenkaart(rijen_per_index: dict[str, list[dict]]) -> str:
    """Bovenaan het dashboard: welke aandelen nu een instapsignaal of oversold-RSI hebben."""
    import html

    chips = [f'<span class="chip {s["soort"]}">{html.escape(s["aandeel"])}: {s["tekst"]} '
             f'(RSI {s["rsi"]})</span>' for s in bepaal_signalen(rijen_per_index)]
    inhoud = "".join(chips) or '<span class="leeg">Vandaag geen instapsignalen of oversold-aandelen.</span>'
    return f'<div class="kaart"><h2>Signalen</h2><div class="signalen">{inhoud}</div></div>'


def maak_dashboard_html(rijen_per_index: dict[str, list[dict]]) -> str:
    """Bouwt één zelfstandige webpagina met tabs: Koersen, per index een tabel, Toelichting."""
    import html

    tijd = pd.Timestamp.now(tz="Europe/Amsterdam").strftime("%d-%m-%Y %H:%M")
    tabs = [("koersen", "Koersen")]
    secties = []

    koers_html = (maak_koers_styler(maak_koerstabel(rijen_per_index))
                  .set_uuid("koersen").to_html())
    secties.append(
        '<section id="koersen" class="actief">'
        + maak_signalenkaart(rijen_per_index)
        + '<div class="kaart"><h2>Grootste stijgers en dalers per index</h2>'
        + f'<div class="scroll">{koers_html}</div></div></section>'
    )

    for nummer, (index_naam, rijen) in enumerate(rijen_per_index.items()):
        if not rijen:
            continue
        sleutel = f"index{nummer}"
        tabs.append((sleutel, index_naam))
        tabel_html = maak_overzicht_styler(maak_overzicht(rijen)).set_uuid(sleutel).to_html()
        secties.append(
            f'<section id="{sleutel}"><div class="kaart"><h2>{html.escape(index_naam)}</h2>'
            f'<div class="scroll">{tabel_html}</div></div></section>'
        )

    tabs.append(("uitleg", "Toelichting"))
    secties.append('<section id="uitleg"><div class="kaart toelichting">'
                   + markdown_naar_html(TOELICHTING) + "</div></section>")

    actief = ' class="actief"'
    knoppen = "".join(
        f'<button data-tab="{sleutel}"{actief if i == 0 else ""}>{html.escape(label)}</button>'
        for i, (sleutel, label) in enumerate(tabs)
    )
    return f"""<!doctype html>
<html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MalKho dashboard</title><style>{DASHBOARD_CSS}</style></head>
<body>
<header><h1>MalKho</h1><div class="sub">Bijgewerkt {tijd} · koersen van Yahoo Finance (slotkoers of 15 min vertraagd)</div></header>
<nav>{knoppen}</nav>
<main>{"".join(secties)}</main>
<footer>MalKho-script versie {MALKHO_VERSIE} ({MALKHO_DATUM}) · Geen beleggingsadvies. Cijfers van Yahoo Finance kunnen afwijken van andere bronnen.</footer>
<script>{DASHBOARD_JS}</script>
</body></html>"""


# =============================================================================
# 9. DATABESTAND VOOR DE APP (data.json)
# =============================================================================

KLEURNAMEN = {GROEN: "groen", GEEL: "geel", ROOD: "rood", DONKERGROEN: "donkergroen"}


def json_waarde(waarde):
    """Zet een waarde om naar iets wat in JSON past (lege waarden worden null)."""
    if waarde is None:
        return None
    if isinstance(waarde, str):
        return waarde
    try:
        if pd.isna(waarde):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(waarde, "item"):  # numpy-getallen omzetten naar gewone Python-getallen
        waarde = waarde.item()
    if isinstance(waarde, float):
        return waarde if math.isfinite(waarde) else None
    return waarde


def maak_index_data(rijen: list[dict]) -> list[dict]:
    """Alle aandelen van één index, met waarden en kleuren per kolom, gesorteerd op branche."""
    overzicht = maak_overzicht(rijen)
    stijlen = bouw_stijlen(overzicht)
    aandelen = []
    for (branche, aandeel), rij in overzicht.iterrows():
        aandelen.append({
            "aandeel": aandeel,
            "branche": branche,
            "ticker": rij[KOL_TICKER],
            "valuta": json_waarde(rij[KOL_VALUTA]),
            "waarden": {kol: json_waarde(rij[kol]) for kol in TECHNISCH + FUNDAMENTEEL},
            "kleuren": {kol: KLEURNAMEN[stijl] for kol, stijl in stijlen.loc[(branche, aandeel)].items()
                        if stijl in KLEURNAMEN},
        })
    return aandelen


def maak_beweging_data(rijen_per_index: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Per index de grootste stijgers en dalers (zoals de koerstabel bovenaan)."""
    beweging, gezien = {}, set()
    for index_naam, rijen in rijen_per_index.items():
        regels = []
        for rij in rijen:
            if rij[KOL_TICKER] in gezien:
                continue
            gezien.add(rij[KOL_TICKER])
            regels.append({KOL_AANDEEL: rij[KOL_AANDEEL], KOL_TICKER: rij[KOL_TICKER],
                           KOL_KOERS: rij[KOL_KOERS], KOL_VALUTA: rij[KOL_VALUTA],
                           KOL_DAGVERSCHIL: rij[KOL_DAGVERSCHIL]})
        if not regels:
            continue
        groep = pd.DataFrame(regels)
        groep[[KOL_KOERS, KOL_DAGVERSCHIL]] = groep[[KOL_KOERS, KOL_DAGVERSCHIL]].apply(
            pd.to_numeric, errors="coerce")
        beweging[index_naam] = [
            {"aandeel": r[KOL_AANDEEL], "ticker": r[KOL_TICKER], "koers": json_waarde(r[KOL_KOERS]),
             "valuta": json_waarde(r[KOL_VALUTA]), "dagverschil": json_waarde(r[KOL_DAGVERSCHIL])}
            for _, r in kies_uitersten(groep).iterrows()
        ]
    return beweging


def afgerond(waarde, decimalen: int = 2) -> float | None:
    getal = als_getal(waarde)
    return round(getal, decimalen) if getal is not None else None


def bereken_koersinfo(markt: pd.DataFrame) -> dict:
    """Slotkoers, vorige slot, dag hoog/laag, 12 maanden hoog/laag en het rendement dit jaar (YTD).
    Op basis van de gewone koersen, zoals op beurssites."""
    slot = markt["slot"].dropna()
    jaar = markt.tail(HANDELSDAGEN_JAAR)
    vorig_jaar = slot[slot.index.year < slot.index[-1].year]
    ytd = None
    if not vorig_jaar.empty and als_getal(vorig_jaar.iloc[-1]):
        ytd = (float(slot.iloc[-1]) / float(vorig_jaar.iloc[-1]) - 1) * 100
    return {
        "slot": afgerond(slot.iloc[-1]),
        "vorige_slot": afgerond(slot.iloc[-2]) if len(slot) > 1 else None,
        "dag_hoog": afgerond(markt["hoog"].iloc[-1]),
        "dag_laag": afgerond(markt["laag"].iloc[-1]),
        "hoog_12m": afgerond(jaar["hoog"].max()),
        "laag_12m": afgerond(jaar["laag"].min()),
        "ytd": afgerond(ytd),
    }


def haal_dagverloop(ticker: str) -> pd.Series | None:
    """Koersen van de laatste beursdag per 5 minuten (voor de grafiek 1D), in Amsterdamse tijd."""
    try:
        data = yf.download(ticker, period="5d", interval="5m", auto_adjust=False, progress=False)
    except Exception as fout:  # yfinance geeft uiteenlopende fouttypen
        log.warning("Dagverloop mislukt voor %s: %s", ticker, fout)
        return None
    if data.empty:
        return None
    koers = data["Close"].squeeze().dropna()
    if koers.empty:
        return None
    if koers.index.tz is None:
        koers.index = koers.index.tz_localize("UTC")
    koers.index = koers.index.tz_convert("Europe/Amsterdam")
    laatste_dag = koers.index[-1].date()
    return koers[koers.index.date == laatste_dag]


def reeks_naar_lijst(reeks: pd.Series, datumformaat: str) -> dict[str, list]:
    return {"datums": [d.strftime(datumformaat) for d in reeks.index],
            "koersen": [round(float(k), 2) for k in reeks]}


def maak_historie_bestand(markt: pd.DataFrame, dagverloop: pd.Series | None) -> dict:
    """Koersgeschiedenis van één aandeel voor de grafieken in de app:
    'dag'        de laatste beursdag per 5 minuten (1D),
    'dagelijks'  slotkoersen van ruim het laatste jaar (1W tot en met 1Y en YTD),
    'wekelijks'  de laatste slotkoers van elke week, over de hele geschiedenis (3Y, 5Y, Max)."""
    slot = markt["slot"].dropna()
    dagelijks = slot[slot.index >= slot.index[-1] - pd.DateOffset(days=HISTORIE_DAGEN_APP)]
    wekelijks = slot.groupby(slot.index.to_period("W-FRI")).tail(1)
    return {
        "dag": reeks_naar_lijst(dagverloop, "%H:%M") if dagverloop is not None else None,
        "dagelijks": reeks_naar_lijst(dagelijks, "%Y-%m-%d"),
        "wekelijks": reeks_naar_lijst(wekelijks, "%Y-%m-%d"),
    }


def historie_bestandsnaam(ticker: str) -> str:
    """Veilige bestandsnaam voor een ticker; de app gebruikt dezelfde regel."""
    import re
    return re.sub(r"[^A-Za-z0-9.\-]", "_", ticker) + ".json"


def maak_app_data(rijen_per_index: dict[str, list[dict]]) -> dict:
    """Alles wat de app op het eerste scherm nodig heeft, in één databestand.
    De koersgeschiedenis per aandeel staat in aparte bestanden in de map 'historie'."""
    return {
        "versie": 2,
        "script_versie": f"{MALKHO_VERSIE} ({MALKHO_DATUM})",
        "bijgewerkt": pd.Timestamp.now(tz="Europe/Amsterdam").isoformat(timespec="minutes"),
        "kolommen": {"technisch": TECHNISCH, "fundamenteel": FUNDAMENTEEL},
        "signalen": bepaal_signalen(rijen_per_index),
        "beweging": maak_beweging_data(rijen_per_index),
        "indices": {naam: maak_index_data(rijen) for naam, rijen in rijen_per_index.items() if rijen},
        "koersinfo": {ticker: bereken_koersinfo(markt) for ticker, markt in KOERSHISTORIE.items()},
        "waardering": WAARDERING,
        "toelichting": TOELICHTING.strip(),
    }


def bewaar_historie(map_pad: str) -> int:
    """Schrijft per aandeel een historiebestand. Geeft het aantal geschreven bestanden terug."""
    historie_map = os.path.join(map_pad, HISTORIE_MAP)
    aantal = 0
    for ticker, markt in KOERSHISTORIE.items():
        try:
            inhoud = maak_historie_bestand(markt, haal_dagverloop(ticker))
            schrijf_bestand(historie_map, historie_bestandsnaam(ticker),
                            json.dumps(inhoud, separators=(",", ":")))
            aantal += 1
        except Exception as fout:  # één aandeel mag de rest niet blokkeren
            log.warning("Historie opslaan mislukt voor %s: %s", ticker, fout)
        time.sleep(PAUZE_TUSSEN_AANVRAGEN)
    return aantal


# =============================================================================
# 10. BESTANDEN OPSLAAN
# =============================================================================

def kies_uitvoermap() -> tuple[str, bool]:
    """Bepaalt waar de bestanden komen. Geeft (map, terugval_in_colab) terug."""
    if UITVOER_MAP:  # GitHub of een zelf gekozen map
        return UITVOER_MAP, False
    try:
        from google.colab import drive  # bestaat alleen in Colab
    except ImportError:
        return DASHBOARD_MAP_LOKAAL, False
    try:
        if not os.path.isdir("/content/drive/MyDrive"):
            drive.mount("/content/drive")
        return DASHBOARD_MAP_DRIVE, False
    except Exception as fout:  # bijv. 'credential propagation was unsuccessful'
        log.warning("Google Drive koppelen mislukt (%s). Het dashboard wordt in plaats "
                    "daarvan gedownload.", fout)
        return "/content", True


def schrijf_bestand(map_pad: str, naam: str, inhoud: str) -> str:
    os.makedirs(map_pad, exist_ok=True)
    pad = os.path.join(map_pad, naam)
    with open(pad, "w", encoding="utf-8") as bestand:
        bestand.write(inhoud)
    return pad


def bewaar_uitvoer(rijen_per_index: dict[str, list[dict]]) -> list[str]:
    """Schrijft het dashboard en het databestand voor de app. Geeft de opgeslagen paden terug."""
    map_pad, downloaden = kies_uitvoermap()
    dashboard_naam = "index.html" if UITVOER_MAP else DASHBOARD_BESTAND
    paden = []
    taken = (
        (dashboard_naam, lambda: maak_dashboard_html(rijen_per_index)),
        (DATA_BESTAND, lambda: json.dumps(maak_app_data(rijen_per_index), ensure_ascii=False,
                                          separators=(",", ":"))),
    )
    for naam, maak in taken:
        try:
            paden.append(schrijf_bestand(map_pad, naam, maak()))
        except Exception as fout:  # het ene bestand mag het andere niet blokkeren
            log.warning("%s opslaan mislukt: %s", naam, fout)

    aantal = bewaar_historie(map_pad)
    if not IN_NOTEBOOK:
        print(f"Koersgeschiedenis opgeslagen voor {aantal} aandelen.")

    if downloaden and paden:
        from google.colab import files
        try:
            files.download(paden[0])  # het dashboard komt in de downloadmap van je browser
        except Exception as fout:
            log.warning("Downloaden mislukt: %s. Het bestand staat links in Colab onder 'Bestanden'.", fout)
    return paden


# =============================================================================
# 11. HOOFDPROGRAMMA
# =============================================================================

def main() -> int:
    print(f"MalKho-script versie {MALKHO_VERSIE} ({MALKHO_DATUM})")
    # Plek helemaal bovenaan reserveren; de tabel komt hier te staan zodra de data binnen is
    koers_plek = display(
        Markdown("## Koersen en dagverschil\n\n*De gegevens worden opgehaald...*"),
        display_id=True,
    )

    rijen_per_index = {naam: verzamel_rijen(tickers) for naam, tickers in INDICES.items()}
    if not any(rijen_per_index.values()):
        koers_plek.update(Markdown("**Geen gegevens opgehaald.** Kijk naar de meldingen 'Mislukt voor'."))
        log.error("Geen enkel aandeel gelukt.")
        return 1

    koers_plek.update(maak_koers_styler(maak_koerstabel(rijen_per_index)))

    for index_naam, rijen in rijen_per_index.items():
        display(Markdown(f"## {index_naam}"))
        if not rijen:
            log.error("Geen enkel aandeel gelukt voor %s.", index_naam)
            continue
        toon_overzicht(maak_overzicht(rijen))
    display(Markdown(TOELICHTING))

    if DASHBOARD_MAKEN:
        paden = bewaar_uitvoer(rijen_per_index)
        if paden:
            lijst = ", ".join(f"`{pad}`" for pad in paden)
            display(Markdown(f"**Opgeslagen:** {lijst} (download het dashboard en open het in je browser)."))
        if not IN_NOTEBOOK:
            aantal = sum(len(rijen) for rijen in rijen_per_index.values())
            print(f"Klaar: {aantal} aandelen verwerkt. Opgeslagen: {', '.join(paden) or 'niets'}")
            if len(paden) < 2:
                return 1

    if IN_NOTEBOOK:
        ververs_koerstabel(koers_plek, rijen_per_index)
    return 0


if IN_NOTEBOOK:
    main()
elif __name__ == "__main__":
    sys.exit(main())
