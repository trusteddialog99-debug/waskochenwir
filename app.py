import json, random, re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse, unquote
import pandas as pd
import streamlit as st

st.set_page_config(page_title='Unser Wochenkochplan',page_icon='🍽️',layout='wide')
BASE=Path(__file__).parent; DATA=BASE/'data'; DATA.mkdir(exist_ok=True)
RECIPES=DATA/'recipes.csv'; RULES=DATA/'rules.json'; SOURCE=BASE/'Chefkoch_Kochbuch.xlsx'
DAYS=['Montag','Dienstag','Mittwoch','Donnerstag','Freitag','Samstag','Sonntag']; MEALS=['Mittagessen','Abendessen']
DEFAULT={
'Montag':{'Mittagessen':[False,'Reste vom Wochenende',0],'Abendessen':[True,'warm',15]},
'Dienstag':{'Mittagessen':[False,'Reste vom Wochenende',0],'Abendessen':[True,'warm',30]},
'Mittwoch':{'Mittagessen':[False,'kein Vorschlag',0],'Abendessen':[True,'warm',30]},
'Donnerstag':{'Mittagessen':[False,'kein Vorschlag',0],'Abendessen':[True,'warm',15]},
'Freitag':{'Mittagessen':[False,'kein Vorschlag',0],'Abendessen':[True,'warm',30]},
'Samstag':{'Mittagessen':[True,'warm',60],'Abendessen':[True,'warm',30]},
'Sonntag':{'Mittagessen':[True,'warm',60],'Abendessen':[True,'warm',30]},'_global':{'cold_min':1,'cold_max':2}}

def infer(name):
 n=name.lower(); cold=any(x in n for x in ['salat','wrap','müsli','aufstrich','guacamole','hummus'])
 veg=not any(x in n for x in ['hähn','huhn','hack','fleisch','schinken','lachs','fisch','dorade','zander','steak','gulasch','cabanossi','souvlaki','pute','speck','wurst','geschnetzeltes','gans'])
 cat='Kaltgericht' if cold else ('Suppe & Eintopf' if any(x in n for x in ['suppe','eintopf']) else ('Nudeln' if any(x in n for x in ['nudel','pasta','spaghetti','penne','tortell','lasagne']) else 'Hauptgericht'))
 mins=15 if any(x in n for x in ['schnell','blitz','salat','wrap']) else (45 if any(x in n for x in ['lasagne','roulade','gulasch','moussaka']) else 30)
 return cat,not cold,mins,veg

def seed():
 if RECIPES.exists(): return
 d=pd.read_excel(SOURCE,sheet_name='Mein Kochbuch',engine='openpyxl').fillna(''); rows=[]
 for i,r in d.iterrows():
  cat,warm,mins,veg=infer(str(r['Name'])); rows.append([i+1,r['Name'],r['Rezept-Link'],r['Persönliche Notiz'],cat,warm,mins,veg,False,True,3])
 pd.DataFrame(rows,columns=['ID','Name','Link','Notiz','Kategorie','Warm','Arbeitszeit_Min','Vegetarisch','Favorit','Aktiv','Bewertung']).to_csv(RECIPES,index=False)
def recipes(): seed(); return pd.read_csv(RECIPES).fillna('')
def normalize_rules(rs):
 # Migriert alle bisher verwendeten Regel-Formate auf das aktuelle Listenformat:
 # [aktiv, modus, max_minuten].
 defaults=DEFAULT
 for day in DAYS:
  day_rules=rs.setdefault(day,{})
  for meal in MEALS:
   fallback=defaults[day][meal]
   r=day_rules.get(meal,fallback)
   if isinstance(r,dict):
    active=bool(r.get('active',fallback[0]))
    mode=r.get('mode',fallback[1])
    max_minutes=int(r.get('max_minutes',fallback[2]) or 0)
    day_rules[meal]=[active,mode,max_minutes]
   elif isinstance(r,(list,tuple)) and len(r)>=3:
    day_rules[meal]=[bool(r[0]),r[1],int(r[2] or 0)]
   else:
    day_rules[meal]=list(fallback)
 g=rs.setdefault('_global',{})
 g['cold_min']=int(g.get('cold_min',g.get('cold_weekday_dinners_min',1)))
 g['cold_max']=int(g.get('cold_max',g.get('cold_weekday_dinners_max',2)))
 if g['cold_min']>g['cold_max']:
  g['cold_min'],g['cold_max']=g['cold_max'],g['cold_min']
 return rs

