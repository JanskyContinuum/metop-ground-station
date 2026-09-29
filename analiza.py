import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from pyorbital.orbital import Orbital


# ==========================================
# 1. FUNKCJE POMOCNICZE (zostawiamy bez zmian)
# ==========================================
def parse_tle_epoch(line1):
    tokens = line1.split()
    epoch_str = tokens[3]
    year = int(epoch_str[:2])
    year += 2000 if year < 57 else 1900
    day_of_year = float(epoch_str[2:])
    return datetime(year, 1, 1) + timedelta(days=day_of_year - 1)


def load_all_tles(filepath):
    tles = []
    try:
        with open(filepath, 'r') as file:
            lines = file.readlines()
        for i in range(0, len(lines), 2):
            if i + 1 >= len(lines): break
            l1 = lines[i]
            l2 = lines[i + 1]
            tles.append({'name': 'METOP-B', 'line1': l1, 'line2': l2, 'epoch': parse_tle_epoch(l1)})
    except FileNotFoundError:
        print(f"BŁĄD: Nie znaleziono pliku {filepath}!")
    return tles


def get_closest_tle_from_memory(tles, target_date):
    best_tle = None
    min_time_diff = timedelta(days=99999)
    for tle in tles:
        time_diff = abs(target_date - tle['epoch'])
        if time_diff < min_time_diff:
            min_time_diff = time_diff
            best_tle = tle
    return best_tle


# ==========================================
# 2. KONFIGURACJA GŁÓWNA
# ==========================================
OBS_LON = 21.0122  # Warszawa
OBS_LAT = 52.2297
OBS_ALT = 0.11
TLE_FILE = "metop_b_history.txt"

end_time = datetime.utcnow()
start_time = end_time - timedelta(days=30)  # Zmień na tyle dni, ile analizujesz
step_seconds = 30
MIN_ELEVATION = 5.0  # Minimalny kąt elewacji dla AOS/LOS

# ==========================================
# 3. ALGORYTM SYMULACJI (Poprawiony)
# ==========================================
print("Wczytywanie archiwum TLE...")
history_tles = load_all_tles(TLE_FILE)
if not history_tles: exit()

passes = []  # Przechowuje dane o każdym PEŁNYM przelocie

print("Rozpoczynam symulację dzień po dniu...")
current_day = start_time

is_visible = False
current_pass = {'az': [], 'el': [], 'time': []}

while current_day <= end_time:
    best_tle = get_closest_tle_from_memory(history_tles, current_day)
    orb = Orbital(best_tle['name'], line1=best_tle['line1'], line2=best_tle['line2'])

    day_end = current_day + timedelta(days=1)
    current_step = current_day

    while current_step < day_end and current_step <= end_time:
        az, el = orb.get_observer_look(current_step, OBS_LON, OBS_LAT, OBS_ALT)

        if el > MIN_ELEVATION:
            if not is_visible:
                is_visible = True
                current_pass = {'az': [], 'el': [], 'time': []}

            current_pass['az'].append(az)
            current_pass['el'].append(el)
            current_pass['time'].append(current_step)
        else:
            if is_visible:
                is_visible = False
                if len(current_pass['el']) > 0:
                    # Obliczanie parametrów przelotu
                    max_el = max(current_pass['el'])
                    max_el_index = current_pass['el'].index(max_el)
                    az_at_max_el = current_pass['az'][max_el_index]

                    # Sprawdzenie czy przelot jest zachodni (Azymut > 180) czy wschodni
                    is_west = az_at_max_el > 180.0

                    passes.append({
                        'az': current_pass['az'],
                        'el': current_pass['el'],
                        'time': current_pass['time'],
                        'max_el': max_el,
                        'is_west': is_west,
                        'start_time': current_pass['time'][0]
                    })
        current_step += timedelta(seconds=step_seconds)
    current_day += timedelta(days=1)

print(f"Zarejestrowano {len(passes)} pełnych przelotów (> {MIN_ELEVATION}°).")

# ==========================================
# 4. RYSOWANIE WYKRESÓW
# ==========================================

