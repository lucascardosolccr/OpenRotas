# Autenticação — Como configurar

Sistema de cadastro, login, sessão, perfil e recuperação de senha, construído sobre o
[Supabase](https://supabase.com) (Postgres + Auth gerenciados, free tier gratuito) e o
envio de e-mail SMTP já usado pela aplicação.

## 1. Criar o projeto Supabase (gratuito)

1. Crie uma conta em [supabase.com](https://supabase.com) (ou entre com GitHub).
2. **New project** → escolha um nome, uma senha forte para o banco (guarde-a — não é a
   mesma coisa que a `SUPABASE_ANON_KEY` abaixo) e a região mais próxima (ex.: São Paulo).
3. Aguarde o projeto provisionar (1-2 minutos).

## 2. Rodar o schema SQL

1. No painel do projeto: **SQL Editor** → **New query**.
2. Copie TODO o conteúdo de [`auth/schema.sql`](./schema.sql) deste repositório, cole e
   clique em **Run**.
3. Isso cria a tabela `public.profiles`, as políticas de segurança (Row Level Security) e
   os triggers que sincronizam automaticamente o perfil com o cadastro/login — nenhum passo
   manual adicional é necessário no banco.

## 3. Pegar as credenciais da API

Painel do projeto → **Project Settings → API**:

* `Project URL` → vira `SUPABASE_URL`.
* `anon` `public` key → vira `SUPABASE_ANON_KEY`.

⚠️ **Nunca** use a `service_role` key na aplicação — ela ignora as políticas de segurança
do banco e é só para uso administrativo/servidor confiável.

## 4. (Opcional, recomendado) Configurar e-mail com a marca da aplicação

Por padrão, o Supabase envia os e-mails de autenticação (confirmação, recuperação de
senha) pelo próprio servidor dele, com limite baixo (poucos e-mails/hora) e remetente
genérico. Para usar o mesmo e-mail Gmail já configurado nesta aplicação (`EMAIL_SISTEMA`/
`SENHA_APP`, hoje usado no recurso de tickets):

1. Painel do projeto → **Project Settings → Auth → SMTP Settings** → ative "Enable Custom
   SMTP".
2. Host: `smtp.gmail.com` · Porta: `587` · Usuário: seu `EMAIL_SISTEMA` · Senha: sua
   `SENHA_APP` (a mesma [senha de aplicativo](https://myaccount.google.com/apppasswords)
   já usada pela aplicação, **não** a senha normal da conta Google).
3. (Opcional) **Authentication → Email Templates** → edite o template "Reset Password"
   para exibir o **código** `{{ .Token }}` em vez do link padrão — é isso que faz o fluxo
   de recuperação por código de 6 dígitos funcionar (em vez de um link "mágico").

Sem este passo, a aplicação continua funcionando — só usa o remetente/limites padrão do
Supabase em vez do Gmail configurado.

## 5. Configurar os secrets da aplicação

Copie [`auth/secrets.toml.example`](./secrets.toml.example) para `.streamlit/secrets.toml`
(raiz do repositório — arquivo já no `.gitignore`, nunca é commitado) e preencha com os
valores reais dos passos 3-4.

Em produção (Streamlit Community Cloud): cole o mesmo conteúdo, com os valores reais, em
**Settings → Secrets** do seu app, no painel do Streamlit Cloud. Use um projeto Supabase
**separado** do de desenvolvimento, se possível (evita misturar dados de teste com dados
reais de usuários).

## 6. Instalar a dependência

```bash
pip install -r requirements.txt
```

(`supabase` já está listado no `requirements.txt`.)

## 7. Testar localmente

```bash
streamlit run streamlit_app.py
```

A aplicação deve abrir direto na tela de login. Clique em **Criar uma conta**, preencha o
formulário e confirme que:

* a conta aparece em **Authentication → Users** no painel do Supabase;
* uma linha correspondente aparece em **Table Editor → profiles**;
* o login funciona com o e-mail/senha cadastrados;
* **Esqueci minha senha** envia um código de 6 dígitos por e-mail e permite redefinir.

## Arquitetura (resumo)

```
auth/
├── validators.py       # validação/normalização pura (nome, e-mail, telefone, CEP, senha) — sem I/O
├── supabase_client.py  # cliente Supabase compartilhado (cacheado), lê credenciais de st.secrets
├── auth_service.py     # cadastro/login/logout/recuperação/perfil — só fala com o Supabase Auth
├── email_service.py    # e-mail de boas-vindas (SMTP Gmail já usado pela aplicação)
├── session_manager.py  # st.session_state + o PORTÃO exigir_autenticacao() + telas de auth/perfil
├── schema.sql           # tabela de perfil + RLS + triggers (rodar uma vez no Supabase)
├── secrets.toml.example
└── tests/                # testes offline (validators) e com cliente Supabase mockado (auth_service)
```

### Perfil e troca de e-mail

Com a sessão aberta, o botão **Perfil** na barra lateral abre uma tela onde o usuário vê/edita
nome, telefone e endereço (`auth_service.obter_perfil`/`atualizar_perfil`) e pode solicitar a
troca do e-mail de login. A troca de e-mail nunca é imediata: `atualizar_perfil` recusa
explicitamente a chave `email`, e o pedido de troca (`auth_service.solicitar_alteracao_email`)
dispara a confirmação nativa do Supabase Auth para o **novo** endereço — a alteração só é
efetivada quando o usuário clica no link recebido lá. Nenhum código desta aplicação decide
quando a troca vale; isso é delegado inteiramente ao Supabase, como todo o resto da autenticação.

A senha do usuário **nunca** passa pelo código desta aplicação em texto puro além do
formulário — é enviada diretamente ao Supabase Auth via HTTPS, que já faz o hash (bcrypt)
e armazenamento seguro. Este módulo nunca reimplementa hash de senha, geração/validação de
token de recuperação, nem comparação de credenciais — tudo isso é delegado ao Supabase
Auth, testado em produção por milhares de aplicações.

## Limitações conhecidas (documentadas, não escondidas)

* A sessão vive em `st.session_state`: sobrevive a reruns/F5 na mesma aba, mas se perde ao
  fechar o navegador. Uma persistência "lembrar-me" entre sessões exigiria um componente de
  cookies dedicado — fora do escopo deste bloco inicial.
* O rate limiting no lado do cliente (`auth_service._rate_limit_excedido`) é defesa em
  profundidade, por sessão de navegador — a proteção principal contra força bruta vem do
  próprio Supabase Auth no servidor.