def rules():
 if not RULES.exists():
  RULES.write_text(json.dumps(DEFAULT,ensure_ascii=False,indent=2),encoding='utf-8')
 rs=json.loads(RULES.read_text(encoding='utf-8'))
 rs=normalize_rules(rs)
 # Migration dauerhaft speichern, damit Folgeaufrufe dasselbe Format verwenden.
 RULES.write_text(json.dumps(rs,ensure_ascii=False,indent=2),encoding='utf-8')
 return rs

def truth(s): return str(s).lower() in ['true','1']
def pool(df,rule,used,cold=False):
 x=df[df.Aktiv.map(truth)&~df.ID.astype(str).isin({str(i) for i in used})].copy(); mx=int(rule[2])
 if mx:x=x[pd.to_numeric(x.Arbeitszeit_Min,errors='coerce').fillna(30)<=mx]
 return x[x.Warm.map(truth)==(False if cold else rule[1]=='warm')]
def pick(x):
 if x.empty:return None
 w=x.apply(lambda r:(2.5 if truth(r.Favorit) else 1)*max(1,float(r.Bewertung or 3))*(1.15 if str(r.Notiz).strip() else 1),axis=1)
 return x.sample(1,weights=w).iloc[0]
def make_plan(df,rs):
 used=[]; out=[]; k=random.randint(int(rs['_global']['cold_min']),int(rs['_global']['cold_max'])); cold=set(random.sample(DAYS[:5],min(k,5)))
 for day in DAYS:
  for meal in MEALS:
   r=rs[day][meal]
   if not r[0]:out.append([day,meal,r[1],'','','','']);continue
   is_cold=meal=='Abendessen' and day in cold; p=pick(pool(df,r,used,is_cold))
   if p is None: p=pick(pool(df,r,used,False))
   if p is None:out.append([day,meal,'Kein passendes Rezept','','','','']);continue
   used.append(p.ID); out.append([day,meal,p.Name,p.ID,p.Link,f'{int(float(p.Arbeitszeit_Min))} Min.','warm' if truth(p.Warm) else 'kalt'])
 return pd.DataFrame(out,columns=['Tag','Mahlzeit','Rezept','ID','Link','Arbeitszeit','Warm/Kalt'])

st.title('🍽️ Unser Wochenkochplan'); df=recipes(); rs=rules()
page=st.sidebar.radio('Bereich',['Wochenplan','Rezepte','Regeln'])
if page=='Wochenplan':
 week=st.date_input('Woche ab Montag',date.today()-timedelta(days=date.today().weekday()))
 if st.button('✨ Wochenplan erstellen',type='primary') or 'plan' not in st.session_state:st.session_state.plan=make_plan(df,rs)
 plan=st.session_state.plan
 for day in DAYS:
  st.subheader(day); cols=st.columns(2)
  for j,meal in enumerate(MEALS):
   idx=plan.index[(plan.Tag==day)&(plan.Mahlzeit==meal)][0]; row=plan.loc[idx]
   with cols[j]:
    st.markdown(f'**{meal}**'); st.markdown(f"[{row.Rezept}]({row.Link})" if row.Link else row.Rezept)
    if row.Arbeitszeit:st.caption(f'{row["Warm/Kalt"]} · {row.Arbeitszeit}')
    if row.ID!='' and st.button('🔄 Austauschen',key=f'{day}{meal}'):
     used=plan.loc[plan.index!=idx,'ID'].tolist(); p=pick(pool(df,rs[day][meal],used,row['Warm/Kalt']=='kalt'))
     if p is not None:plan.loc[idx]=[day,meal,p.Name,p.ID,p.Link,f'{int(float(p.Arbeitszeit_Min))} Min.','warm' if truth(p.Warm) else 'kalt'];st.rerun()
  st.divider()
 st.download_button('⬇️ Wochenplan als CSV',plan.drop(columns='ID').to_csv(index=False).encode('utf-8-sig'),f'Wochenplan_{week}.csv')