# --- WYKRES 1: TRAJEKTORIE POLARNE ---
fig1 = plt.figure(figsize=(10, 10))
ax1 = fig1.add_subplot(111, polar=True)
ax1.set_theta_zero_location('N')
ax1.set_theta_direction(-1)
ax1.set_rlim(0, 90)  # Krawędź to 0 stopni (horyzont)
ax1.set_yticks(np.arange(0, 90, 15))
ax1.set_yticklabels([f"{90 - y}°" for y in np.arange(0, 90, 15)])

high_pass_handled = False
low_pass_handled = False

for p in passes:
    az_rad = np.radians(p['az'])
    r = 90.0 - np.array(p['el'])  # 0 na środku to 90 stopni elewacji

    if p['max_el'] >= 60.0:
        ax1.plot(az_rad, r, color='crimson', linewidth=2, alpha=0.8,
                 label='Przeloty wysokie (≥60°)' if not high_pass_handled else "")
        high_pass_handled = True
    else:
        ax1.plot(az_rad, r, color='steelblue', linewidth=0.5, alpha=0.4,
                 label='Pozostałe przeloty' if not low_pass_handled else "")
        low_pass_handled = True

plt.title('Trajektorie przelotów MetOp-B nad Warszawą', pad=20, fontsize=14)
# Ustawiamy legendę pod wykresem
plt.legend(loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=2)
# ZAMIAST tight_layout() wymuszamy marginesy okna:
# 15% wolnego miejsca od dołu i 10% od góry
fig1.subplots_adjust(bottom=0.15, top=0.80)
# --- WYKRES 2: MAX ELEWACJA VS CZAS (ZACHÓD VS WSCHÓD) ---
fig2, ax2 = plt.subplots(figsize=(12, 6))

west_times = [p['start_time'] for p in passes if p['is_west']]
west_els = [p['max_el'] for p in passes if p['is_west']]
east_times = [p['start_time'] for p in passes if not p['is_west']]
east_els = [p['max_el'] for p in passes if not p['is_west']]

#ax2.scatter(west_times, west_els, color='darkorange', marker='v', s=60, label='Po stronie zachodniej (Az > 180°)', zorder=3)
#ax2.scatter(east_times, east_els, color='forestgreen', marker='^', s=60, label='Po stronie wschodniej (Az < 180°)', zorder=3)

ax2.scatter([p['start_time'] for p in passes], [p['max_el'] for p in passes], color='forestgreen', marker='^', s=60, label='Osiągnięta elewacja',
            zorder=3)



# Linia odcięcia dla wysokich przelotów
ax2.axhline(y=60, color='red', linestyle='--', alpha=0.6, label='Próg wysokich przelotów (60°)')

ax2.set_ylim(0, 95)
ax2.set_ylabel('Maksymalna elewacja [°]', fontsize=12)
ax2.set_xlabel('Data', fontsize=12)
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
plt.xticks(rotation=45)
ax2.grid(True, linestyle=':', alpha=0.7)
plt.title('Maksymalna elewacja przelotów MetOp-B w czasie', pad=15, fontsize=14)
plt.legend()
plt.tight_layout()

# --- WYKRES 3: HISTOGRAM PRZELOTÓW ---
fig3, ax3 = plt.subplots(figsize=(8, 5))
all_max_els = [p['max_el'] for p in passes]
bins = [5, 15, 30, 45, 60, 75, 90]

ax3.hist(all_max_els, bins=bins, color='royalblue', edgecolor='black', alpha=0.7)
ax3.axvline(x=60, color='red', linestyle='--', linewidth=2, label='Cel promotora (>60°)')

ax3.set_xlabel('Maksymalna elewacja przelotu [°]', fontsize=12)
ax3.set_ylabel('Liczba przelotów', fontsize=12)
ax3.set_xticks(bins)
plt.title('Rozkład maksymalnych elewacji przelotów', pad=15, fontsize=14)
plt.legend()
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()


# --- WYKRES 4: PROFIL DYNAMICZNY PRZELOTU (INDUSTRY STANDARD LINK BUDGET) ---
# Wybieramy najlepszy przelot (najwyższa elewacja) do analizy szczegółowej
best_pass = max(passes, key=lambda p: p['max_el'])

# Parametry fizyczne
RE_KM = 6371.0  # Promień Ziemi [km]
H_SAT_KM = 817.0 # Średnia wysokość MetOp-B [km]
FREQ_MHZ = 1701.3 # Częstotliwość AHRPT (pasmo L)

