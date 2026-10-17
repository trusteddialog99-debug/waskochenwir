import json, random, re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse, unquote

import pandas as pd
import streamlit as st

st.set_page_config(page_title='Unser Wochenkochplan', page_icon='🍽️', layout='wide')
BASE = Path(__file__).parent
DATA = BASE / 'data'
DATA.mkdir(exist_ok=True)
RECIPES_CSV = DATA / 'recipes.csv'
RULES_JSON = DATA / 'rules.json'
SOURCE_XLSX = BASE / 'Chefkoch_Kochbuch_237_Rezepte.xlsx'
DAYS = ['Montag','Dienstag','Mittwoch','Donnerstag','Freitag','Samstag','Sonntag']
MEALS = ['Mittagessen','Abendessen']

DEFAULT_RULES = {
 'Montag': {'Mittagessen': {'active': False,'mode':'Reste vom Wochenende','max_minutes':0}, 'Abendessen': {'active':True,'mode':'warm','max_minutes':15}},
 'Dienstag': {'Mittagessen': {'active': False,'mode':'Reste vom Wochenende','max_minutes':0}, 'Abendessen': {'active':True,'mode':'warm','max_minutes':30}},
 'Mittwoch': {'Mittagessen': {'active': False,'mode':'kein Vorschlag','max_minutes':0}, 'Abendessen': {'active':True,'mode':'warm','max_minutes':30}},
 'Donnerstag': {'Mittagessen': {'active': False,'mode':'kein Vorschlag','max_minutes':0}, 'Abendessen': {'active':True,'mode':'warm','max_minutes':15}},
 'Freitag': {'Mittagessen': {'active': False,'mode':'kein Vorschlag','max_minutes':0}, 'Abendessen': {'active':True,'mode':'warm','max_minutes':30}},
 'Samstag': {'Mittagessen': {'active': True,'mode':'warm','max_minutes':60}, 'Abendessen': {'active':True,'mode':'warm','max_minutes':30}},
 'Sonntag': {'Mittagessen': {'active': True,'mode':'warm','max_minutes':60}, 'Abendessen': {'active':True,'mode':'warm','max_minutes':30}},
 '_global': {'cold_weekday_dinners_min':1,'cold_weekday_dinners_max':2,'avoid_repeat_weeks':3}
}

def infer_meta(name):
    n=name.lower()
    sweet=any(x in n for x in ['kuchen','muffin','keks','plätz','torte','waffel','praline','eis','crumble','lebkuchen','mandel','marzipan'])
    cold=any(x in n for x in ['salat','brot','wrap','müsli','pudding','aufstrich','guacamole','hummus']) and not any(x in n for x in ['auflauf','suppe'])
    veg=not any(x in n for x in ['hähn','huhn','hack','fleisch','schinken','lachs','fisch','dorade','zander','steak','gulasch','cabanossi','souvlaki','pute','speck','wurst','geschnetzeltes','gans'])
    if sweet: cat='Backen & Süßes'
    elif any(x in n for x in ['suppe','eintopf']): cat='Suppe & Eintopf'
    elif any(x in n for x in ['nudel','pasta','spaghetti','penne','tortell','lasagne']): cat='Nudeln'
    elif any(x in n for x in ['reis','risotto','couscous']): cat='Reis & Getreide'
    elif cold: cat='Kaltgericht'
    else: cat='Hauptgericht'
    mins=15 if any(x in n for x in ['schnell','blitz','ruckzuck','salat','brot','wrap']) else (45 if any(x in n for x in ['lasagne','roulade','gulasch','moussaka']) else 30)
    return {'Kategorie':cat,'Warm':not cold,'Arbeitszeit_Min':mins,'Vegetarisch':veg,'Favorit':False,'Aktiv':not sweet,'Bewertung':3}

def seed_recipes():
    if RECIPES_CSV.exists(): return
    df=pd.read_excel(SOURCE_XLSX, sheet_name='Mein Kochbuch', engine='openpyxl').fillna('')
    rows=[]
    for _,r in df.iterrows():
        m=infer_meta(str(r['Name']))
        rows.append({'ID':len(rows)+1,'Name':r['Name'],'Link':r['Rezept-Link'],'Notiz':r['Persönliche Notiz'],**m})
    pd.DataFrame(rows).to_csv(RECIPES_CSV,index=False)

def load_rules():
    if not RULES_JSON.exists(): RULES_JSON.write_text(json.dumps(DEFAULT_RULES,ensure_ascii=False,indent=2),encoding='utf-8')
    return json.loads(RULES_JSON.read_text(encoding='utf-8'))

def load_recipes():
    seed_recipes(); return pd.read_csv(RECIPES_CSV).fillna('')

