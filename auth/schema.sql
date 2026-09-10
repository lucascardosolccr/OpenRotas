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