# Czas w minutach od AOS (Acquisition of Signal)
rel_times_min = [(t - best_pass['time'][0]).total_seconds() / 60.0 for t in best_pass['time']]
elevations = np.array(best_pass['el'])

# Obliczenia fizyczne: Slant Range (Twierdzenie cosinusów dla sfery Ziemi)
# d = sqrt( (Re * sin(El))^2 + 2*Re*h + h^2 ) - Re * sin(El)
el_rad = np.radians(elevations)
slant_ranges = np.sqrt((RE_KM * np.sin(el_rad))**2 + 2 * RE_KM * H_SAT_KM + H_SAT_KM**2) - (RE_KM * np.sin(el_rad))

# Obliczenia fizyczne: Free Space Path Loss (FSPL) w [dB]
# Wzór: FSPL(dB) = 20*log10(d_km) + 20*log10(f_MHz) + 32.44
fspl_db = 20 * np.log10(slant_ranges) + 20 * np.log10(FREQ_MHZ) + 32.44

# Rysowanie wykresu
fig4, ax4_el = plt.subplots(figsize=(10, 6))

# Oś 1: Elewacja (tło)
color_el = 'lightgray'
ax4_el.fill_between(rel_times_min, 0, elevations, color=color_el, alpha=0.5, label='Kąt Elewacji [°]')
ax4_el.set_xlabel('Czas od rozpoczęcia obserwacji (AOS) [minuty]', fontsize=12)
ax4_el.set_ylabel('Elewacja [°]', fontsize=12, color='gray')
ax4_el.tick_params(axis='y', labelcolor='gray')
ax4_el.set_ylim(0, 90)

# Oś 2: Slant Range (Dystans w km)
ax4_sr = ax4_el.twinx()
color_sr = 'tab:blue'
ax4_sr.plot(rel_times_min, slant_ranges, color=color_sr, linewidth=2.5, label='Dystans (Slant Range) [km]')
ax4_sr.set_ylabel('Dystans do satelity [km]', fontsize=12, color=color_sr)
ax4_sr.tick_params(axis='y', labelcolor=color_sr)

# Oś 3: FSPL (Tłumienie)
ax4_fspl = ax4_el.twinx()
# Przesuwamy trzecią oś na prawo, żeby się nie nakładała z drugą
ax4_fspl.spines['right'].set_position(('outward', 60))
color_fspl = 'tab:red'
ax4_fspl.plot(rel_times_min, fspl_db, color=color_fspl, linestyle='--', linewidth=2.5, label='FSPL [dB]')
ax4_fspl.set_ylabel('Tłumienie wolnej przestrzeni (FSPL) [dB]', fontsize=12, color=color_fspl)
ax4_fspl.tick_params(axis='y', labelcolor=color_fspl)

# Złożenie legend z różnych osi
lines_el, labels_el = ax4_el.get_legend_handles_labels()
lines_sr, labels_sr = ax4_sr.get_legend_handles_labels()
lines_fspl, labels_fspl = ax4_fspl.get_legend_handles_labels()
ax4_el.legend(lines_el + lines_sr + lines_fspl, labels_el + labels_sr + labels_fspl, loc='upper center', bbox_to_anchor=(0.5, 1.15), ncol=3)

plt.title('Profil przelotu zenitalnego: Dynamika dystansu i tłumienia sygnału AHRPT', pad=35, fontsize=14)
fig4.tight_layout()
plt.grid(True, linestyle=':', alpha=0.6)

# ==========================================
# 5. DODATKOWE WYKRESY UZASADNIAJĄCE PROJEKT
# ==========================================

# Przygotowanie danych do nowych wykresów
durations_total = []
durations_useful = []
max_els = []
pass_hours_local = []

# Zakładamy strefę czasową Warszawy (ok. UTC+2 dla czasu letniego CEST)
# Dla idealnej precyzji używa się biblioteki pytz, ale proste przesunięcie wystarczy do statystyki
TIMEZONE_OFFSET = timedelta(hours=2)

