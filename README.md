# Unser Wochenkochplan

## Start
1. Python installieren.
2. Im Projektordner: `pip install -r requirements.txt`
3. App starten: `streamlit run app.py`

Beim ersten Start werden die 237 Rezepte aus der Excel-Datei importiert und automatisch grob kategorisiert. Alle Einstufungen können in der App unter **Rezepte** angepasst werden.

## Enthalten
- Wochenplan nach den Regeln aus „Hinweise Wochentage“
- 1–2 kalte Abendessen Montag bis Freitag
- Einzelne Vorschläge austauschen
- Rezepte per Name oder Link ergänzen
- Arbeitszeit, warm/kalt, Kategorie, Favorit, Bewertung, vegetarisch und Aktiv-Status pflegen
- CSV-Export des Wochenplans

## Hinweis zur Datenspeicherung
Änderungen werden lokal im Unterordner `data` gespeichert. Für eine öffentliche Cloud-Bereitstellung sollte später eine persistente Datenbank wie Supabase oder PostgreSQL ergänzt werden.
