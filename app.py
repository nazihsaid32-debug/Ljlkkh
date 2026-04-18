import streamlit as st
import pandas as pd
from datetime import datetime, time
import plotly.express as px
import io

# 1. Configuration
st.set_page_config(page_title="AKHFENNIRE 1 - Manager", layout="wide")

# 2. Interface
st.image("https://i1.hespress.com/wp-content/uploads/2020/02/energie___olienne_321369521.jpg", use_container_width=True)
st.markdown("<h1 style='text-align: center; color: #1E3A8A;'>Gestionnaire d'Alarmes AKHFENNIRE 1</h1>", unsafe_allow_html=True)

# 3. Sidebar
st.sidebar.header("🗓️ Paramètres Généraux")
target_date = st.sidebar.date_input("Date de travail", datetime.now())

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Configuration Cas Spécial")
selected_wtgs = st.sidebar.multiselect("Turbines concernées", [f"WTG{str(i).zfill(2)}" for i in range(1, 62)])
cs_start_h = st.sidebar.time_input("Heure de début (CS)", time(8, 0))
cs_end_h = st.sidebar.time_input("Heure de fin (CS)", time(17, 0))
cs_resp = st.sidebar.selectbox("Responsable (CS)", ["EEM", "WTG", "ONEE"])
cs_impact = st.sidebar.selectbox("Nature de l'impact", ["Déclenchement", "Bridage", "Inspection Générale"])

# 4. Base Alarmes
st.sidebar.markdown("---")
st.sidebar.header("📋 Base des Codes (Excel)")
base_file = st.sidebar.file_uploader("Charger Base Alarmes", type=["xlsx"])

dict_alarme = {}
if base_file:
    try:
        df_base = pd.read_excel(base_file)
        df_base.columns = [str(c).strip() for c in df_base.columns]
        for _, row in df_base.iterrows():
            code = str(row['cod alarm']).strip()
            resp = str(row['responsable']).strip()
            # منطق الأولوية
            if "EEM" in resp.upper(): pri = 1
            elif "CORRMAINT" in resp.upper(): pri = 2
            elif "MANUALSTOP" in resp.upper(): pri = 3
            else: pri = 4
            dict_alarme[code] = {'resp': resp, 'pri': pri}
    except: st.sidebar.error("Erreur Base Excel")

# 5. Journal des Alarmes
uploaded_file = st.file_uploader("📂 Charger le Journal des Alarmes", type=["xlsx"])

if uploaded_file:
    try:
        raw_df = pd.read_excel(uploaded_file, header=None)
        header_row_index = None
        for i, row in raw_df.iterrows():
            if row.astype(str).str.contains('WTG0', case=False).any():
                header_row_index = i
                break
        
        if header_row_index is not None:
            df = pd.read_excel(uploaded_file, skiprows=header_row_index)
            df = df.dropna(how='all', axis=1)
            df.columns = ['WTG', 'Code', 'Text', 'Start', 'End'] + list(df.columns[5:])
            
            df['S_DT'] = pd.to_datetime(df['Start'], dayfirst=True, errors='coerce')
            df['E_DT'] = pd.to_datetime(df['End'], dayfirst=True, errors='coerce')
            
            d_day_start = datetime.combine(target_date, time(0, 0))
            d_day_end = datetime.combine(target_date, time(23, 59, 59))
            
            df = df.dropna(subset=['S_DT', 'E_DT'])
            df = df[(df['S_DT'] <= d_day_end) & (df['E_DT'] >= d_day_start)].copy()

            # تجميع كل البيانات (Excel + Cas Spécial)
            all_events = []
            for wtg in selected_wtgs:
                s_cs = datetime.combine(target_date, cs_start_h)
                e_cs = datetime.combine(target_date, cs_end_h)
                all_events.append({'WTG': wtg, 'Code': 'CS', 'Text': cs_impact, 'Start': s_cs, 'End': e_cs, 'Resp': cs_resp, 'Impact': cs_impact, 'Pri': 0})

            for _, row in df.iterrows():
                s = max(row['S_DT'], d_day_start)
                e = min(row['E_DT'], d_day_end)
                if s < e:
                    info = dict_alarme.get(str(row['Code']).strip(), {'resp': 'WTG', 'pri': 4})
                    all_events.append({'WTG': row['WTG'], 'Code': row['Code'], 'Text': row['Text'], 'Start': s, 'End': e, 'Resp': info['resp'], 'Impact': '-', 'Pri': info['pri']})

            # --- الخوارزمية الذكية لإزالة التداخل ---
            processed_data = []
            events_df = pd.DataFrame(all_events)
            
            if not events_df.empty:
                for wtg, group in events_df.groupby('WTG'):
                    # ترتيب حسب الوقت ثم الأولوية (الأهم أولاً)
                    group = group.sort_values(by=['Start', 'Pri'])
                    
                    current_timeline = []
                    for _, ev in group.iterrows():
                        if not current_timeline:
                            current_timeline.append(ev.to_dict())
                        else:
                            last = current_timeline[-1]
                            # فحص التداخل
                            if ev['Start'] < last['End']:
                                if ev['Pri'] < last['Pri']: # الجديد أهم: قص القديم
                                    last['End'] = ev['Start']
                                    current_timeline.append(ev.to_dict())
                                elif ev['Pri'] == last['Pri']: # نفس الأهمية: دمج الوقت
                                    last['End'] = max(last['End'], ev['End'])
                                else: # الجديد أقل أهمية: يبدأ بعد انتهاء القديم
                                    if ev['End'] > last['End']:
                                        ev['Start'] = last['End']
                                        current_timeline.append(ev.to_dict())
                            else: # لا يوجد تداخل
                                current_timeline.append(ev.to_dict())
                    processed_data.extend(current_timeline)

            final_df = pd.DataFrame(processed_data)
            final_df['Durée_H'] = (final_df['End'] - final_df['Start']).dt.total_seconds() / 3600
            
            # العرض
            st.success("✅ Analyse sans chevauchements terminée")
            st.dataframe(final_df[['WTG', 'Code', 'Text', 'Start', 'End', 'Resp', 'Impact', 'Durée_H']])

            # الرسم البياني
            stats = final_df.groupby('WTG')['Durée_H'].sum().reset_index()
            all_wtgs_list = pd.DataFrame({'WTG': [f"WTG{str(i).zfill(2)}" for i in range(1, 62)]})
            stats = pd.merge(all_wtgs_list, stats, on='WTG', how='left').fillna(0)
            stats['Heures_Marche'] = 24 - stats['Durée_H']
            
            fig = px.bar(stats, x='WTG', y='Heures_Marche', color='Heures_Marche', color_continuous_scale='RdYlGn', range_y=[0, 24])
            st.plotly_chart(fig, use_container_width=True)

            # Export
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                final_df.to_excel(writer, index=False)
            st.download_button("📥 Télécharger le Rapport Pro", data=output.getvalue(), file_name=f"Rapport_Final.xlsx")

    except Exception as e:
        st.error(f"Erreur : {e}")