for p in passes:
    max_els.append(p['max_el'])

    # 1. Czas całkowitego kontaktu (od wyjścia nad horyzont do zajścia)
    t_total = (p['time'][-1] - p['time'][0]).total_seconds() / 60.0
    durations_total.append(t_total)

    # 2. Czas "użytecznego" okna (elewacja >= 30 stopni)
    useful_times = [t for el, t in zip(p['el'], p['time']) if el >= 30.0]
    if len(useful_times) > 1:
        t_useful = (useful_times[-1] - useful_times[0]).total_seconds() / 60.0
    else:
        t_useful = 0.0  # Przelot nie osiągnął 30 stopni
    durations_useful.append(t_useful)

    # 3. Godzina lokalna przelotu (środek przelotu - max elewacja)
    max_el_index = p['el'].index(p['max_el'])
    time_utc = p['time'][max_el_index]
    time_local = time_utc + TIMEZONE_OFFSET
    # Zapisujemy godzinę w formacie ułamkowym (np. 14:30 to 14.5) dla gładkiego histogramu
    pass_hours_local.append(time_local.hour + time_local.minute / 60.0)

# --- WYKRES 4: CZAS TRWANIA PRZELOTU VS MAX ELEWACJA ---
fig4, ax4 = plt.subplots(figsize=(10, 6))

ax4.scatter(max_els, durations_total, color='steelblue', alpha=0.6, s=50,
            label='Całkowity czas widoczności (>5°)')
ax4.scatter(max_els, durations_useful, color='crimson', alpha=0.8, s=50, marker='s',
            label='Użyteczne okno odbioru AHRPT (≥30°)')

# Dodanie linii trendu dla użytecznego okna (opcjonalne, ale wygląda profesjonalnie)
valid_idx = [i for i, d in enumerate(durations_useful) if d > 0]
if valid_idx:
    z = np.polyfit([max_els[i] for i in valid_idx], [durations_useful[i] for i in valid_idx], 2)
    p_poly = np.poly1d(z)
    x_trend = np.linspace(30, 90, 100)
    ax4.plot(x_trend, p_poly(x_trend), color='darkred', linestyle='--', alpha=0.7)

ax4.axvline(x=60, color='gray', linestyle=':', label='Próg wysokich przelotów (60°)')
ax4.axhline(y=5.5, color='green', linestyle='-.', alpha=0.5, label='Nominalny czas okna (~5.5 min)')

ax4.set_xlabel('Maksymalna elewacja przelotu [°]', fontsize=12)
ax4.set_ylabel('Czas trwania okna [minuty]', fontsize=12)
plt.title('Zależność czasu trwania okna obserwacyjnego od maksymalnej elewacji', pad=15, fontsize=14)
ax4.grid(True, linestyle='--', alpha=0.6)
plt.legend(loc='upper left')
plt.tight_layout()


# --- WYKRES 6: ZALEŻNOŚĆ ELEWACJI OD PORY DNIA (TYPOWY CYKL 24H) ---
fig6, ax6 = plt.subplots(figsize=(10, 6))

# Rysowanie punktów przelotów (Oś X: Godzina, Oś Y: Max Elewacja)
ax6.scatter(pass_hours_local, max_els, color='darkmagenta', alpha=0.75, s=60, edgecolors='black', zorder=3, label='Zarejestrowane przeloty')


# Dodanie zacienionych obszarów (okien), w których zazwyczaj występują najlepsze przeloty
# Parametry okien można delikatnie dostosować w zależności od przesunięcia czasu (Zima/Lato)
ax6.axvspan(9, 11.5, color='orange', alpha=0.15, label='Okno poranne')
ax6.axvspan(20, 22.5, color='navy', alpha=0.15, label='Okno wieczorne')

# Ustawienia osi
ax6.set_xlim(0, 24)
ax6.set_ylim(0, 95)
ax6.set_xticks(np.arange(0, 25, 2))
ax6.set_xticklabels([f"{h:02d}:00" for h in np.arange(0, 25, 2)])

ax6.set_xlabel('Czas lokalny (CEST) [HH:MM]', fontsize=12)
ax6.set_ylabel('Maksymalna elewacja przelotu [°]', fontsize=12)
plt.title('Zależność elewacji przelotu od pory dnia', pad=15, fontsize=14)

# Legenda ląduje symetrycznie pod wykresem, rozbita na dwie kolumny,
# żeby nie zasłaniała danych o wysokich elewacjach.
ax6.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=2)
plt.tight_layout()


# Wyświetlenie wszystkich wygenerowanych wykresów na raz
plt.show()