def save_recipes(df): df.to_csv(RECIPES_CSV,index=False)
def save_rules(r): RULES_JSON.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')

def monday_of(d): return d-timedelta(days=d.weekday())

def candidates(df, rule, used, cold_override=False):
    x=df[df['Aktiv'].astype(str).str.lower().isin(['true','1'])].copy()
    x=x[~x['ID'].astype(str).isin({str(v) for v in used})]
    x=x[x['Kategorie']!='Backen & Süßes']
    maxm=int(rule.get('max_minutes',30))
    if maxm: x=x[pd.to_numeric(x['Arbeitszeit_Min'],errors='coerce').fillna(30)<=maxm]
    want_warm=False if cold_override else rule.get('mode')=='warm'
    warm=x['Warm'].astype(str).str.lower().isin(['true','1'])
    x=x[warm==want_warm]
    return x

def choose(df):
    if df.empty: return None
    weights=[]
    for _,r in df.iterrows():
        fav=2.5 if str(r['Favorit']).lower() in ['true','1'] else 1
        rating=max(1,float(r.get('Bewertung',3) or 3))
        note=1.15 if str(r.get('Notiz','')).strip() else 1
        weights.append(fav*rating*note)
    return df.sample(1,weights=weights).iloc[0]

def generate_plan(df,rules):
    used=[]; plan=[]
    cold_count=random.randint(int(rules['_global']['cold_weekday_dinners_min']),int(rules['_global']['cold_weekday_dinners_max']))
    cold_days=set(random.sample(DAYS[:5],k=min(cold_count,5)))
    for day in DAYS:
        for meal in MEALS:
            rule=rules[day][meal]
            if not rule['active']:
                plan.append({'Tag':day,'Mahlzeit':meal,'Rezept':rule['mode'],'ID':'','Link':'','Arbeitszeit':'','Warm/Kalt':''}); continue
            cold=(meal=='Abendessen' and day in cold_days)
            c=candidates(df,rule,used,cold)
            if c.empty and cold: c=candidates(df,rule,used,False)
            pick=choose(c)
            if pick is None:
                plan.append({'Tag':day,'Mahlzeit':meal,'Rezept':'Kein passendes Rezept gefunden','ID':'','Link':'','Arbeitszeit':'','Warm/Kalt':''})
            else:
                used.append(pick['ID']); plan.append({'Tag':day,'Mahlzeit':meal,'Rezept':pick['Name'],'ID':pick['ID'],'Link':pick['Link'],'Arbeitszeit':f"{int(float(pick['Arbeitszeit_Min']))} Min.",'Warm/Kalt':'warm' if str(pick['Warm']).lower() in ['true','1'] else 'kalt'})
    return plan

def slug_name(url):
    slug=unquote(urlparse(url).path.rstrip('/').split('/')[-1]); slug=re.sub(r'\.html$','',slug); return slug.replace('-',' ').strip().title()

st.title('🍽️ Unser Wochenkochplan')
st.caption('Lieblingsrezepte verwalten, Regeln anpassen und den Wochenplan flexibel neu zusammenstellen.')
df=load_recipes(); rules=load_rules()
page=st.sidebar.radio('Bereich',['Wochenplan','Rezepte','Regeln'])

if page=='Wochenplan':
    week=st.date_input('Woche ab Montag',monday_of(date.today()))
    c1,c2=st.columns([1,2])
    if c1.button('✨ Wochenplan erstellen',type='primary',use_container_width=True): st.session_state.plan=generate_plan(df,rules)
    if 'plan' not in st.session_state: st.session_state.plan=generate_plan(df,rules)
    plan=st.session_state.plan
    for day in DAYS:
        st.subheader(day)
        cols=st.columns(2)
        for j,meal in enumerate(MEALS):
            item=next(x for x in plan if x['Tag']==day and x['Mahlzeit']==meal)
            with cols[j]:
                st.markdown(f'**{meal}**')
                if item['Link']: st.markdown(f"[{item['Rezept']}]({item['Link']})")
                else: st.write(item['Rezept'])
                if item['Arbeitszeit']: st.caption(f"{item['Warm/Kalt']} · {item['Arbeitszeit']}")
                if item['ID']!='' and st.button('🔄 Austauschen',key=f'{day}-{meal}'):
                    rule=rules[day][meal]; used=[x['ID'] for x in plan if x['ID']!='' and x is not item]
                    cold=item['Warm/Kalt']=='kalt'; pick=choose(candidates(df,rule,used,cold))
                    if pick is not None:
                        item.update({'Rezept':pick['Name'],'ID':pick['ID'],'Link':pick['Link'],'Arbeitszeit':f"{int(float(pick['Arbeitszeit_Min']))} Min.",'Warm/Kalt':'warm' if str(pick['Warm']).lower() in ['true','1'] else 'kalt'})
                        st.rerun()
        st.divider()
    export=pd.DataFrame(plan)[['Tag','Mahlzeit','Rezept','Arbeitszeit','Warm/Kalt','Link']]
    st.download_button('⬇️ Wochenplan als CSV',export.to_csv(index=False).encode('utf-8-sig'),f'Wochenplan_{week}.csv','text/csv')

