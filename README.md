# Gerenciador de Compras - MySQL / Streamlit Cloud

Esta versão troca o SQLite por MySQL usando SQLAlchemy + PyMySQL.

## Rodar local

```bash
pip install -r requirements.txt
```

Renomeie `.env.example` para `.env` e configure:

```txt
DB_URL=mysql+pymysql://USUARIO:SENHA@HOST:3306/BANCO?charset=utf8mb4
```

Depois:

```bash
streamlit run app.py
```

Na primeira execução, as tabelas são criadas automaticamente.

## Streamlit Cloud

Em `Settings > Secrets`, coloque:

```toml
DB_URL = "mysql+pymysql://USUARIO:SENHA@HOST:3306/BANCO?charset=utf8mb4"
APP_BASE_URL = "https://SEU-APP.streamlit.app"
ULTRAMSG_INSTANCE = "instance173813"
ULTRAMSG_TOKEN = "SEU_TOKEN_NOVO"
WHATSAPP_DESTINATARIOS = "5519999999999,5519888888888"
WHATSAPP_ENVIAR_PDF = "SIM"
```

## Observação importante

O banco MySQL fica persistente. Porém anexos, PDFs e logo ainda ficam salvos como arquivos locais. No Streamlit Cloud, o ideal é depois migrar esses arquivos para Cloudinary, Supabase Storage, S3 ou Google Drive.
