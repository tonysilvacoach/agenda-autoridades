import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Agenda de Autoridades - Fórum", page_icon="🏛️", layout="wide"
)

st.title("🏛️ Consulta Rápida de Autoridades e Órgãos")
st.markdown(
    "Digite qualquer termo abaixo (nome do órgão, cargo, cidade ou inicial) para"
    " localizar instantaneamente:"
)

SHEET_ID = "1PWxjWALBtB_SNNHIwPErRu5mVn5PEkZv3B8MEP79Hfg"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"


@st.cache_data(ttl=15)
def carregar_dados():
  try:
    df = pd.read_csv(SHEET_URL, skiprows=4)
    df = df.dropna(subset=["Órgão / Instituição"])
    return df
  except Exception as e:
    st.error(f"Erro ao carregar dados da planilha: {e}")
    return pd.DataFrame()


df = carregar_dados()

if not df.empty:
  termo = st.text_input(
      "🔍 Pesquisar Órgão, Autoridade ou Cargo:",
      "",
      placeholder="Ex: Fórum, Delegacia, Prefeitura, Juiz...",
  )

  if termo:
    mask = df.astype(str).apply(
        lambda x: x.str.contains(termo, case=False, na=False)
    ).any(axis=1)
    df_filtrado = df[mask]
  else:
    df_filtrado = df

  st.markdown(f"**Total de registros encontrados:** {len(df_filtrado)}")
  st.markdown("---")

  for idx, row in df_filtrado.iterrows():
    orgao = str(row.get("Órgão / Instituição", ""))
    cargo = str(row.get("Cargo / Função", ""))
    autoridade = str(row.get("Nome da Autoridade", ""))
    telefone = str(row.get("Telefone / WhatsApp", ""))
    email = str(row.get("E-mail Institucional", ""))
    endereco = str(row.get("Endereço / Local", ""))
    obs = str(row.get("Observações", ""))

    with st.container():
      st.subheader(f"🏢 {orgao}")
      if cargo != "nan" and cargo:
        st.write(
            f"**Cargo/Setor:** {cargo}"
            + (
                f" — *{autoridade}*"
                if autoridade != "nan" and autoridade
                else ""
            )
        )
      if endereco != "nan" and endereco:
        st.write(f"📍 **Local:** {endereco}")

      col1, col2 = st.columns(2)
      with col1:
        if telefone != "nan" and telefone:
          st.write(f"📞 **Telefone:** {telefone}")
      with col2:
        if email != "nan" and email:
          st.markdown(f"✉️ **E-mail:** [{email}](mailto:{email})")

      if obs != "nan" and obs:
        st.info(f"💡 **Observações:** {obs}")
      st.markdown("---")
else:
  st.warning("Carregando dados...")