elif page=='Rezepte':
    st.subheader('Neues Rezept hinzufügen')
    with st.form('add'):
        c1,c2=st.columns(2); name=c1.text_input('Rezeptname'); link=c2.text_input('Link (optional)')
        c3,c4,c5=st.columns(3); mins=c3.number_input('Arbeitszeit in Minuten',5,180,30,5); warm=c4.selectbox('Art',['warm','kalt']); cat=c5.selectbox('Kategorie',['Hauptgericht','Nudeln','Reis & Getreide','Suppe & Eintopf','Kaltgericht','Backen & Süßes'])
        c6,c7,c8=st.columns(3); veg=c6.checkbox('Vegetarisch',True); fav=c7.checkbox('Lieblingsrezept'); rating=c8.slider('Bewertung',1,5,3)
        note=st.text_area('Persönliche Notiz'); submit=st.form_submit_button('Rezept speichern',type='primary')
        if submit:
            final=name.strip() or (slug_name(link) if link.strip() else '')
            if not final: st.error('Bitte Rezeptname oder Link eingeben.')
            else:
                row={'ID':int(pd.to_numeric(df['ID']).max())+1,'Name':final,'Link':link.strip(),'Notiz':note,'Kategorie':cat,'Warm':warm=='warm','Arbeitszeit_Min':mins,'Vegetarisch':veg,'Favorit':fav,'Aktiv':cat!='Backen & Süßes','Bewertung':rating}
                df=pd.concat([df,pd.DataFrame([row])],ignore_index=True); save_recipes(df); st.success(f'„{final}“ wurde gespeichert.'); st.rerun()
    st.subheader(f'Rezeptsammlung ({len(df)})')
    edited=st.data_editor(df,use_container_width=True,hide_index=True,num_rows='dynamic',column_config={'Link':st.column_config.LinkColumn('Link'),'Warm':st.column_config.CheckboxColumn('Warm'),'Vegetarisch':st.column_config.CheckboxColumn('Vegetarisch'),'Favorit':st.column_config.CheckboxColumn('Favorit'),'Aktiv':st.column_config.CheckboxColumn('Für Kochplan aktiv'),'Bewertung':st.column_config.NumberColumn('Bewertung',min_value=1,max_value=5,step=1),'Arbeitszeit_Min':st.column_config.NumberColumn('Arbeitszeit (Min.)',min_value=5,max_value=180,step=5)})
    if st.button('Änderungen speichern',type='primary'): save_recipes(edited); st.success('Rezeptsammlung gespeichert.')

else:
    st.subheader('Regeln für Wochentage')
    st.info('Voreingestellt nach dem Arbeitsblatt „Hinweise Wochentage“: werktags kein Mittagessen, am Wochenende Mittagessen bis 60 Minuten, Abendessen je nach Tag 15 oder 30 Minuten, dazu 1–2 kalte Abendessen von Montag bis Freitag.')
    for day in DAYS:
        st.markdown(f'### {day}')
        cols=st.columns(2)
        for j,meal in enumerate(MEALS):
            r=rules[day][meal]
            with cols[j]:
                r['active']=st.checkbox(f'{meal}: Vorschlag erstellen',value=r['active'],key=f'a-{day}-{meal}')
                r['mode']=st.selectbox('Art',options=['warm','kalt','Reste vom Wochenende','kein Vorschlag'],index=['warm','kalt','Reste vom Wochenende','kein Vorschlag'].index(r['mode']),key=f'm-{day}-{meal}')
                r['max_minutes']=st.number_input('Max. Arbeitszeit',0,180,int(r['max_minutes']),5,key=f't-{day}-{meal}')
    st.markdown('### Globale Regeln')
    g=rules['_global']; c1,c2=st.columns(2)
    g['cold_weekday_dinners_min']=c1.number_input('Mindestens kalte Abendessen Mo–Fr',0,5,int(g['cold_weekday_dinners_min']))
    g['cold_weekday_dinners_max']=c2.number_input('Höchstens kalte Abendessen Mo–Fr',0,5,int(g['cold_weekday_dinners_max']))
    if st.button('Regeln speichern',type='primary'): save_rules(rules); st.success('Regeln gespeichert.')
