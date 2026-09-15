-- ==============================================================================
-- Schema de autenticação — Motor Nacional de Inteligência Logística para Exames
-- ==============================================================================
-- Execute este arquivo INTEIRO no SQL Editor do seu projeto Supabase
-- (painel do projeto → SQL Editor → New query → cole tudo → Run).
--
-- O Supabase já mantém a tabela `auth.users` (e-mail, senha com hash bcrypt,
-- confirmação, sessões) — este schema só ADICIONA a tabela `public.profiles`
-- com os dados de perfil que a aplicação pede no cadastro (nome, telefone,
-- endereço), ligada 1-para-1 com `auth.users` por triggers automáticos.
-- Nunca duplicamos e-mail/senha aqui: eles continuam vivendo só em auth.users.
-- ==============================================================================

create table if not exists public.profiles (
    id uuid primary key references auth.users (id) on delete cascade,
    nome_completo text not null default '',
    email text not null,
    telefone text,
    logradouro text,
    numero text,
    complemento text,
    bairro text,
    cidade text,
    uf text,
    cep text,
    -- [§20/§21] preparado para autorização e administração futuras, sem exigir
    -- construir o painel admin agora.
    role text not null default 'user' check (role in ('user', 'admin')),
    status text not null default 'ativo' check (status in ('ativo', 'desativado')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    last_login_at timestamptz
);

-- Unicidade de e-mail garantida no BANCO (não só no formulário) — case-insensitive,
-- já que "Fulano@x.com" e "fulano@x.com" devem ser a MESMA conta.
create unique index if not exists profiles_email_idx on public.profiles (lower(email));

-- ------------------------------------------------------------------------------
-- Row Level Security: cada usuário só enxerga/edita a própria linha. Sem isso,
-- a chave "anon" (pública, usada pelo cliente Streamlit) permitiria qualquer
-- pessoa ler/editar o perfil de qualquer outra — a segurança real está aqui,
-- não em "esconder" a chave.
-- ------------------------------------------------------------------------------
alter table public.profiles enable row level security;

drop policy if exists "usuarios veem o proprio perfil" on public.profiles;
create policy "usuarios veem o proprio perfil"
    on public.profiles for select
    using (auth.uid() = id);

drop policy if exists "usuarios atualizam o proprio perfil" on public.profiles;
create policy "usuarios atualizam o proprio perfil"
    on public.profiles for update
    using (auth.uid() = id)
    with check (auth.uid() = id);

-- Nenhuma política de INSERT/DELETE para o usuário comum: a criação da linha é
-- feita SÓ pelo trigger abaixo (security definer), nunca diretamente pelo
-- cliente — impede um usuário mal-intencionado de inserir um perfil com
-- id de outra pessoa. Exclusão de conta fica fora do escopo deste bloco.

-- ------------------------------------------------------------------------------
-- Trigger: cria a linha de perfil automaticamente quando uma conta é criada em
-- auth.users (via auth.sign_up), usando os metadados (nome/telefone) enviados
-- no cadastro. security definer: roda com permissão de dono da função, não do
-- usuário anônimo — é o padrão oficial do Supabase para este cenário.
-- ------------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
    insert into public.profiles (id, nome_completo, email, telefone)
    values (
        new.id,
        coalesce(new.raw_user_meta_data ->> 'nome_completo', ''),
        new.email,
        coalesce(new.raw_user_meta_data ->> 'telefone', '')
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- ------------------------------------------------------------------------------
-- Trigger: mantém `last_login_at` sincronizado a cada login bem-sucedido
-- (o Supabase já atualiza auth.users.last_sign_in_at internamente a cada
-- sign-in — só espelhamos essa data no perfil, sem reimplementar o rastreio).
-- ------------------------------------------------------------------------------
create or replace function public.handle_user_login()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
    if new.last_sign_in_at is distinct from old.last_sign_in_at then
        update public.profiles set last_login_at = new.last_sign_in_at where id = new.id;
    end if;
    return new;
end;
$$;

drop trigger if exists on_auth_user_login on auth.users;
create trigger on_auth_user_login
    after update on auth.users
    for each row execute function public.handle_user_login();

-- ------------------------------------------------------------------------------
-- Trigger: mantém `updated_at` sempre correto em qualquer UPDATE do perfil
-- (nunca confiamos no cliente para enviar essa data — o banco é a fonte da
-- verdade, §34 da missão: nunca confiar só no lado que chama).
-- ------------------------------------------------------------------------------
create or replace function public.handle_profile_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists on_profile_updated on public.profiles;
create trigger on_profile_updated
    before update on public.profiles
    for each row execute function public.handle_profile_updated_at();

-- ==============================================================================
-- [RECURSOS DO USUÁRIO] Anotações, estudos salvos e foto de perfil
-- ------------------------------------------------------------------------------
-- Mesmas garantias das profiles: Row Level Security por usuário (cada um só vê/
-- edita o que é seu), e updated_at mantido pelo banco. Rode este bloco junto do
-- restante do arquivo (é idempotente: create ... if not exists / drop policy if
-- exists). Se você NÃO rodar, a aplicação degrada com elegância — os recursos
-- aparecem como "indisponíveis" em vez de quebrar.
-- ==============================================================================

-- Foto de perfil: só a URL pública fica no perfil; o arquivo em si vive no
-- Storage (bucket 'avatars'). Coluna adicionada de forma idempotente.
alter table public.profiles add column if not exists avatar_url text;

-- [COMPARTILHAR] Instante em que o usuário viu pela última vez a seção "Estudos recebidos".
-- Serve ao badge de notificação: estudos compartilhados com created_at posterior a esta data são
-- "novos". Fica no PRÓPRIO perfil (que o usuário pode atualizar via RLS), sem tornar as linhas de
-- compartilhamento graváveis pelo destinatário.
alter table public.profiles add column if not exists estudos_recebidos_vistos_em timestamptz;

-- ------------------------------------------------------------------------------
-- Anotações do usuário
-- ------------------------------------------------------------------------------
create table if not exists public.anotacoes (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    titulo text not null default '',
    conteudo text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists anotacoes_user_idx on public.anotacoes (user_id, updated_at desc);
alter table public.anotacoes enable row level security;

drop policy if exists "anotacoes: dono le" on public.anotacoes;
create policy "anotacoes: dono le" on public.anotacoes for select using (auth.uid() = user_id);
drop policy if exists "anotacoes: dono insere" on public.anotacoes;
create policy "anotacoes: dono insere" on public.anotacoes for insert with check (auth.uid() = user_id);
drop policy if exists "anotacoes: dono atualiza" on public.anotacoes;
create policy "anotacoes: dono atualiza" on public.anotacoes for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "anotacoes: dono exclui" on public.anotacoes;
create policy "anotacoes: dono exclui" on public.anotacoes for delete using (auth.uid() = user_id);

drop trigger if exists on_anotacao_updated on public.anotacoes;
create trigger on_anotacao_updated
    before update on public.anotacoes
    for each row execute function public.handle_profile_updated_at();

-- ------------------------------------------------------------------------------
-- Estudos salvos (últimos resultados que o usuário decide guardar)
-- `resumo` = metadados leves (nome, contagens, KPIs) em JSON para listar rápido;
-- `dados` = a tabela de resultado serializada (JSON) para restaurar depois.
-- ------------------------------------------------------------------------------
create table if not exists public.estudos_salvos (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    nome text not null default 'Estudo sem nome',
    tipo text not null default 'lote',
    resumo jsonb not null default '{}'::jsonb,
    dados jsonb,
    created_at timestamptz not null default now()
);
create index if not exists estudos_user_idx on public.estudos_salvos (user_id, created_at desc);
alter table public.estudos_salvos enable row level security;

drop policy if exists "estudos: dono le" on public.estudos_salvos;
create policy "estudos: dono le" on public.estudos_salvos for select using (auth.uid() = user_id);
drop policy if exists "estudos: dono insere" on public.estudos_salvos;
create policy "estudos: dono insere" on public.estudos_salvos for insert with check (auth.uid() = user_id);
drop policy if exists "estudos: dono exclui" on public.estudos_salvos;
create policy "estudos: dono exclui" on public.estudos_salvos for delete using (auth.uid() = user_id);

-- ------------------------------------------------------------------------------
-- Compartilhamento de estudos ENTRE PERFIS (por e-mail do destinatário)
-- ------------------------------------------------------------------------------
-- Um estudo continua pertencendo ao DONO; compartilhar cria uma linha aqui ligando o estudo ao
-- e-mail de outro perfil. O dono nunca precisa (nem consegue, por RLS) descobrir o id do outro
-- usuário — casa-se por e-mail. O destinatário passa a poder LER a linha do estudo graças à policy
-- "estudos: destinatario le compartilhado" abaixo. Tudo sob RLS, sem service_role.
create table if not exists public.estudos_compartilhados (
    id uuid primary key default gen_random_uuid(),
    estudo_id uuid not null references public.estudos_salvos (id) on delete cascade,
    owner_id uuid not null references auth.users (id) on delete cascade,
    destinatario_email text not null,
    mensagem text not null default '',
    created_at timestamptz not null default now()
);
-- e-mail sempre em minúsculas (a aplicação normaliza; garantimos a busca case-insensitive)
create index if not exists estudos_comp_dest_idx on public.estudos_compartilhados (lower(destinatario_email), created_at desc);
create index if not exists estudos_comp_owner_idx on public.estudos_compartilhados (owner_id, created_at desc);
-- não duplicar o mesmo compartilhamento (mesmo estudo para o mesmo e-mail)
create unique index if not exists estudos_comp_uniq on public.estudos_compartilhados (estudo_id, lower(destinatario_email));
alter table public.estudos_compartilhados enable row level security;

-- o DONO gerencia (vê/cria/revoga) os compartilhamentos que criou
drop policy if exists "comp: dono le" on public.estudos_compartilhados;
create policy "comp: dono le" on public.estudos_compartilhados for select using (auth.uid() = owner_id);
drop policy if exists "comp: dono insere" on public.estudos_compartilhados;
create policy "comp: dono insere" on public.estudos_compartilhados for insert with check (auth.uid() = owner_id);
drop policy if exists "comp: dono exclui" on public.estudos_compartilhados;
create policy "comp: dono exclui" on public.estudos_compartilhados for delete using (auth.uid() = owner_id);

-- o DESTINATÁRIO enxerga os compartilhamentos endereçados ao SEU e-mail (do próprio perfil)
drop policy if exists "comp: destinatario le" on public.estudos_compartilhados;
create policy "comp: destinatario le" on public.estudos_compartilhados for select
    using (lower(destinatario_email) = lower((select p.email from public.profiles p where p.id = auth.uid())));

-- policy EXTRA em estudos_salvos: o destinatário de um compartilhamento pode LER a linha do estudo.
-- Casamos o e-mail do compartilhamento com o e-mail do próprio perfil de quem consulta (a subconsulta
-- em profiles roda como o usuário atual e só retorna a própria linha — permitido pela RLS de profiles).
drop policy if exists "estudos: destinatario le compartilhado" on public.estudos_salvos;
create policy "estudos: destinatario le compartilhado" on public.estudos_salvos for select
    using (exists (
        select 1 from public.estudos_compartilhados c
        where c.estudo_id = estudos_salvos.id
          and lower(c.destinatario_email) = lower((select p.email from public.profiles p where p.id = auth.uid()))
    ));

-- ------------------------------------------------------------------------------
-- Storage: bucket público 'avatars' para as fotos de perfil.
-- (Rode também, se preferir criar o bucket por SQL. Alternativa: crie o bucket
--  'avatars' pelo painel Storage do Supabase, marcando-o como público.)
-- ------------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('avatars', 'avatars', true)
on conflict (id) do nothing;

drop policy if exists "avatars: leitura publica" on storage.objects;
create policy "avatars: leitura publica" on storage.objects for select
    using (bucket_id = 'avatars');
drop policy if exists "avatars: dono envia" on storage.objects;
create policy "avatars: dono envia" on storage.objects for insert
    with check (bucket_id = 'avatars' and auth.uid()::text = (storage.foldername(name))[1]);
drop policy if exists "avatars: dono atualiza" on storage.objects;
create policy "avatars: dono atualiza" on storage.objects for update
    using (bucket_id = 'avatars' and auth.uid()::text = (storage.foldername(name))[1]);
drop policy if exists "avatars: dono exclui" on storage.objects;
create policy "avatars: dono exclui" on storage.objects for delete
    using (bucket_id = 'avatars' and auth.uid()::text = (storage.foldername(name))[1]);
