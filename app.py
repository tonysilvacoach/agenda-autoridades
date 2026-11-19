import re
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Agenda de Autoridades - Fórum", page_icon="🏛️", layout="wide"
)

st.title("🏛️ Agenda de Autoridades e Órgãos")

SHEET_ID = "1PWxjWALBtB_SNNHIwPErRu5mVn5PEkZv3B8MEP79Hfg"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

COLUNAS_OFICIAIS = [
    "Órgão / Instituição",
    "Cargo / Função",
    "Nome da Autoridade",
    "Telefone / WhatsApp",
    "E-mail Institucional",
    "Endereço / Local",
    "Observações",
]


@st.cache_data(ttl=15)
def carregar_dados():
  try:
    df = pd.read_csv(SHEET_URL, skiprows=4)
    df = df.dropna(subset=["Órgão / Instituição"])
    return df
  except Exception as e:
    st.error(
        f"Erro ao carregar dados da planilha: {e}. Verifique se a planilha"
        " está compartilhada como 'Qualquer pessoa com o link' (Leitor)."
    )
    return pd.DataFrame()


def organizar_lista_bruta(texto_bruto: str) -> pd.DataFrame:
  linhas = [linha.strip() for linha in texto_bruto.splitlines() if linha.strip()]
  registros = []

  regex_email = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
  regex_telefone = re.compile(r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?\d{4,5}-?\d{4}")

  for linha in linhas:
    emails = regex_email.findall(linha)
    email_encontrado = ", ".join(emails) if emails else ""
    linha_sem_email = regex_email.sub("", linha)

    telefones = regex_telefone.findall(linha_sem_email)
    telefone_encontrado = (
        " / ".join([t.strip() for t in telefones]) if telefones else ""
    )
    linha_limpa = regex_telefone.sub("", linha_sem_email)

    partes = [
        p.strip(" -|;,")
        for p in re.split(r"\s+[-–—|;]+\s+", linha_limpa)
        if p.strip(" -|;,")
    ]

    orgao = partes[0] if len(partes) >= 1 else linha_limpa.strip()
    cargo_ou_nome = partes[1] if len(partes) >= 2 else ""
    endereco_ou_obs = " | ".join(partes[2:]) if len(partes) >= 3 else ""

    registros.append({
        "Órgão / Instituição": orgao,
        "Cargo / Função": "",
        "Nome da Autoridade": cargo_ou_nome,
        "Telefone / WhatsApp": telefone_encontrado,
        "E-mail Institucional": email_encontrado,
        "Endereço / Local": endereco_ou_obs,
        "Observações": f"Importado de lista: {linha}",
    })

  return pd.DataFrame(registros, columns=COLUNAS_OFICIAIS)


aba_consulta, aba_alimentador = st.tabs(
    ["🔍 Consulta Rápida", "📥 Alimentador Automático de Lista"]
)

with aba_consulta:
  st.markdown(
      "Digite qualquer termo abaixo (nome do órgão, cargo, cidade ou inicial)"
      " para localizar instantaneamente:"
  )
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

    for _, row in df_filtrado.iterrows():
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
        elif autoridade != "nan" and autoridade:
          st.write(f"**Referência/Autoridade:** *{autoridade}*")

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
    st.warning("Aguardando dados da planilha...")

with aba_alimentador:
  st.subheader("📥 Organizador Automático de Listas e Contatos")
  st.markdown(
      "Cole abaixo uma lista solta ou texto com vários contatos (um por"
      " linha). O sistema separa automaticamente e-mails, telefones e partes do"
      " texto para você revisar e levar para a planilha."
  )

  texto_entrada = st.text_area(
      "Cole sua lista aqui:",
      height=180,
      placeholder=(
          "Exemplo:\n"
          "Promotoria de Justiça - Dr. Carlos Silva - (61) 3631-1234 -"
          " promotoria@mpgo.mp.br - Centro\n"
          "Delegacia de Polícia - Bel. Ana Souza - 61 99999-0000 -"
          " dp@pcgo.gov.br"
      ),
  )

  if st.button("✨ Organizar Lista Agora"):
    if texto_entrada.strip():
      df_organizado = organizar_lista_bruta(texto_entrada)
      st.success(f"{len(df_organizado)} linha(s) organizada(s)!")

      st.markdown("### Revise e ajuste se necessário antes de levar para a planilha:")
      df_editado = st.data_editor(
          df_organizado, num_rows="dynamic", use_container_width=True
      )

      tsv_para_colar = df_editado.to_csv(sep="\t", index=False, header=False)
      st.markdown("### 📋 Copiar pronto para colar direto no Google Sheets:")
      st.code(tsv_para_colar, language="text")

      csv_download = df_editado.to_csv(index=False).encode("utf-8-sig")
      st.download_button(
          label="⬇️ Baixar em CSV",
          data=csv_download,
          file_name="contatos_organizados.csv",
          mime="text/csv",
      )
    else:
      st.warning("Cole pelo menos uma linha de texto antes de organizar.")