elif page=='Rezepte':
 st.subheader('Neues Rezept hinzufügen')
 with st.form('new'):
  c1,c2=st.columns(2); name=c1.text_input('Rezeptname'); link=c2.text_input('Link (optional)')
  c1,c2,c3=st.columns(3); mins=c1.number_input('Arbeitszeit',5,180,30,5); warm=c2.selectbox('Art',['warm','kalt']); fav=c3.checkbox('Lieblingsrezept')
  note=st.text_area('Notiz'); save=st.form_submit_button('Speichern',type='primary')
  if save:
   final=name.strip() or unquote(urlparse(link).path.rstrip('/').split('/')[-1]).replace('.html','').replace('-',' ').title()
   if final:
    row={'ID':int(pd.to_numeric(df.ID).max())+1,'Name':final,'Link':link,'Notiz':note,'Kategorie':'Hauptgericht','Warm':warm=='warm','Arbeitszeit_Min':mins,'Vegetarisch':True,'Favorit':fav,'Aktiv':True,'Bewertung':3}
    pd.concat([df,pd.DataFrame([row])],ignore_index=True).to_csv(RECIPES,index=False);st.rerun()
 st.subheader(f'Rezeptsammlung ({len(df)})')
 sort_col, sort_dir = st.columns([3, 1])
 sortable_columns=['Name','Kategorie','Arbeitszeit_Min','Vegetarisch','Favorit','Aktiv','Bewertung']
 sort_by=sort_col.selectbox('Sortieren nach',sortable_columns,index=0)
 ascending=sort_dir.toggle('Aufsteigend',value=True)
 # Stabile Sortierung: Bei gleichen Werten wird zusätzlich nach Rezeptname sortiert.
 if sort_by=='Name':
  shown=df.sort_values('Name',ascending=ascending,kind='stable',key=lambda x:x.astype(str).str.lower())
 else:
  shown=df.sort_values([sort_by,'Name'],ascending=[ascending,True],kind='stable')
 edited=st.data_editor(shown,use_container_width=True,hide_index=True,num_rows='dynamic',column_config={'Link':st.column_config.LinkColumn('Link'),'Warm':st.column_config.CheckboxColumn('Warm'),'Vegetarisch':st.column_config.CheckboxColumn('Vegetarisch'),'Favorit':st.column_config.CheckboxColumn('Favorit'),'Aktiv':st.column_config.CheckboxColumn('Aktiv'),'Bewertung':st.column_config.NumberColumn('Bewertung',min_value=1,max_value=5,step=1),'Arbeitszeit_Min':st.column_config.NumberColumn('Arbeitszeit (Min.)',min_value=5,max_value=180,step=5)})
 if st.button('Änderungen speichern',type='primary'):
  edited.to_csv(RECIPES,index=False)
  st.success('Gespeichert.')
else:
 st.info('Voreinstellungen entsprechen dem Arbeitsblatt „Hinweise Wochentage“.')
 for day in DAYS:
  st.markdown(f'### {day}'); cols=st.columns(2)
  for j,meal in enumerate(MEALS):
   r=rs[day][meal]
   with cols[j]:
    r[0]=st.checkbox(f'{meal}: Vorschlag',r[0],key=f'a{day}{meal}'); r[1]=st.selectbox('Art',['warm','kalt','Reste vom Wochenende','kein Vorschlag'],index=['warm','kalt','Reste vom Wochenende','kein Vorschlag'].index(r[1]),key=f'm{day}{meal}'); r[2]=st.number_input('Max. Minuten',0,180,int(r[2]),5,key=f't{day}{meal}')
 c1,c2=st.columns(2);rs['_global']['cold_min']=c1.number_input('Mind. kalte Abendessen Mo–Fr',0,5,int(rs['_global']['cold_min']));rs['_global']['cold_max']=c2.number_input('Max. kalte Abendessen Mo–Fr',0,5,int(rs['_global']['cold_max']))
 if st.button('Regeln speichern',type='primary'):RULES.write_text(json.dumps(rs,ensure_ascii=False,indent=2),encoding='utf-8');st.success('Gespeichert.')
